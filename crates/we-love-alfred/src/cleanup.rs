//! Resolve workflow-owned cache paths before dispatching a clear-cache command through zsh.

use std::collections::HashMap;
use std::path::{Component, Path, PathBuf};

use crate::cache::{validate_name, with_suffix};
use crate::shell::quote;

/// Paths the "clear cache" action deletes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CacheCleanup {
    pub menu_cache: PathBuf,
    pub icon_cache: PathBuf,
    /// Alfred's cache directory for this workflow; emptied entirely.
    pub workflow_cache: Option<PathBuf>,
    /// Alfred's data directory for this workflow; only `*.cache` files are removed.
    pub workflow_data: Option<PathBuf>,
}

impl CacheCleanup {
    /// Workflow directories come from Alfred's `alfred_workflow_cache`/`_data`, else the bundle ID.
    ///
    /// Relative paths, paths containing `..`, `home` and its ancestors, and the
    /// shared Workflow Data roots are never selected.
    pub fn from_environment(
        menu_cache: PathBuf,
        icon_cache: PathBuf,
        home: &Path,
        environment: &HashMap<String, String>,
    ) -> Self {
        let cache_root = home.join("Library/Caches/com.runningwithcrayons.Alfred/Workflow Data");
        let data_root = home.join("Library/Application Support/Alfred/Workflow Data");
        let bundle = environment
            .get("alfred_workflow_bundleid")
            .filter(|b| !b.is_empty())
            .and_then(|b| validate_name(b).ok());

        let workflow_path = |key: &str, root: &Path| {
            let path = match environment.get(key).filter(|raw| !raw.is_empty()) {
                Some(raw) => PathBuf::from(raw),
                None => root.join(bundle?),
            };
            let blocked =
                home.ancestors().any(|a| a == path) || path == cache_root || path == data_root;
            let escapes = path.components().any(|c| c == Component::ParentDir);
            (path.is_absolute() && !blocked && !escapes).then_some(path)
        };

        Self {
            workflow_cache: workflow_path("alfred_workflow_cache", &cache_root),
            workflow_data: workflow_path("alfred_workflow_data", &data_root),
            menu_cache,
            icon_cache,
        }
    }

    /// A POSIX shell command that stops a pending refresh and deletes the caches.
    pub fn command(&self) -> String {
        let marker = quote(&with_suffix(&self.menu_cache, ".refresh.pid").to_string_lossy());
        let mut commands = vec![
            format!(
                "if [ -f {marker} ]; then refresh_pid=$(cat {marker}); \
                 case \"$refresh_pid\" in \"\"|*[!0-9]*) ;; *) \
                 if [ \"$refresh_pid\" -gt 1 ]; then kill \"$refresh_pid\" 2>/dev/null; fi ;; esac; fi"
            ),
            format!(
                "rm -f {marker} {}",
                quote(&self.menu_cache.to_string_lossy())
            ),
            delete_files(&self.icon_cache, None),
        ];
        if let Some(cache) = &self.workflow_cache {
            let path = quote(&cache.to_string_lossy());
            commands.push(format!(
                "if [ -d {path} ]; then find {path} -mindepth 1 -delete; fi"
            ));
        }
        if let Some(data) = &self.workflow_data {
            commands.push(delete_files(data, Some("*.cache")));
        }
        commands.join("; ")
    }
}

fn delete_files(path: &Path, pattern: Option<&str>) -> String {
    let directory = quote(&path.to_string_lossy());
    let selection = pattern
        .map(|p| format!(" -name {}", quote(p)))
        .unwrap_or_default();
    format!("if [ -d {directory} ]; then find {directory} -type f{selection} -delete; fi")
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::process::Command;

    use super::*;

    fn cleanup(home: &Path, environment: &[(&str, String)]) -> CacheCleanup {
        let environment = environment
            .iter()
            .map(|(k, v)| ((*k).to_owned(), v.clone()))
            .collect();
        CacheCleanup::from_environment(
            home.join("menu.json"),
            home.join("icons"),
            home,
            &environment,
        )
    }

    #[tokio::test]
    async fn cleanup_preserves_workflow_data_and_sibling_caches() {
        let _serial = crate::serial().await;
        for explicit_paths in [false, true] {
            let dir = tempfile::tempdir().unwrap();
            let home = dir.path();
            let mut environment = vec![(
                "alfred_workflow_bundleid",
                "com.example.workflow".to_owned(),
            )];
            if explicit_paths {
                environment.push((
                    "alfred_workflow_cache",
                    home.join("workflow's cache").display().to_string(),
                ));
                environment.push((
                    "alfred_workflow_data",
                    home.join("workflow's data").display().to_string(),
                ));
            }
            let cleanup = cleanup(home, &environment);
            let cache = cleanup.workflow_cache.clone().unwrap();
            let data = cleanup.workflow_data.clone().unwrap();
            for dir in [&cache, &data, &cleanup.icon_cache] {
                fs::create_dir_all(dir).unwrap();
            }
            let sibling = cache.parent().unwrap().join("another-workflow/cache.json");
            fs::create_dir_all(sibling.parent().unwrap()).unwrap();
            let marker = with_suffix(&cleanup.menu_cache, ".refresh.pid");
            let doomed = [
                cache.join("old.json"),
                data.join("state.cache"),
                cleanup.menu_cache.clone(),
                marker.clone(),
                cleanup.icon_cache.join("icon.png"),
            ];
            for file in &doomed {
                fs::write(file, "cache").unwrap();
            }
            fs::write(&marker, "pending").unwrap();
            fs::write(data.join("settings.json"), "user data").unwrap();
            fs::write(&sibling, "other workflow").unwrap();

            let script = format!(
                r#"kill() {{ printf "KILLED:%s\n" "$1"; }}; {}"#,
                cleanup.command()
            );
            let out = Command::new("/bin/sh")
                .arg("-c")
                .arg(script)
                .env_clear()
                .output()
                .unwrap();
            assert!(
                out.status.success(),
                "{}",
                String::from_utf8_lossy(&out.stderr)
            );
            assert!(out.stdout.is_empty());
            for file in &doomed {
                assert!(!file.exists(), "{} survived", file.display());
            }
            assert_eq!(
                fs::read_to_string(data.join("settings.json")).unwrap(),
                "user data"
            );
            assert_eq!(fs::read_to_string(&sibling).unwrap(), "other workflow");
        }
    }

    #[test]
    fn missing_bundle_does_not_select_all_workflows() {
        let dir = tempfile::tempdir().unwrap();
        let cleanup = cleanup(dir.path(), &[]);
        assert_eq!(
            (cleanup.workflow_cache, cleanup.workflow_data),
            (None, None)
        );
    }

    #[test]
    fn relative_workflow_paths_are_ignored() {
        let dir = tempfile::tempdir().unwrap();
        for relative in [".", "..", "Library/Caches"] {
            let cleanup = cleanup(
                dir.path(),
                &[
                    ("alfred_workflow_cache", relative.into()),
                    ("alfred_workflow_data", relative.into()),
                ],
            );
            assert_eq!(
                (cleanup.workflow_cache, cleanup.workflow_data),
                (None, None)
            );
        }
    }

    #[test]
    fn workflow_roots_and_home_are_never_selected() {
        let dir = tempfile::tempdir().unwrap();
        let home = dir.path();
        let cleanup = cleanup(
            home,
            &[
                (
                    "alfred_workflow_cache",
                    home.join("Library/Caches/com.runningwithcrayons.Alfred/Workflow Data")
                        .display()
                        .to_string(),
                ),
                ("alfred_workflow_data", home.display().to_string()),
            ],
        );
        assert_eq!(
            (cleanup.workflow_cache, cleanup.workflow_data),
            (None, None)
        );
    }
}
