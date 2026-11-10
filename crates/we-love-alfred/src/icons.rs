//! Resolve [`IconSource`]s to files, downloading and rendering into an icon cache.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::LazyLock;
use std::time::Duration;

use futures_util::future::{self, BoxFuture, FutureExt};
use glob::{MatchOptions, Pattern};
use regex::Regex;
use reqwest::{Client, Url};
use serde::Deserialize;
use tokio::fs;
use tokio::process::Command;
use tokio::sync::OnceCell;

use crate::cache::{atomic_write, expand_home, home};
use crate::pack::{self, Entry};
use crate::{Icon, IconType};

const USER_AGENT: &str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";

/// Where an item's icon comes from. In TOML: `icon = { clearbit = "github.com" }`,
/// or a list tried in order: `icon = [{ path = "./a.png" }, { glyph = "cloud" }]`.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum IconSource {
    /// An existing file; with `*`, the first case-insensitive match in that directory.
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
    /// `<pack>/<file glob>` from a configured [`IconPack`], fetched alone and cached.
    Pack(String),
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
            Self::Pack(s) => Self::Pack(f(s)?),
            Self::FirstOf(all) => {
                Self::FirstOf(all.iter().map(|s| s.try_map(f)).collect::<Result<_, _>>()?)
            }
        })
    }
}

/// A remote ZIP of icons, read lazily: [`IconSource::Pack`] fetches the archive's index once,
/// then only the bytes of each icon used. The host must support HTTP range requests.
///
/// ```toml
/// [icon_packs.gcp]
/// url = "https://services.google.com/fh/files/misc/google-cloud-legacy-icons.zip"
/// ```
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IconPack {
    pub url: String,
}

struct Pack {
    url: String,
    index: OnceCell<Option<Vec<Entry>>>,
}

impl std::fmt::Debug for Pack {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.url)
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
    packs: BTreeMap<String, Pack>,
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
            packs: BTreeMap::new(),
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
                IconSource::Path(path) => {
                    let path = expand_home(path);
                    if fs::try_exists(&path).await.unwrap_or(false) {
                        found(&path)
                    } else {
                        None
                    }
                }
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
                IconSource::Pack(spec) => found(&self.pack_icon(spec).await?),
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
                    self.favicon(page, &dir).await
                }
            }
        }
        .boxed()
    }

    /// Icon packs [`IconSource::Pack`] can name.
    #[must_use]
    pub fn with_packs(mut self, packs: impl IntoIterator<Item = (String, IconPack)>) -> Self {
        self.packs.extend(packs.into_iter().map(|(name, pack)| {
            (
                name,
                Pack {
                    url: pack.url,
                    index: OnceCell::new(),
                },
            )
        }));
        self
    }

    /// `<pack>/<file glob>`: a cached copy, else the first matching archive entry, fetched alone.
    async fn pack_icon(&self, spec: &str) -> Option<PathBuf> {
        let (name, file) = spec.split_once('/')?;
        let dir = self.dir.join("packs").join(name);
        if let Some(cached) = find_case_insensitive(&dir, file).await {
            return Some(cached);
        }
        let pack = self.packs.get(name).or_else(|| {
            log::warn!("icon pack {name:?} is not configured");
            None
        })?;
        let entries = pack
            .index
            .get_or_init(|| self.pack_index(name, &pack.url))
            .await
            .as_ref()?;
        let pattern = Pattern::new(file).ok()?;
        let options = MatchOptions {
            case_sensitive: false,
            ..MatchOptions::new()
        };
        // macOS-made archives carry resource forks under __MACOSX/.
        let entry = entries
            .iter()
            .filter(|e| !e.name.starts_with("__MACOSX/"))
            .find(|e| {
                let base = e.name.rsplit('/').next().unwrap_or(&e.name);
                pattern.matches_with(base, options)
            })?;
        let bytes = pack::fetch(&self.client, &pack.url, entry)
            .await
            .map_err(|e| log::warn!("icon pack {name}: {e}"))
            .ok()?;
        let path = dir.join(entry.name.rsplit('/').next()?);
        atomic_write(&path, &bytes).await.ok()?;
        Some(path)
    }

    /// The pack's index from disk when it's for the same URL, else from the archive.
    async fn pack_index(&self, name: &str, url: &str) -> Option<Vec<Entry>> {
        #[derive(serde::Serialize, Deserialize)]
        struct Cached {
            url: String,
            entries: Vec<Entry>,
        }
        let path = self.dir.join("packs").join(format!("{name}.index.json"));
        if let Ok(raw) = fs::read(&path).await
            && let Ok(cached) = serde_json::from_slice::<Cached>(&raw)
            && cached.url == url
        {
            return Some(cached.entries);
        }
        let entries = pack::index(&self.client, url)
            .await
            .map_err(|e| log::warn!("icon pack {name}: {e}"))
            .ok()?;
        let cached = Cached {
            url: url.to_owned(),
            entries,
        };
        if let Ok(json) = serde_json::to_vec(&cached) {
            let _ = atomic_write(&path, &json).await;
        }
        Some(cached.entries)
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

    /// The largest icon the page (or its site root) declares that downloads, else `/favicon.ico`
    /// on the host the page redirected to.
    async fn favicon(&self, page: Url, dir: &Path) -> Option<Icon> {
        let mut base = page.clone();
        for candidate in [page.clone(), page.join("/").ok()?] {
            let response = self
                .client
                .get(candidate)
                .send()
                .await
                .ok()
                .and_then(|r| r.error_for_status().ok());
            let Some(response) = response else { continue };
            base = response.url().clone();
            let Ok(html) = response.text().await else {
                continue;
            };
            for href in icon_links(&html) {
                let Ok(url) = base.join(&href) else { continue };
                let ext = Path::new(url.path())
                    .extension()
                    .map_or("ico".into(), |e| e.to_string_lossy().to_lowercase());
                if let Some(icon) = self
                    .download(url.as_str(), &dir.join(format!("favicon.{ext}")))
                    .await
                {
                    return Some(icon);
                }
            }
        }
        self.download(
            base.join("/favicon.ico").ok()?.as_str(),
            &dir.join("favicon.ico"),
        )
        .await
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

/// Icon hrefs a page declares, largest first: `<link rel>` icons and `msapplication-TileImage`
/// by their `sizes` or a `WxH` in the filename, then `og:image` (usually a banner, not an icon).
/// Skips `mask-icon` (a one-colour Safari SVG) and inline `data:` images.
fn icon_links(html: &str) -> Vec<String> {
    const RELS: [&str; 3] = ["icon", "apple-touch-icon", "apple-touch-icon-precomposed"];
    let Ok(dom) = tl::parse(html, tl::ParserOptions::default()) else {
        return Vec::new();
    };
    // HTML attribute names are case-insensitive; `Attributes::get` is not.
    let attr = |tag: &tl::HTMLTag, name: &str| {
        tag.attributes()
            .iter()
            .find(|(key, _)| key.eq_ignore_ascii_case(name))
            .and_then(|(_, value)| value)
            .map(|value| value.trim().to_owned())
            .unwrap_or_default()
    };
    let mut found: Vec<(bool, u32, String)> = dom
        .nodes()
        .iter()
        .filter_map(|node| node.as_tag())
        .filter_map(|tag| {
            let (banner, href) = match tag.name().as_utf8_str().to_lowercase().as_str() {
                "link"
                    if attr(tag, "rel")
                        .to_lowercase()
                        .split_whitespace()
                        .any(|r| RELS.contains(&r)) =>
                {
                    (false, attr(tag, "href"))
                }
                "meta" => match attr(tag, "name").to_lowercase().as_str() {
                    "msapplication-tileimage" => (false, attr(tag, "content")),
                    _ if attr(tag, "property").eq_ignore_ascii_case("og:image") => {
                        (true, attr(tag, "content"))
                    }
                    _ => return None,
                },
                _ => return None,
            };
            if href.is_empty() || href.to_lowercase().starts_with("data:") {
                return None;
            }
            Some((banner, icon_size(&attr(tag, "sizes"), &href), href))
        })
        .collect();
    found.sort_by_key(|(banner, size, _)| (*banner, std::cmp::Reverse(*size)));
    found.into_iter().map(|(_, _, href)| href).collect()
}

/// The largest side named by `sizes` (`16x16 32x32`, `192×192`, sloppy `192x192+`), else by a
/// `WxH` in the filename; 0 when unknown, including `sizes="any"`.
fn icon_size(sizes: &str, href: &str) -> u32 {
    static IN_NAME: LazyLock<Regex> =
        LazyLock::new(|| Regex::new(r"(?i)(\d{2,4})[x×](\d{2,4})").expect("valid regex"));
    let side = |n: &str| {
        n.chars()
            .filter(char::is_ascii_digit)
            .collect::<String>()
            .parse::<u32>()
            .unwrap_or(0)
    };
    let declared = sizes
        .split_whitespace()
        .filter_map(|size| {
            size.to_lowercase()
                .split_once(['x', '×'])
                .map(|(w, h)| side(w).max(side(h)))
        })
        .max();
    declared
        .or_else(|| IN_NAME.captures(href).map(|c| side(&c[1]).max(side(&c[2]))))
        .unwrap_or(0)
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
    async fn pack_icons_fetch_one_entry_and_cache_it() {
        let (url, ranges) = crate::pack::tests::range_server(crate::pack::tests::archive());
        let dir = tempfile::tempdir().unwrap();
        let icons = Icons::new(dir.path()).with_packs([("aws".to_owned(), IconPack { url })]);
        let source = IconSource::Pack("aws/arch_amazon-rds_64.png".into());
        let icon = icons.resolve(&source).await.unwrap();
        assert!(
            icon.path.ends_with("packs/aws/Arch_Amazon-RDS_64.png"),
            "{}",
            icon.path
        );
        assert_eq!(std::fs::read(&icon.path).unwrap(), b"rds rds rds rds rds");
        let requests = ranges.lock().unwrap().len();
        assert_eq!(
            icons.resolve(&source).await,
            Some(icon),
            "served from the cache"
        );
        assert_eq!(ranges.lock().unwrap().len(), requests, "no new requests");
        let fresh = Icons::new(dir.path()).with_packs([(
            "aws".to_owned(),
            IconPack {
                url: "http://127.0.0.1:9/x.zip".into(),
            },
        )]);
        assert!(
            fresh
                .resolve(&IconSource::Pack("aws/bigquery.png".into()))
                .await
                .is_none(),
            "index cached per URL"
        );
        assert!(
            icons
                .resolve(&IconSource::Pack("aws/bigquery.png".into()))
                .await
                .is_some(),
            "index reused from disk"
        );
        assert!(
            icons
                .resolve(&IconSource::Pack("gcp/x.png".into()))
                .await
                .is_none(),
            "unknown pack"
        );
    }

    #[tokio::test]
    async fn missing_paths_fall_through() {
        let icons = Icons::new("/nonexistent");
        let source = IconSource::FirstOf(vec![
            IconSource::Path("/nonexistent/a.png".into()),
            IconSource::FileType("public.folder".into()),
        ]);
        assert_eq!(icons.resolve(&source).await.unwrap().path, "public.folder");
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
        let html = r#"
            <link rel="stylesheet" href="a.css">
            <link rel="mask-icon" href="/pinned.svg">
            <link rel="icon" href="data:image/png;base64,AAAA">
            <meta property="og:image" content="/social-1200x630.png">
            <LINK REL="Shortcut Icon" href=" /favicon-16x16.png ">
            <link rel="apple-touch-icon" sizes="192x192+" href="/touch.png">
            <link rel="icon" sizes="16x16 32x32" href="/multi.ico">
            <meta name="msapplication-TileImage" content="/tile-144x144.png">
            <link rel="icon" sizes="any" href="/icon.svg">"#;
        assert_eq!(
            icon_links(html),
            [
                "/touch.png",
                "/tile-144x144.png",
                "/multi.ico",
                "/favicon-16x16.png",
                "/icon.svg",
                "/social-1200x630.png"
            ]
        );
        assert_eq!(icon_size("180×180", "x"), 180);
        assert_eq!(icon_size("", "apple-touch-icon-57x57.png"), 57);
        assert_eq!(
            clearbit_domain("https://user.example.com:8443/path"),
            "user.example.com"
        );
    }
}
