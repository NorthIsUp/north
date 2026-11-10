//! `[sources]`: one item per source folder and installed editor.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use futures_util::future::{self, BoxFuture, FutureExt};
use serde::Deserialize;
use tokio::fs;
use toml::Table;

use crate::cache::expand_home;
use crate::editor::Editor;
use crate::feature::{Context, Feature};
use crate::template::Scope;
use crate::{ItemBuilder, Result};

/// Paths or glob patterns, preferring a `*.code-workspace` inside a directory. Missing paths are skipped.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Sources {
    #[serde(default)]
    pub paths: Vec<String>,
}

impl Sources {
    /// These sources with the templates in `paths` rendered.
    pub(crate) fn render(&self, vars: &Table) -> Result<Self> {
        let none = BTreeMap::new();
        let scope = Scope {
            vars,
            bindings: &none,
            literals: &none,
        };
        Ok(Self {
            paths: self
                .paths
                .iter()
                .map(|p| scope.render(p))
                .collect::<Result<_>>()?,
        })
    }

    async fn targets(&self) -> Result<Vec<PathBuf>> {
        let patterns: Vec<String> = self
            .paths
            .iter()
            .map(|p| expand_home(p).to_string_lossy().into_owned())
            .collect();
        let paths = tokio::task::spawn_blocking(move || {
            patterns
                .iter()
                .flat_map(|pattern| glob::glob(pattern).into_iter().flatten().flatten())
                .collect::<Vec<PathBuf>>()
        })
        .await?;
        Ok(future::join_all(paths.iter().map(|path| workspace_or(path))).await)
    }
}

impl Feature for Sources {
    fn items<'a>(&'a self, _ctx: &'a Context) -> BoxFuture<'a, Result<Vec<ItemBuilder>>> {
        async move {
            let (targets, editors) = future::join(self.targets(), Editor::installed()).await;
            Ok(targets?
                .iter()
                .flat_map(|target| editors.iter().map(move |editor| editor.open(target)))
                .collect())
        }
        .boxed()
    }
}

/// The first `*.code-workspace` in a directory, else the path itself.
async fn workspace_or(path: &Path) -> PathBuf {
    if let Ok(mut entries) = fs::read_dir(path).await {
        while let Ok(Some(entry)) = entries.next_entry().await {
            if entry
                .path()
                .extension()
                .is_some_and(|e| e == "code-workspace")
            {
                return entry.path();
            }
        }
    }
    path.to_owned()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Icons;

    #[tokio::test]
    async fn globs_and_prefers_workspaces() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join("app")).unwrap();
        std::fs::write(dir.path().join("app/app.code-workspace"), "{}").unwrap();
        std::fs::create_dir_all(dir.path().join("lib")).unwrap();
        let vars: Table = format!("root = '{}'", dir.path().display())
            .parse()
            .unwrap();
        let sources = Sources {
            paths: vec!["{root}/*".into()],
        }
        .render(&vars)
        .unwrap();
        let ctx = Context {
            icons: Icons::new("/nonexistent"),
            populators: BTreeMap::new(),
        };
        let installed = Editor::installed().await.len();
        let items = sources.items(&ctx).await.unwrap();
        assert_eq!(items.len(), 2 * installed);
        if installed > 0 {
            assert_eq!(items[0].title, "app.code-workspace");
        }
    }
}
