//! SF Pro glyphs rendered to PNG with ImageMagick.

use std::path::PathBuf;

use futures_util::future;
use tokio::fs;
use tokio::process::Command;

use super::{Icons, quiet};

impl Icons {
    /// Render `symbol` from SF Pro to dark and light PNGs concurrently; the dark one is returned.
    pub(super) async fn sfsymbol(&self, symbol: &str) -> Option<PathBuf> {
        let variant = |mode: &str| self.glyph_dir.join(format!("sf-pro-{symbol}-{mode}.png"));
        let dark = variant("dark");
        if !fs::try_exists(&dark).await.unwrap_or(false) {
            if !self.has_magick().await {
                return None;
            }
            fs::create_dir_all(&self.glyph_dir).await.ok()?;
            let render = |fill: &'static str, out: PathBuf| {
                let mut command = Command::new("magick");
                command
                    .args(["-background", "none", "-fill", fill, "-font"])
                    .arg(&self.font)
                    .args(["-pointsize", "300", &format!("label:{symbol}")])
                    .arg(out);
                async move { quiet(&mut command).status().await }
            };
            let _ = future::join(
                render("black", dark.clone()),
                render("white", variant("light")),
            )
            .await;
        }
        fs::try_exists(&dark).await.unwrap_or(false).then_some(dark)
    }

    async fn has_magick(&self) -> bool {
        *self
            .magick
            .get_or_init(|| async {
                quiet(Command::new("which").arg("magick"))
                    .status()
                    .await
                    .is_ok_and(|s| s.success())
            })
            .await
    }
}
