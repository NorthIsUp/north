//! Resolve [`IconSource`]s to files, downloading and rendering into an icon cache.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;

use futures_util::future::{self, BoxFuture, FutureExt};
use glob::{MatchOptions, Pattern};
use reqwest::{Client, Url};
use serde::Deserialize;
use tokio::fs;
use tokio::process::Command;
use tokio::sync::OnceCell;

use crate::cache::{expand_home, home};
use crate::{Icon, IconType};

const USER_AGENT: &str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";

/// Where an item's icon comes from. In TOML: `icon = { clearbit = "github.com" }`,
/// or a list tried in order: `icon = [{ path = "./a.png" }, { glyph = "cloud" }]`.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum IconSource {
    /// A file path; with `*`, the first case-insensitive match in that directory.
    Path(String),
    /// A name from [`Icons::glyphs`] rendered from SF Pro, or a path to an existing image.
    Glyph(String),
    /// An app name in `/Applications`, or a path to an `.icns`, converted to PNG.
    App(String),
    /// The Clearbit logo for a URL's domain.
    Clearbit(String),
    /// An image URL.
    Url(String),
    /// The favicon a page links to, falling back to `/favicon.ico`.
    Favicon(String),
    /// The icon for a UTI, e.g. `public.folder`.
    FileType(String),
    /// The icon of the file at this path.
    FileIcon(String),
    /// The first source that resolves.
    #[serde(skip)]
    FirstOf(Vec<IconSource>),
}

impl IconSource {
    /// Apply `f` to every string in the source.
    pub(crate) fn try_map<E>(&self, f: &impl Fn(&str) -> Result<String, E>) -> Result<Self, E> {
        Ok(match self {
            Self::Path(s) => Self::Path(f(s)?),
            Self::Glyph(s) => Self::Glyph(f(s)?),
            Self::App(s) => Self::App(f(s)?),
            Self::Clearbit(s) => Self::Clearbit(f(s)?),
            Self::Url(s) => Self::Url(f(s)?),
            Self::Favicon(s) => Self::Favicon(f(s)?),
            Self::FileType(s) => Self::FileType(f(s)?),
            Self::FileIcon(s) => Self::FileIcon(f(s)?),
            Self::FirstOf(all) => {
                Self::FirstOf(all.iter().map(|s| s.try_map(f)).collect::<Result<_, _>>()?)
            }
        })
    }
}

/// Icon cache and fetch settings, shared by every item in a build.
#[derive(Debug)]
pub struct Icons {
    pub dir: PathBuf,
    /// Where rendered SF Pro glyphs go.
    pub glyph_dir: PathBuf,
    pub font: PathBuf,
    /// Glyph names to SF Pro characters.
    pub glyphs: BTreeMap<String, String>,
    client: Client,
    magick: OnceCell<bool>,
}

impl Default for Icons {
    fn default() -> Self {
        let home = home();
        let glyphs = [
            ("terminal", '\u{100a7c}'),
            ("terminal-fill", '\u{100a8f}'),
            ("bookmark", '\u{10025e}'),
            ("path", '\u{100215}'),
            ("file", '\u{100237}'),
            ("sparkles", '\u{1001bf}'),
            ("monitor-sparkles", '\u{10114b}'),
            ("monitor-sparkles-fill", '\u{10114c}'),
            ("bubbles-sparkles", '\u{101489}'),
            ("bubbles-sparkles-fill", '\u{10148a}'),
            ("cloud", '\u{1001c2}'),
        ];
        Self::new(home.join(".cache/alfred-icons"))
            .with_glyph_dir(home.join(".cache/font-icons"))
            .with_glyphs(
                glyphs
                    .into_iter()
                    .map(|(name, c)| (name.to_owned(), c.to_string())),
            )
    }
}

impl Icons {
    pub fn new(dir: impl Into<PathBuf>) -> Self {
        let client = Client::builder()
            .user_agent(USER_AGENT)
            .timeout(Duration::from_secs(2))
            .build()
            .expect("static client config is valid");
        let dir = dir.into();
        Self {
            glyph_dir: dir.join("glyphs"),
            font: home().join("Library/Fonts/SF-Pro.ttf"),
            glyphs: BTreeMap::new(),
            dir,
            client,
            magick: OnceCell::new(),
        }
    }

    #[must_use]
    pub fn with_glyph_dir(mut self, dir: impl Into<PathBuf>) -> Self {
        self.glyph_dir = dir.into();
        self
    }

    #[must_use]
    pub fn with_glyphs(mut self, glyphs: impl IntoIterator<Item = (String, String)>) -> Self {
        self.glyphs.extend(glyphs);
        self
    }

    /// `None` when the icon can't be found or fetched; a missing icon never fails a menu.
    pub fn resolve<'a>(&'a self, source: &'a IconSource) -> BoxFuture<'a, Option<Icon>> {
        async move {
            let found = |p: &Path| Some(Icon::path(p.display().to_string()));
            match source {
                IconSource::FirstOf(sources) => {
                    for source in sources {
                        if let Some(icon) = self.resolve(source).await {
                            return Some(icon);
                        }
                    }
                    None
                }
                IconSource::Path(pattern) if pattern.contains('*') => {
                    let pattern = expand_home(pattern);
                    let dir = pattern
                        .parent()
                        .filter(|p| !p.as_os_str().is_empty())
                        .unwrap_or(Path::new("."));
                    let name = pattern.file_name()?.to_string_lossy();
                    found(&std::path::absolute(find_case_insensitive(dir, &name).await?).ok()?)
                }
                IconSource::Path(path) => found(&expand_home(path)),
                IconSource::Glyph(name) => match self.glyphs.get(name) {
                    Some(symbol) => found(&self.sfsymbol(symbol).await?),
                    None if fs::try_exists(name).await.unwrap_or(false) => Some(Icon::path(name)),
                    None => {
                        log::warn!("glyph {name:?} does not exist");
                        None
                    }
                },
                IconSource::FileType(uti) => Some(Icon {
                    kind: Some(IconType::Filetype),
                    path: uti.clone(),
                }),
                IconSource::FileIcon(path) => Some(Icon {
                    kind: Some(IconType::Fileicon),
                    path: path.clone(),
                }),
                IconSource::App(app) => found(&self.app_icon(app).await?),
                IconSource::Clearbit(value) => {
                    let domain = clearbit_domain(value);
                    self.download(
                        &format!("https://logo.clearbit.com/{domain}"),
                        &self.dir.join(format!("{domain}.png")),
                    )
                    .await
                }
                IconSource::Url(url) => {
                    self.download(
                        url,
                        &self.dir.join(format!("{}.png", url.replace('/', "_"))),
                    )
                    .await
                }
                IconSource::Favicon(page) => {
                    let page = Url::parse(page).ok()?;
                    let port = page.port().map(|p| format!(":{p}")).unwrap_or_default();
                    let dir = self.dir.join(format!("{}{port}", page.host_str()?));
                    if let Some(cached) = find_case_insensitive(&dir, "favicon.*").await
                        && is_usable(&cached).await
                    {
                        return found(&cached);
                    }
                    let (url, filename) = self.favicon_url(page).await?;
                    self.download(url.as_str(), &dir.join(filename)).await
                }
            }
        }
        .boxed()
    }

    async fn app_icon(&self, app: &str) -> Option<PathBuf> {
        let (icns, png) = match app.strip_suffix(".icns") {
            Some(_) => {
                let stem = Path::new(app).file_stem()?.to_string_lossy();
                (PathBuf::from(app), self.dir.join(format!("{stem}.png")))
            }
            None => (
                PathBuf::from(format!(
                    "/Applications/{app}.app/Contents/Resources/{app}.icns"
                )),
                self.dir.join(format!("{app}.png")),
            ),
        };
        if fs::try_exists(&png).await.unwrap_or(false) {
            return Some(png);
        }
        if !fs::try_exists(&icns).await.unwrap_or(false) {
            return None;
        }
        fs::create_dir_all(&self.dir).await.ok()?;
        let converted = quiet(
            Command::new("sips")
                .args(["-s", "format", "png"])
                .arg(&icns)
                .arg("--out")
                .arg(&png),
        )
        .status()
        .await
        .is_ok_and(|s| s.success());
        converted.then_some(png)
    }

    /// Render `symbol` from SF Pro to dark and light PNGs concurrently; the dark one is returned.
    async fn sfsymbol(&self, symbol: &str) -> Option<PathBuf> {
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

    async fn download(&self, url: &str, path: &Path) -> Option<Icon> {
        if !is_usable(path).await {
            let fetch = async {
                let bytes = self
                    .client
                    .get(url)
                    .send()
                    .await?
                    .error_for_status()?
                    .bytes()
                    .await?;
                if let Some(parent) = path.parent() {
                    fs::create_dir_all(parent).await?;
                }
                fs::write(path, bytes).await?;
                Ok::<_, crate::Error>(())
            };
            if let Err(e) = fetch.await {
                log::debug!("icon download from {url} failed: {e}");
                return None;
            }
        }
        Some(Icon::path(path.display().to_string()))
    }

    /// The first `<link rel="…icon…">` on the page or its site root, else `/favicon.ico`.
    async fn favicon_url(&self, page: Url) -> Option<(Url, String)> {
        let root = page.join("/").ok()?;
        for candidate in [page.clone(), root] {
            let response = self
                .client
                .get(candidate)
                .send()
                .await
                .ok()?
                .error_for_status()
                .ok()?;
            let final_url = response.url().clone();
            let html = response.text().await.ok()?;
            if let Some(href) = icon_links(&html).into_iter().next() {
                let icon = final_url.join(&href).ok()?;
                let suffix = Path::new(icon.path())
                    .extension()
                    .map_or("ico".into(), |e| e.to_string_lossy().into_owned());
                return Some((icon, format!("favicon.{suffix}")));
            }
        }
        Some((page.join("/favicon.ico").ok()?, "favicon.ico".into()))
    }
}

fn quiet(command: &mut Command) -> &mut Command {
    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
}

async fn find_case_insensitive(dir: &Path, pattern: &str) -> Option<PathBuf> {
    let pattern = Pattern::new(pattern).ok()?;
    let options = MatchOptions {
        case_sensitive: false,
        ..MatchOptions::new()
    };
    let mut entries = fs::read_dir(dir).await.ok()?;
    while let Ok(Some(entry)) = entries.next_entry().await {
        if pattern.matches_with(&entry.file_name().to_string_lossy(), options) {
            return Some(entry.path());
        }
    }
    None
}

fn clearbit_domain(value: &str) -> &str {
    let rest = value.rsplit("://").next().unwrap_or(value);
    let host = rest.split('/').next().unwrap_or(rest);
    host.split(':').next().unwrap_or(host)
}

/// Anything this small is an error page, not an icon.
async fn is_usable(path: &Path) -> bool {
    fs::metadata(path).await.is_ok_and(|m| m.len() > 20)
}

fn icon_links(html: &str) -> Vec<String> {
    let Ok(dom) = tl::parse(html, tl::ParserOptions::default()) else {
        return Vec::new();
    };
    // HTML attribute names are case-insensitive; `Attributes::get` is not.
    let attr = |tag: &tl::HTMLTag, name: &str| {
        tag.attributes()
            .iter()
            .find(|(key, _)| key.eq_ignore_ascii_case(name))
            .and_then(|(_, value)| value)
            .map(|value| value.into_owned())
            .unwrap_or_default()
    };
    dom.nodes()
        .iter()
        .filter_map(|node| node.as_tag())
        .filter(|tag| tag.name().as_utf8_str().eq_ignore_ascii_case("link"))
        .filter(|tag| attr(tag, "rel").to_lowercase().contains("icon"))
        .map(|tag| attr(tag, "href"))
        .filter(|href| !href.is_empty())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn first_of_falls_through_to_a_match() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("Arch_Amazon-S3.PNG"), "x").unwrap();
        let icons = Icons::new(dir.path());
        let source = IconSource::FirstOf(vec![
            IconSource::Path(format!("{}/*nothing*", dir.path().display())),
            IconSource::Glyph("unknown".into()),
            IconSource::Path(format!("{}/arch_*s3*", dir.path().display())),
        ]);
        let icon = icons.resolve(&source).await.unwrap();
        assert!(icon.path.ends_with("Arch_Amazon-S3.PNG"), "{}", icon.path);
    }

    #[tokio::test]
    async fn uti_and_file_icons_need_no_io() {
        let icons = Icons::new("/nonexistent");
        let icon = icons
            .resolve(&IconSource::FileType("public.folder".into()))
            .await;
        assert_eq!(
            icon,
            Some(Icon {
                kind: Some(IconType::Filetype),
                path: "public.folder".into()
            })
        );
    }

    #[test]
    fn parses_icon_links_and_domains() {
        let html =
            r#"<link rel="stylesheet" href="a.css"><LINK REL="Shortcut Icon" href="/fav.png">"#;
        assert_eq!(icon_links(html), ["/fav.png"]);
        assert_eq!(
            clearbit_domain("https://user.example.com:8443/path"),
            "user.example.com"
        );
    }
}
