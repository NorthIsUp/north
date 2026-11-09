//! Installed code editors that can open a workflow's source files.

use std::path::{Path, PathBuf};
use std::sync::OnceLock;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Editor {
    pub name: String,
    pub short_name: String,
    pub path: PathBuf,
    /// An app name or `.icns` path for [`crate::IconSource::App`].
    pub appicon: Option<String>,
}

impl Editor {
    fn known(name: &str, short_name: &str, appicon: &str) -> Self {
        Self {
            name: name.into(),
            short_name: short_name.into(),
            path: PathBuf::from(format!("/Applications/{name}.app")),
            appicon: Some(appicon.into()),
        }
    }

    pub fn exists(&self) -> bool {
        self.path.exists()
    }

    pub fn open_cmd(&self, path: &Path) -> String {
        format!("open -a '{}' {}", self.name, path.display())
    }

    /// Installed editors, discovered once per process.
    pub fn installed() -> &'static [Editor] {
        static INSTALLED: OnceLock<Vec<Editor>> = OnceLock::new();
        INSTALLED.get_or_init(|| {
            let icns = |app: &str, icon: &str| {
                format!("/Applications/{app}.app/Contents/Resources/{icon}.icns")
            };
            [
                Editor::known("Cursor", "cursor", "Cursor"),
                Editor::known(
                    "Visual Studio Code - Insiders",
                    "code-insiders",
                    &icns("Visual Studio Code - Insiders", "Code - Insiders"),
                ),
                Editor::known(
                    "Visual Studio Code",
                    "code",
                    &icns("Visual Studio Code", "Code"),
                ),
                Editor::known("Xcode", "xcode", &icns("Xcode", "Xcode")),
                Editor::known("TextEdit", "textedit", &icns("TextEdit", "TextEdit")),
            ]
            .into_iter()
            // The Python package sorted by priority with reverse=True; keep its menu order.
            .rev()
            .filter(Editor::exists)
            .collect()
        })
    }
}
