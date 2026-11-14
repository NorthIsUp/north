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
use crate::feature::split_word;
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
    ///
    /// # Errors
    ///
    /// [`Error::InvalidCacheName`] when `name` is empty, `.`/`..`, or has characters other than letters, digits, `_`, `.` and `-`.
    pub fn named(name: &str) -> Result<Self> {
        Ok(Self::at(
            cache_dir().join(format!("{}.json", validate_name(name)?)),
        ))
    }

    /// Named after `$alfred_workflow_bundleid`.
    ///
    /// # Errors
    ///
    /// [`Error::InvalidCacheName`] when the variable is unset (outside Alfred) or not a plain filename.
    pub fn for_workflow() -> Result<Self> {
        Self::named(&env::var("alfred_workflow_bundleid").unwrap_or_default())
    }

    pub fn at(path: impl Into<PathBuf>) -> Self {
        Self { path: path.into() }
    }

    #[must_use]
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// `None` for a missing, unreadable, or malformed cache.
    pub async fn read(&self) -> Option<Menu> {
        serde_json::from_slice(&fs::read(&self.path).await.ok()?).ok()
    }

    /// Atomically replace the cache.
    ///
    /// # Errors
    ///
    /// I/O errors creating the directory or writing and renaming the file.
    pub async fn write(&self, menu: &Menu) -> Result<()> {
        atomic_write(&self.path, &serde_json::to_vec(menu)?).await
    }

    /// Re-run this binary detached with `args` (usually a flag that skips the cache) unless a
    /// refresh started within [`REFRESH_INTERVAL`]. Returns whether it launched.
    pub async fn refresh<I, S>(&self, args: I) -> bool
    where
        I: IntoIterator<Item = S>,
        S: AsRef<std::ffi::OsStr>,
    {
        spawn_self(args, &self.refresh_marker(), REFRESH_INTERVAL).await
    }

    /// `<cache>.refresh.pid`: the throttle marker, holding the refresh's PID.
    #[must_use]
    pub fn refresh_marker(&self) -> PathBuf {
        with_suffix(&self.path, ".refresh.pid")
    }

    /// An item that stops a pending refresh and deletes this cache, the icon
    /// cache, and Alfred's cache files for the workflow.
    pub fn clear_item(&self, icons: &Icons) -> ItemBuilder {
        Item::exec("clear cache", self.cleanup(icons).command())
            .subtitle("Delete this workflow's cached menus, icons and data")
    }

    /// Clear every cache the first time `version` runs, so an update never reads what an older
    /// version wrote. The `<cache>.version` marker is outside what clearing deletes.
    ///
    /// # Errors
    ///
    /// I/O errors running the cleanup or writing the marker.
    pub async fn clear_on_new_version(&self, icons: &Icons, version: &str) -> Result<()> {
        let marker = with_suffix(&self.path, ".version");
        if fs::read_to_string(&marker)
            .await
            .is_ok_and(|seen| seen == version)
        {
            return Ok(());
        }
        Command::new("/bin/sh")
            .arg("-c")
            .arg(self.cleanup(icons).command())
            .status()
            .await?;
        atomic_write(&marker, version.as_bytes()).await
    }

    fn cleanup(&self, icons: &Icons) -> CacheCleanup {
        let environment = env::vars().collect();
        CacheCleanup::from_environment(self.path.clone(), icons.dir.clone(), &home(), &environment)
    }
}

/// Every word after an optional keyword starts `clear` or `cache` (`py cl`, `cache clear`).
pub(crate) fn wants_clear(query: &str) -> bool {
    let words = |q: &str| {
        let q = q.to_lowercase();
        !q.trim().is_empty()
            && q.split_whitespace()
                .all(|w| "clear".starts_with(w) || "cache".starts_with(w))
    };
    words(query) || words(split_word(query.trim()).1)
}

/// `$XDG_CACHE_HOME/alfred`, else `~/.cache/alfred` when `~/.cache` exists, else `/tmp/alfred`.
#[must_use]
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

/// Build `path` atomically: `write` fills a uniquely named sibling, renamed over `path` only on
/// success and removed on failure, so readers never see a partial file.
pub(crate) async fn replace<T, F, Fut>(path: &Path, write: F) -> Result<T>
where
    F: FnOnce(PathBuf) -> Fut,
    Fut: Future<Output = Result<T>>,
{
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let parent = path.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(parent).await?;
    let name = path.file_name().unwrap_or_default().to_string_lossy();
    let temporary = parent.join(format!(
        ".{name}.{}.{}.tmp",
        std::process::id(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    ));
    let written = match write(temporary.clone()).await {
        Ok(value) => fs::rename(&temporary, path)
            .await
            .map(|()| value)
            .map_err(Error::from),
        Err(e) => Err(e),
    };
    if written.is_err() {
        let _ = fs::remove_file(&temporary).await;
    }
    written
}

pub(crate) async fn atomic_write(path: &Path, payload: &[u8]) -> Result<()> {
    replace(path, |temporary| async move {
        Ok(fs::write(temporary, payload).await?)
    })
    .await
}

/// Re-run this binary detached with `args`, throttled by `marker` (see [`spawn_throttled`]).
pub(crate) async fn spawn_self<I, S>(args: I, marker: &Path, interval: Duration) -> bool
where
    I: IntoIterator<Item = S>,
    S: AsRef<std::ffi::OsStr>,
{
    let Ok(exe) = env::current_exe() else {
        return false;
    };
    spawn_throttled(Command::new(exe).args(args), marker, interval).await
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
        let spawned = spawn_unless_recent(command, &mut file, interval).await;
        // tokio closes files on a blocking thread, so the lock could outlive this call; release it now.
        let _ = file.into_std().await.unlock();
        spawned
    };
    attempt.await.unwrap_or(false)
}

/// With the marker locked: spawn `command` unless the marker says one started within `interval`.
async fn spawn_unless_recent(
    command: &mut Command,
    file: &mut File,
    interval: Duration,
) -> io::Result<bool> {
    let meta = file.metadata().await?;
    let age = SystemTime::now()
        .duration_since(meta.modified()?)
        .unwrap_or_default();
    if meta.len() > 0 && age < interval {
        return Ok(false);
    }
    overwrite(file, "pending").await?;
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
    overwrite(file, &pid.to_string()).await?;
    Ok(true)
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
    async fn clears_once_per_new_version() {
        let dir = tempfile::tempdir().unwrap();
        let cache = Cache::at(dir.path().join("menu.json"));
        let icons = Icons::new(dir.path().join("icons"));
        let menu = Menu::from_iter([Item::message("old", "")]);
        for (version, cleared) in [("1.0", true), ("1.0", false), ("1.1", true)] {
            cache.write(&menu).await.unwrap();
            cache.clear_on_new_version(&icons, version).await.unwrap();
            assert_eq!(cache.read().await.is_none(), cleared, "{version}");
        }
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
        assert!(
            spawn_throttled(
                &mut Command::new("true"),
                &cache.refresh_marker(),
                REFRESH_INTERVAL
            )
            .await
        );
        assert!(
            !spawn_throttled(
                &mut Command::new("true"),
                &cache.refresh_marker(),
                REFRESH_INTERVAL
            )
            .await
        );
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
            !spawn_throttled(
                &mut Command::new(dir.path().join("missing")),
                &cache.refresh_marker(),
                REFRESH_INTERVAL
            )
            .await
        );
        assert_eq!(
            fs::read_to_string(cache.refresh_marker()).await.unwrap(),
            "pending"
        );
        assert!(
            !spawn_throttled(
                &mut Command::new("true"),
                &cache.refresh_marker(),
                REFRESH_INTERVAL
            )
            .await
        );
    }
}
