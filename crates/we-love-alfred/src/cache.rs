//! A menu cache served on every keystroke and refreshed in the background.

use std::env;
use std::ffi::OsString;
use std::io::{self, SeekFrom};
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, SystemTime};

use tokio::fs::{self, File, OpenOptions};
use tokio::io::{AsyncSeekExt, AsyncWriteExt};
use tokio::process::Command;

use crate::cleanup::CacheCleanup;
use crate::{Error, Icons, Item, ItemBuilder, Menu, Result};

/// Minimum gap between background refresh launches, including failed ones.
pub const REFRESH_INTERVAL: Duration = Duration::from_secs(60);

/// A cached [`Menu`] on disk.
///
/// ```
/// use we_love_alfred::{Cache, Item, Menu};
///
/// # tokio_test(async {
/// let dir = tempfile::tempdir()?;
/// let cache = Cache::at(dir.path().join("menu.json"));
/// assert!(cache.read().await.is_none());
/// cache.write(&Menu::from_iter([Item { title: "Ready".into(), ..Item::default() }])).await?;
/// assert_eq!(cache.read().await.unwrap().items[0].title, "Ready");
/// # Ok::<_, we_love_alfred::Error>(()) });
/// # fn tokio_test<F: Future<Output = Result<(), we_love_alfred::Error>>>(f: F) {
/// #     tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap().block_on(f).unwrap()
/// # }
/// ```
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Cache {
    path: PathBuf,
}

impl Cache {
    /// `<name>.json` in [`cache_dir`]; `name` must be a plain filename stem.
    pub fn named(name: &str) -> Result<Self> {
        Ok(Self::at(
            cache_dir().join(format!("{}.json", validate_name(name)?)),
        ))
    }

    /// Named after `$alfred_workflow_bundleid`.
    pub fn for_workflow() -> Result<Self> {
        Self::named(&env::var("alfred_workflow_bundleid").unwrap_or_default())
    }

    pub fn at(path: impl Into<PathBuf>) -> Self {
        Self { path: path.into() }
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    /// `None` for a missing, unreadable, or malformed cache.
    pub async fn read(&self) -> Option<Menu> {
        serde_json::from_slice(&fs::read(&self.path).await.ok()?).ok()
    }

    /// Atomically replace the cache.
    pub async fn write(&self, menu: &Menu) -> Result<()> {
        atomic_write(&self.path, &serde_json::to_vec(menu)?).await
    }

    /// Launch `command` detached unless a refresh started within [`REFRESH_INTERVAL`].
    ///
    /// Returns whether it launched.
    pub async fn refresh(&self, command: &mut Command) -> bool {
        spawn_throttled(command, &self.refresh_marker(), REFRESH_INTERVAL).await
    }

    /// `<cache>.refresh.pid`: the throttle marker, holding the refresh's PID.
    pub fn refresh_marker(&self) -> PathBuf {
        with_suffix(&self.path, ".refresh.pid")
    }

    /// An item that stops a pending refresh and deletes this cache, the icon
    /// cache, and Alfred's cache files for the workflow.
    pub fn clear_item(&self, icons: &Icons) -> ItemBuilder {
        let environment = env::vars().collect();
        let cleanup = CacheCleanup::from_environment(
            self.path.clone(),
            icons.dir.clone(),
            &home(),
            &environment,
        );
        Item::exec("clear cache", cleanup.command())
    }
}

/// `$XDG_CACHE_HOME/alfred`, else `~/.cache/alfred` when `~/.cache` exists, else `/tmp/alfred`.
pub fn cache_dir() -> PathBuf {
    let home_cache = home().join(".cache");
    let root = match env::var_os("XDG_CACHE_HOME").filter(|x| !x.is_empty()) {
        Some(xdg) => PathBuf::from(xdg),
        None if home_cache.is_dir() => home_cache,
        None => PathBuf::from("/tmp"),
    };
    root.join("alfred")
}

pub(crate) fn validate_name(name: &str) -> Result<&str> {
    let valid = |c: char| c.is_alphanumeric() || "_.-".contains(c);
    if name.is_empty() || name == "." || name == ".." || !name.chars().all(valid) {
        return Err(Error::InvalidCacheName(name.to_owned()));
    }
    Ok(name)
}

pub(crate) fn home() -> PathBuf {
    env::var_os("HOME").map_or_else(|| env::home_dir().unwrap_or_default(), PathBuf::from)
}

/// `~/` expanded against [`home`].
pub(crate) fn expand_home(path: &str) -> PathBuf {
    match path.strip_prefix("~/") {
        Some(rest) => home().join(rest),
        None if path == "~" => home(),
        None => PathBuf::from(path),
    }
}

pub(crate) fn with_suffix(path: &Path, suffix: &str) -> PathBuf {
    let mut name = OsString::from(path);
    name.push(suffix);
    name.into()
}

/// Write to a uniquely named sibling, then rename it over `path`.
pub(crate) async fn atomic_write(path: &Path, payload: &[u8]) -> Result<()> {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let parent = path.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(parent).await?;
    let name = path.file_name().unwrap_or_default().to_string_lossy();
    let unique = format!(
        ".{name}.{}.{}.tmp",
        std::process::id(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    );
    let temporary = parent.join(unique);
    let written = async {
        fs::write(&temporary, payload).await?;
        fs::rename(&temporary, path).await
    }
    .await;
    if written.is_err() {
        let _ = fs::remove_file(&temporary).await;
    }
    Ok(written?)
}

/// Spawn `command` detached, at most once per `interval` per `marker`, counting failed spawns.
pub(crate) async fn spawn_throttled(
    command: &mut Command,
    marker: &Path,
    interval: Duration,
) -> bool {
    let attempt = async {
        if let Some(parent) = marker.parent() {
            fs::create_dir_all(parent).await?;
        }
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(marker)
            .await?;
        let file = file.into_std().await;
        if file.try_lock().is_err() {
            return Ok::<_, io::Error>(false);
        }
        let mut file = File::from_std(file);
        let meta = file.metadata().await?;
        let age = SystemTime::now()
            .duration_since(meta.modified()?)
            .unwrap_or_default();
        if meta.len() > 0 && age < interval {
            return Ok(false);
        }
        overwrite(&mut file, "pending").await?;
        let child = command
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            // Own process group, so the refresh outlives Alfred killing the Script Filter.
            .process_group(0)
            .spawn();
        let Some(pid) = child.ok().and_then(|c| c.id()) else {
            return Ok(false);
        };
        overwrite(&mut file, &pid.to_string()).await?;
        Ok(true)
    };
    attempt.await.unwrap_or(false)
}

async fn overwrite(file: &mut File, contents: &str) -> io::Result<()> {
    file.set_len(0).await?;
    file.seek(SeekFrom::Start(0)).await?;
    file.write_all(contents.as_bytes()).await?;
    file.flush().await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_are_validated() {
        for bad in ["../escape", "..", "a/b", ""] {
            assert!(
                matches!(Cache::named(bad), Err(Error::InvalidCacheName(_))),
                "{bad}"
            );
        }
        assert!(
            Cache::named("com.example.workflow")
                .unwrap()
                .path()
                .ends_with("alfred/com.example.workflow.json")
        );
    }

    #[tokio::test]
    async fn malformed_caches_read_as_none() {
        let dir = tempfile::tempdir().unwrap();
        let cache = Cache::at(dir.path().join("menu.json"));
        fs::write(cache.path(), r#"{"items": ["#).await.unwrap();
        assert_eq!(cache.read().await, None);
        fs::write(cache.path(), r#"{"items": [{"subtitle": "no title"}]}"#)
            .await
            .unwrap();
        assert_eq!(cache.read().await, None);
    }

    #[tokio::test]
    async fn concurrent_writes_are_atomic() {
        let dir = tempfile::tempdir().unwrap();
        let cache = Cache::at(dir.path().join("menu.json"));
        let menus: Vec<Menu> = (0..8)
            .map(|n| Menu::from_iter([Item::message(n.to_string(), "")]))
            .collect();
        futures_util::future::try_join_all(menus.iter().map(|m| cache.write(m)))
            .await
            .unwrap();
        assert!(menus.contains(&cache.read().await.unwrap()));
        assert_eq!(
            std::fs::read_dir(dir.path()).unwrap().count(),
            1,
            "temporary files left behind"
        );
    }

    #[tokio::test]
    async fn refresh_records_pid_and_throttles() {
        let _serial = crate::serial().await;
        let dir = tempfile::tempdir().unwrap();
        let cache = Cache::at(dir.path().join("menu.json"));
        assert!(cache.refresh(&mut Command::new("true")).await);
        assert!(!cache.refresh(&mut Command::new("true")).await);
        assert!(
            fs::read_to_string(cache.refresh_marker())
                .await
                .unwrap()
                .parse::<u32>()
                .is_ok()
        );
        assert!(
            spawn_throttled(
                &mut Command::new("true"),
                &cache.refresh_marker(),
                Duration::ZERO
            )
            .await
        );
    }

    #[tokio::test]
    async fn failed_refresh_is_throttled() {
        let _serial = crate::serial().await;
        let dir = tempfile::tempdir().unwrap();
        let cache = Cache::at(dir.path().join("menu.json"));
        assert!(
            !cache
                .refresh(&mut Command::new(dir.path().join("missing")))
                .await
        );
        assert_eq!(
            fs::read_to_string(cache.refresh_marker()).await.unwrap(),
            "pending"
        );
        assert!(!cache.refresh(&mut Command::new("true")).await);
    }
}
