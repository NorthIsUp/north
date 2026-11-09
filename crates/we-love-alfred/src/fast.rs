//! Serve a cached menu without touching the network, refreshing it in the background.

use std::ffi::OsString;
use std::fs::{self, File, OpenOptions};
use std::io::{Seek, SeekFrom, Write};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, SystemTime};
use std::{env, io};

use crate::{Error, Menu, Result};

/// How often a failing background refresh may be retried.
pub const REFRESH_INTERVAL: Duration = Duration::from_secs(60);

/// `<name>.json`, where `name` is the argument, `$alfred_workflow_bundleid`, or `maxcare-menu`.
pub fn cache_filename(name: Option<&str>) -> Result<String> {
    let bundle = env::var("alfred_workflow_bundleid").ok();
    let name = name
        .filter(|n| !n.is_empty())
        .or(bundle.as_deref().filter(|b| !b.is_empty()))
        .unwrap_or("maxcare-menu");
    let valid = |c: char| c.is_alphanumeric() || "_.-".contains(c);
    if name.is_empty() || name == "." || name == ".." || !name.chars().all(valid) {
        return Err(Error::InvalidCacheName(name.to_owned()));
    }
    Ok(format!("{name}.json"))
}

/// `$XDG_CACHE_HOME/alfred/`, else `~/.cache/alfred/` when `~/.cache` exists, else `/tmp/alfred/`.
pub fn cache_path(name: Option<&str>) -> Result<PathBuf> {
    let home_cache = home().join(".cache");
    let root = match env::var_os("XDG_CACHE_HOME").filter(|x| !x.is_empty()) {
        Some(xdg) => PathBuf::from(xdg),
        None if home_cache.exists() => home_cache,
        // Existing workflows already use this rather than macOS's per-user temp dir.
        None => PathBuf::from("/tmp"),
    };
    Ok(root.join("alfred").join(cache_filename(name)?))
}

pub(crate) fn home() -> PathBuf {
    env::var_os("HOME").map_or_else(|| env::home_dir().unwrap_or_default(), PathBuf::from)
}

/// The throttle marker beside a cache: `<cache>.refresh.pid`.
pub fn refresh_marker(cache: &Path) -> PathBuf {
    with_suffix(cache, ".refresh.pid")
}

pub(crate) fn with_suffix(path: &Path, suffix: &str) -> PathBuf {
    let mut name = OsString::from(path);
    name.push(suffix);
    name.into()
}

/// `None` for a missing, unreadable, or malformed cache.
pub fn read_cache(path: &Path) -> Option<Menu> {
    serde_json::from_slice(&fs::read(path).ok()?).ok()
}

/// Atomically replace the cache at `path`.
pub fn write_cache(path: &Path, menu: &Menu) -> Result<()> {
    atomic_write(path, &serde_json::to_vec(menu)?)
}

/// Write to a uniquely named sibling, then rename it over `path`.
pub fn atomic_write(path: &Path, payload: &[u8]) -> Result<()> {
    let parent = path.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    let mut temporary = tempfile::NamedTempFile::new_in(parent)?;
    temporary.write_all(payload)?;
    temporary.persist(path).map_err(|e| e.error)?;
    Ok(())
}

/// Spawn `command` detached, at most once per `interval` per `marker`, counting failed spawns.
///
/// Returns whether a process was started. The marker holds the child's PID.
pub fn spawn_refresh(mut command: Command, marker: &Path, interval: Duration) -> bool {
    let mut attempt = || -> io::Result<bool> {
        if let Some(parent) = marker.parent() {
            fs::create_dir_all(parent)?;
        }
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(marker)?;
        if file.try_lock().is_err() {
            return Ok(false);
        }
        let meta = file.metadata()?;
        let age = SystemTime::now()
            .duration_since(meta.modified()?)
            .unwrap_or_default();
        if meta.len() > 0 && age < interval {
            return Ok(false);
        }
        overwrite(&mut file, "pending")?;
        let child = command
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            // Own process group, so the refresh outlives Alfred killing the Script Filter.
            .process_group(0)
            .spawn();
        let Ok(child) = child else { return Ok(false) };
        overwrite(&mut file, &child.id().to_string())?;
        Ok(true)
    };
    attempt().unwrap_or(false)
}

fn overwrite(file: &mut File, contents: &str) -> io::Result<()> {
    file.set_len(0)?;
    file.seek(SeekFrom::Start(0))?;
    file.write_all(contents.as_bytes())
}

/// Print the cached menu filtered by `query`; `Ok(false)` means the caller must build it.
///
/// A valid cache is served even when stale; `refresh` (usually the current
/// binary with `--no-cache`) is spawned in the background, throttled by
/// [`REFRESH_INTERVAL`].
pub fn serve(query: &str, name: Option<&str>, refresh: Option<Command>) -> Result<bool> {
    let path = cache_path(name)?;
    let Some(menu) = read_cache(&path) else {
        return Ok(false);
    };
    if let Some(command) = refresh {
        spawn_refresh(command, &refresh_marker(&path), REFRESH_INTERVAL);
    }
    println!("{}", serde_json::to_string(&menu.filter(query))?);
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::MenuItem;

    #[test]
    fn cache_names_are_validated() {
        assert_eq!(cache_filename(Some("second")).unwrap(), "second.json");
        for bad in ["../escape", "..", "a/b"] {
            assert!(matches!(
                cache_filename(Some(bad)),
                Err(Error::InvalidCacheName(_))
            ));
        }
    }

    #[test]
    fn cache_round_trips_and_rejects_garbage() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("menu.json");
        let menu = Menu {
            items: vec![MenuItem {
                title: "Ready".into(),
                ..Default::default()
            }],
            ..Default::default()
        };
        write_cache(&path, &menu).unwrap();
        assert_eq!(read_cache(&path), Some(menu));
        fs::write(&path, r#"{"items": ["#).unwrap();
        assert_eq!(read_cache(&path), None);
        fs::write(&path, r#"{"items": [{"subtitle": "no title"}]}"#).unwrap();
        assert_eq!(read_cache(&path), None);
    }

    #[test]
    fn refresh_records_pid_and_throttles() {
        let _serial = crate::serial();
        let dir = tempfile::tempdir().unwrap();
        let marker = dir.path().join("cache.json.refresh.pid");
        assert!(spawn_refresh(
            Command::new("true"),
            &marker,
            REFRESH_INTERVAL
        ));
        assert!(!spawn_refresh(
            Command::new("true"),
            &marker,
            REFRESH_INTERVAL
        ));
        assert!(fs::read_to_string(&marker).unwrap().parse::<u32>().is_ok());
        assert!(spawn_refresh(Command::new("true"), &marker, Duration::ZERO));
    }

    #[test]
    fn failed_refresh_is_throttled() {
        let _serial = crate::serial();
        let dir = tempfile::tempdir().unwrap();
        let marker = dir.path().join("cache.json.refresh.pid");
        let missing = || Command::new(dir.path().join("missing"));
        assert!(!spawn_refresh(missing(), &marker, REFRESH_INTERVAL));
        assert_eq!(fs::read_to_string(&marker).unwrap(), "pending");
        assert!(!spawn_refresh(
            Command::new("true"),
            &marker,
            REFRESH_INTERVAL
        ));
    }
}
