//! Installed code editors that open source folders and files.

use std::path::{Path, PathBuf};

use futures_util::future;
use tokio::fs;
use tokio::sync::OnceCell;

use crate::shell::quote;
use crate::{IconSource, Item, ItemBuilder};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Editor {
    pub name: String,
    pub short_name: String,
    pub path: PathBuf,
    /// An app name or `.icns` path for [`IconSource::App`].
    pub appicon: Option<String>,
}

impl Editor {
    fn known(name: &str, short_name: &str, icns: Option<&str>) -> Self {
        let appicon = match icns {
            Some(icon) => format!("/Applications/{name}.app/Contents/Resources/{icon}.icns"),
            None => name.to_owned(),
        };
        Self {
            name: name.into(),
            short_name: short_name.into(),
            path: PathBuf::from(format!("/Applications/{name}.app")),
            appicon: Some(appicon),
        }
    }

    #[must_use]
    pub fn open_cmd(&self, path: &Path) -> String {
        format!(
            "open -a {} {}",
            quote(&self.name),
            quote(&path.to_string_lossy())
        )
    }

    /// An item opening `path` in this editor.
    pub fn open(&self, path: &Path) -> ItemBuilder {
        let name = path.file_name().unwrap_or_default().to_string_lossy();
        let item = Item::arg(name.as_ref(), self.open_cmd(path)).subtitle(format!(
            "{} {}",
            self.short_name,
            path.display()
        ));
        match &self.appicon {
            Some(icon) => item.icon(IconSource::App(icon.clone())),
            None => item,
        }
    }

    /// Installed editors in priority order (Cursor first), checked concurrently once per process.
    pub async fn installed() -> &'static [Editor] {
        static INSTALLED: OnceCell<Vec<Editor>> = OnceCell::const_new();
        INSTALLED
            .get_or_init(|| async {
                let known = [
                    Editor::known("Cursor", "cursor", None),
                    Editor::known(
                        "Visual Studio Code - Insiders",
                        "code-insiders",
                        Some("Code - Insiders"),
                    ),
                    Editor::known("Visual Studio Code", "code", Some("Code")),
                    Editor::known("Xcode", "xcode", Some("Xcode")),
                    Editor::known("TextEdit", "textedit", Some("TextEdit")),
                ];
                let installed =
                    future::join_all(known.iter().map(|e| fs::try_exists(&e.path))).await;
                known
                    .into_iter()
                    .zip(installed)
                    .filter(|(_, ok)| matches!(ok, Ok(true)))
                    .map(|(e, _)| e)
                    .collect()
            })
            .await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn open_cmd_quotes_name_and_path() {
        let editor = Editor::known("Visual Studio Code", "code", Some("Code"));
        assert_eq!(
            editor.open_cmd(Path::new("/tmp/my project/a.rs")),
            "open -a 'Visual Studio Code' '/tmp/my project/a.rs'"
        );
    }
}
