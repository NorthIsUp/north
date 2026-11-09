//! Build a full menu: queue items, resolve their icons in parallel, cache the result.

use std::collections::{BTreeMap, HashMap};
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::OnceLock;
use std::thread;
use std::time::Duration;

use glob::{MatchOptions, Pattern};
use sha2::{Digest, Sha256};
use ureq::ResponseExt;
use url::{Position, Url};

use crate::cleanup::CacheCleanup;
use crate::editor::Editor;
use crate::fast::{self, home};
use crate::{Error, Icon, IconType, Menu, MenuCache, MenuItem, Modifier, Result};

const USER_AGENT: &str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";

/// Where an item's icon comes from.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IconSource {
    /// A file path; a pattern containing `*` matches case-insensitively in the icon cache.
    Path(String),
    /// A name from [`Workflow::glyphs`] rendered from SF Pro, or a path to an existing image.
    Glyph(String),
    /// An app name in `/Applications`, or a path to an `.icns`, converted to PNG.
    App(String),
    /// The Clearbit logo for a URL's domain.
    Clearbit(String),
    /// An image URL.
    Url(String),
    /// The favicon a page links to, falling back to `/favicon.ico`.
    Favicon(String),
    /// `./icons/<name>.png` inside the workflow bundle.
    Workflow(String),
    /// The icon for a UTI, e.g. `public.folder`.
    FileType(String),
    /// The icon of the file at this path.
    FileIcon(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum Kind {
    Easy { arg: String },
    Url { url: String },
    Exec { command: String },
}

/// A queued menu item. Unset fields get defaults when the workflow is built.
#[derive(Debug, Clone, PartialEq, Eq)]
#[must_use]
pub struct Item {
    kind: Kind,
    pub(crate) title: String,
    subtitle: Option<String>,
    icon: Option<IconSource>,
    uid: Option<String>,
    match_text: Option<String>,
    autocomplete: Option<String>,
    alt: Option<String>,
    cmd: Option<String>,
}

impl Item {
    fn new(kind: Kind, title: impl Into<String>) -> Self {
        Self {
            kind,
            title: title.into(),
            subtitle: None,
            icon: None,
            uid: None,
            match_text: None,
            autocomplete: None,
            alt: None,
            cmd: None,
        }
    }

    /// Passes `arg` to the workflow's next action.
    pub fn easy(
        title: impl Into<String>,
        subtitle: impl Into<String>,
        arg: impl Into<String>,
    ) -> Self {
        Self::new(Kind::Easy { arg: arg.into() }, title).subtitle(subtitle)
    }

    /// Opens `url` (upgraded to https); the icon defaults to the page's favicon.
    pub fn url(title: impl Into<String>, url: impl Into<String>) -> Self {
        Self::new(
            Kind::Url {
                url: url.into().replace("http://", "https://"),
            },
            title,
        )
    }

    /// Runs `command` through `zsh://`; the icon defaults to the terminal glyph.
    pub fn exec(title: impl Into<String>, command: impl Into<String>) -> Self {
        Self::new(
            Kind::Exec {
                command: command.into(),
            },
            title,
        )
    }

    pub fn subtitle(mut self, subtitle: impl Into<String>) -> Self {
        self.subtitle = Some(subtitle.into());
        self
    }

    pub fn icon(mut self, icon: IconSource) -> Self {
        self.icon = Some(icon);
        self
    }

    pub fn uid(mut self, uid: impl Into<String>) -> Self {
        self.uid = Some(uid.into());
        self
    }

    /// Text Alfred matches the query against, instead of the title.
    pub fn match_text(mut self, text: impl Into<String>) -> Self {
        self.match_text = Some(text.into());
        self
    }

    pub fn autocomplete(mut self, autocomplete: impl Into<String>) -> Self {
        self.autocomplete = Some(autocomplete.into());
        self
    }

    /// Subtitle shown while ⌥ is held.
    pub fn alt(mut self, subtitle: impl Into<String>) -> Self {
        self.alt = Some(subtitle.into());
        self
    }

    /// Subtitle shown while ⌘ is held.
    pub fn cmd(mut self, subtitle: impl Into<String>) -> Self {
        self.cmd = Some(subtitle.into());
        self
    }
}

/// An Alfred menu under construction.
#[derive(Debug)]
pub struct Workflow {
    /// Cache filename stem; see [`fast::cache_filename`].
    pub cache_name: Option<String>,
    /// How long Alfred may reuse the printed menu.
    pub cache_ttl: Duration,
    pub home: PathBuf,
    pub xdg_cache_home: PathBuf,
    pub icon_cache: PathBuf,
    pub menu_items: Vec<MenuItem>,
    /// Glyph names to SF Pro characters, rendered by [`IconSource::Glyph`].
    pub glyphs: BTreeMap<String, String>,
    pub(crate) pending: Vec<Item>,
    magick: OnceLock<bool>,
}

impl Default for Workflow {
    fn default() -> Self {
        let home = home();
        let glyphs = [
            ("terminal", '\u{100a7c}'),
            ("terminal-fill", '\u{100a8f}'),
            ("bookmark", '\u{10025e}'),
            ("path", '\u{100215}'),
            ("file", '\u{100237}'),
            ("maxcare", '\u{100d3f}'),
            ("sparkles", '\u{1001bf}'),
            ("monitor-sparkles", '\u{10114b}'),
            ("monitor-sparkles-fill", '\u{10114c}'),
            ("bubbles-sparkles", '\u{101489}'),
            ("bubbles-sparkles-fill", '\u{10148a}'),
            ("cloud", '\u{1001c2}'),
        ];
        Self {
            cache_name: None,
            cache_ttl: Duration::from_secs(3600),
            xdg_cache_home: home.join(".cache"),
            icon_cache: home.join(".cache/alfred-icons"),
            home,
            menu_items: Vec::new(),
            glyphs: glyphs
                .into_iter()
                .map(|(name, c)| (name.to_owned(), c.to_string()))
                .collect(),
            pending: Vec::new(),
            magick: OnceLock::new(),
        }
    }
}

impl Workflow {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_cache_name(name: impl Into<String>) -> Self {
        Self {
            cache_name: Some(name.into()),
            ..Self::default()
        }
    }

    /// Queue an item; its icon is resolved by [`Workflow::process_items`].
    pub fn add(&mut self, item: Item) {
        self.pending.push(item);
    }

    /// One item per source file and editor, opening the file in that editor.
    ///
    /// `None` uses every [installed](Editor::installed) editor.
    pub fn add_source_files<P: AsRef<Path>>(
        &mut self,
        sources: &[P],
        editors: Option<&[Editor]>,
    ) -> Result<()> {
        if sources.is_empty() {
            return Err(Error::NoSourceFiles);
        }
        let editors = editors.unwrap_or_else(|| Editor::installed());
        for source in sources {
            let source = source.as_ref();
            let name = source.file_name().unwrap_or_default().to_string_lossy();
            for editor in editors {
                let mut item = Item::easy(
                    name.as_ref(),
                    format!("{} {}", editor.short_name, source.display()),
                    editor.open_cmd(source),
                );
                if let Some(appicon) = &editor.appicon {
                    item = item.icon(IconSource::App(appicon.clone()));
                }
                self.add(item);
            }
        }
        Ok(())
    }

    /// A "clear cache" item removing this workflow's menu, icon, and Alfred caches.
    pub fn add_config_items(&mut self) -> Result<()> {
        let environment: HashMap<String, String> = std::env::vars().collect();
        let cleanup = CacheCleanup::from_environment(
            fast::cache_path(self.cache_name.as_deref())?,
            self.icon_cache.clone(),
            &self.home,
            &environment,
        );
        self.add(Item::exec("clear cache", cleanup.command()));
        Ok(())
    }

    /// One item per app name, opening it.
    pub fn add_dev_workflow(&mut self, apps: &[&str]) {
        for app in apps {
            self.add(Item::exec(*app, format!("open -a {app}")));
        }
    }

    /// Resolve every queued item, in parallel, appending them in queue order.
    pub fn process_items(&mut self) {
        let pending = std::mem::take(&mut self.pending);
        let resolved: Vec<MenuItem> = thread::scope(|scope| {
            let handles: Vec<_> = pending
                .into_iter()
                .map(|item| scope.spawn(|| self.resolve(item)))
                .collect();
            handles
                .into_iter()
                .map(|h| h.join().expect("icon resolution panicked"))
                .collect()
        });
        self.menu_items.extend(resolved);
    }

    /// Add the config items, process the queue, and write the cache.
    pub fn build(&mut self) -> Result<()> {
        self.add_config_items()?;
        self.process_items();
        self.write_cache()
    }

    pub fn menu(&self) -> Menu {
        Menu {
            cache: Some(MenuCache {
                seconds: self.cache_ttl.as_secs(),
                ..MenuCache::default()
            }),
            items: self.menu_items.clone(),
            ..Menu::default()
        }
    }

    pub fn print_menu(&self) {
        println!("{self}");
    }

    /// A workflow holding the cached menu; a malformed cache is deleted.
    pub fn read_cache(name: Option<&str>) -> Result<Option<Self>> {
        let path = fast::cache_path(name)?;
        let Ok(data) = fs::read(&path) else {
            return Ok(None);
        };
        match serde_json::from_slice::<Menu>(&data) {
            Ok(menu) => Ok(Some(Self {
                cache_name: name.map(str::to_owned),
                cache_ttl: Duration::from_secs(menu.cache.unwrap_or_default().seconds),
                menu_items: menu.items,
                ..Self::default()
            })),
            Err(_) => {
                fs::remove_file(&path)?;
                Ok(None)
            }
        }
    }

    pub fn write_cache(&self) -> Result<()> {
        let path = fast::cache_path(self.cache_name.as_deref())?;
        fast::atomic_write(&path, self.to_string().as_bytes())
    }

    fn resolve(&self, item: Item) -> MenuItem {
        let Item {
            kind,
            title,
            subtitle,
            icon,
            uid,
            match_text,
            autocomplete,
            alt,
            cmd,
        } = item;
        let (subtitle, arg, default_icon) = match kind {
            Kind::Easy { arg } => (subtitle.unwrap_or_default(), arg, None),
            Kind::Url { url } => (
                subtitle.unwrap_or_else(|| format!("open {title} in browser ({url})")),
                format!("open {url}"),
                Some(IconSource::Favicon(url)),
            ),
            Kind::Exec { command } => (
                subtitle.unwrap_or_else(|| command.clone()),
                format!("zsh://{command}"),
                Some(IconSource::Glyph("terminal".into())),
            ),
        };
        MenuItem {
            icon: icon
                .or(default_icon)
                .and_then(|source| self.resolve_icon(&source)),
            uid: uid.unwrap_or_else(|| generate_uid(&title, &subtitle, &arg)),
            match_text: match_text.unwrap_or_else(|| format!("{title} {subtitle} {arg}")),
            autocomplete: autocomplete.unwrap_or_else(|| arg.clone()),
            alt: alt.map(Modifier::from),
            cmd: cmd.map(Modifier::from),
            title,
            subtitle,
            arg,
            ..MenuItem::default()
        }
    }

    /// `None` when the icon can't be found or fetched; a missing icon never fails the menu.
    fn resolve_icon(&self, source: &IconSource) -> Option<Icon> {
        let path = |p: &Path| Some(Icon::path(p.display().to_string()));
        match source {
            IconSource::Path(pattern) if pattern.contains('*') => {
                let found = find_case_insensitive(&self.icon_cache, pattern)?;
                path(&std::path::absolute(found).ok()?)
            }
            IconSource::Path(value) => Some(Icon::path(value)),
            IconSource::Glyph(name) => match self.glyphs.get(name) {
                Some(symbol) => path(&self.sfsymbol(symbol)?),
                None if Path::new(name).exists() => Some(Icon::path(name)),
                None => {
                    log::warn!("glyph: {name:?} does not exist");
                    None
                }
            },
            IconSource::FileType(value) => Some(Icon {
                kind: Some(IconType::Filetype),
                path: value.clone(),
            }),
            IconSource::FileIcon(value) => Some(Icon {
                kind: Some(IconType::Fileicon),
                path: value.clone(),
            }),
            IconSource::Workflow(name) => Some(Icon::path(format!("./icons/{name}.png"))),
            IconSource::App(app) => {
                let (icns, png) = match app.strip_suffix(".icns") {
                    Some(_) => {
                        let stem = Path::new(app)
                            .file_stem()
                            .unwrap_or_default()
                            .to_string_lossy();
                        (
                            PathBuf::from(app),
                            self.icon_cache.join(format!("{stem}.png")),
                        )
                    }
                    None => (
                        PathBuf::from(format!(
                            "/Applications/{app}.app/Contents/Resources/{app}.icns"
                        )),
                        self.icon_cache.join(format!("{app}.png")),
                    ),
                };
                if png.exists() {
                    return path(&png);
                }
                if !icns.exists() {
                    return None;
                }
                fs::create_dir_all(&self.icon_cache).ok()?;
                let converted = Command::new("sips")
                    .args(["-s", "format", "png"])
                    .arg(&icns)
                    .arg("--out")
                    .arg(&png)
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .status()
                    .is_ok_and(|s| s.success());
                if converted { path(&png) } else { None }
            }
            IconSource::Clearbit(value) => {
                let domain = clearbit_domain(value);
                let url = format!("https://logo.clearbit.com/{domain}");
                download_icon(&url, &self.icon_cache.join(format!("{domain}.png")))
            }
            IconSource::Url(url) => download_icon(
                url,
                &self
                    .icon_cache
                    .join(format!("{}.png", url.replace('/', "_"))),
            ),
            IconSource::Favicon(page) => {
                let netloc = Url::parse(page)
                    .map(|u| u[Position::BeforeUsername..Position::AfterPort].to_owned())
                    .unwrap_or_default();
                let dir = self.icon_cache.join(netloc);
                if let Some(cached) =
                    find_case_insensitive(&dir, "favicon.*").filter(|p| is_usable(p))
                {
                    return path(&cached);
                }
                let (url, filename) = favicon_url(page)?;
                download_icon(&url, &dir.join(filename))
            }
        }
    }

    /// Render `symbol` from SF Pro to dark and light PNGs with ImageMagick; the dark one is returned.
    fn sfsymbol(&self, symbol: &str) -> Option<PathBuf> {
        let dir = self.xdg_cache_home.join("font-icons");
        let variant = |mode: &str| dir.join(format!("sf-pro-{symbol}-{mode}.png"));
        let dark = variant("dark");
        if !dark.exists() {
            if !self.has_magick() {
                return None;
            }
            fs::create_dir_all(&dir).ok()?;
            let font = self.home.join("Library/Fonts/SF-Pro.ttf");
            let renders: Vec<_> = [("black", dark.clone()), ("white", variant("light"))]
                .into_iter()
                .filter_map(|(fill, out)| {
                    Command::new("magick")
                        .args(["-background", "none", "-fill", fill, "-font"])
                        .arg(&font)
                        .args(["-pointsize", "300", &format!("label:{symbol}")])
                        .arg(out)
                        .spawn()
                        .ok()
                })
                .collect();
            for mut render in renders {
                let _ = render.wait();
            }
        }
        dark.exists().then_some(dark)
    }

    fn has_magick(&self) -> bool {
        *self.magick.get_or_init(|| {
            Command::new("which")
                .arg("magick")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
                .is_ok_and(|s| s.success())
        })
    }
}

impl fmt::Display for Workflow {
    /// The complete menu as pretty JSON.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let json = serde_json::to_string_pretty(&self.menu()).map_err(|_| fmt::Error)?;
        f.write_str(&json)
    }
}

/// SHA-256 of `"{title} {subtitle} {arg}"`, hex encoded.
pub fn generate_uid(title: &str, subtitle: &str, arg: &str) -> String {
    Sha256::digest(format!("{title} {subtitle} {arg}"))
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn find_case_insensitive(dir: &Path, pattern: &str) -> Option<PathBuf> {
    let pattern = Pattern::new(pattern).ok()?;
    let options = MatchOptions {
        case_sensitive: false,
        ..MatchOptions::new()
    };
    fs::read_dir(dir)
        .ok()?
        .flatten()
        .find(|entry| pattern.matches_with(&entry.file_name().to_string_lossy(), options))
        .map(|entry| entry.path())
}

fn clearbit_domain(value: &str) -> &str {
    let rest = value.rsplit("://").next().unwrap_or(value);
    let host = rest.split('/').next().unwrap_or(rest);
    host.split(':').next().unwrap_or(host)
}

/// Anything this small is an error page, not an icon.
fn is_usable(path: &Path) -> bool {
    fs::metadata(path).is_ok_and(|m| m.len() > 20)
}

fn agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .timeout_global(Some(Duration::from_secs(2)))
        .build()
        .into()
}

fn download_icon(url: &str, path: &Path) -> Option<Icon> {
    if !is_usable(path) {
        let fetch = || -> Result<()> {
            let bytes = agent()
                .get(url)
                .header("User-Agent", USER_AGENT)
                .call()?
                .body_mut()
                .read_to_vec()?;
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent)?;
            }
            fs::write(path, bytes)?;
            Ok(())
        };
        if let Err(e) = fetch() {
            log::debug!("icon download from {url} failed: {e}");
            return None;
        }
    }
    Some(Icon::path(path.display().to_string()))
}

/// The first `<link rel="…icon…">` on the page or its site root, else `/favicon.ico`.
fn favicon_url(page: &str) -> Option<(String, String)> {
    let page_url = Url::parse(page).ok()?;
    let agent = agent();
    for candidate in [page, &page_url[..Position::BeforePath]] {
        let mut response = agent.get(candidate).call().ok()?;
        let final_url =
            Url::parse(&response.get_uri().to_string()).unwrap_or_else(|_| page_url.clone());
        let html = response.body_mut().read_to_string().ok()?;
        if let Some(href) = icon_links(&html).into_iter().next() {
            let icon_url = final_url.join(&href).ok()?;
            let suffix = Path::new(icon_url.path())
                .extension()
                .map_or("ico".into(), |e| e.to_string_lossy().into_owned());
            return Some((icon_url.into(), format!("favicon.{suffix}")));
        }
    }
    Some((
        page_url.join("/favicon.ico").ok()?.into(),
        "favicon.ico".into(),
    ))
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

    fn workflow(dir: &Path) -> Workflow {
        Workflow {
            home: dir.into(),
            xdg_cache_home: dir.join(".cache"),
            icon_cache: dir.join("icons"),
            ..Workflow::default()
        }
    }

    #[test]
    fn items_get_defaults() {
        let dir = tempfile::tempdir().unwrap();
        let mut wf = workflow(dir.path());
        wf.glyphs.clear();
        wf.add(Item::exec("list", "ls -la").icon(IconSource::Workflow("ls".into())));
        wf.add(
            Item::url("Docs", "http://example.com")
                .icon(IconSource::FileType("public.html".into()))
                .alt("alt text"),
        );
        wf.add(
            Item::easy("Easy", "sub", "arg")
                .uid("fixed")
                .match_text("m")
                .autocomplete("auto"),
        );
        wf.process_items();
        let [exec, url, easy] = wf.menu_items.as_slice() else {
            panic!("{:?}", wf.menu_items)
        };

        assert_eq!(exec.arg, "zsh://ls -la");
        assert_eq!(exec.subtitle, "ls -la");
        assert_eq!(exec.uid, generate_uid("list", "ls -la", "zsh://ls -la"));
        assert_eq!(exec.match_text, "list ls -la zsh://ls -la");
        assert_eq!(exec.autocomplete, "zsh://ls -la");
        assert_eq!(exec.icon, Some(Icon::path("./icons/ls.png")));

        assert_eq!(url.arg, "open https://example.com");
        assert_eq!(url.subtitle, "open Docs in browser (https://example.com)");
        assert_eq!(
            url.icon,
            Some(Icon {
                kind: Some(IconType::Filetype),
                path: "public.html".into()
            })
        );
        assert_eq!(url.alt, Some(Modifier::from("alt text".to_owned())));

        assert_eq!(
            (
                easy.uid.as_str(),
                easy.match_text.as_str(),
                easy.autocomplete.as_str()
            ),
            ("fixed", "m", "auto")
        );
    }

    #[test]
    fn unknown_glyph_has_no_icon() {
        let dir = tempfile::tempdir().unwrap();
        let mut wf = workflow(dir.path());
        wf.glyphs.clear();
        wf.add(Item::exec("x", "true"));
        wf.process_items();
        assert_eq!(wf.menu_items[0].icon, None);
    }

    #[test]
    fn glob_icons_match_case_insensitively() {
        let dir = tempfile::tempdir().unwrap();
        let wf = workflow(dir.path());
        fs::create_dir_all(&wf.icon_cache).unwrap();
        fs::write(wf.icon_cache.join("Sentry.PNG"), "x").unwrap();
        let icon = wf
            .resolve_icon(&IconSource::Path("sentry.*".into()))
            .unwrap();
        assert!(icon.path.ends_with("icons/Sentry.PNG"), "{}", icon.path);
    }

    #[test]
    fn source_files_queue_editor_actions() {
        let dir = tempfile::tempdir().unwrap();
        let editor = Editor {
            name: "Example".into(),
            short_name: "example".into(),
            path: dir.path().into(),
            appicon: None,
        };
        let mut wf = workflow(dir.path());
        assert!(matches!(
            wf.add_source_files::<&Path>(&[], Some(&[])),
            Err(Error::NoSourceFiles)
        ));
        wf.add_source_files(
            &[dir.path().join("config.toml")],
            Some(std::slice::from_ref(&editor)),
        )
        .unwrap();
        wf.process_items();
        let item = &wf.menu_items[0];
        assert_eq!(item.title, "config.toml");
        assert_eq!(
            item.arg,
            format!(
                "open -a 'Example' {}",
                dir.path().join("config.toml").display()
            )
        );
    }

    #[test]
    fn menu_json_matches_python_shape() {
        let dir = tempfile::tempdir().unwrap();
        let mut wf = workflow(dir.path());
        wf.menu_items.push(MenuItem {
            title: "Ready".into(),
            ..MenuItem::default()
        });
        let json: serde_json::Value = serde_json::from_str(&wf.to_string()).unwrap();
        assert_eq!(
            json,
            serde_json::json!({"cache": {"seconds": 3600, "loosereload": true}, "items": [{"title": "Ready"}]})
        );
    }

    #[test]
    fn parses_icon_links_and_domains() {
        let html = r#"<html><head><link rel="stylesheet" href="a.css"><LINK REL="Shortcut Icon" href="/fav.png"></head></html>"#;
        assert_eq!(icon_links(html), ["/fav.png"]);
        assert_eq!(
            clearbit_domain("https://user.example.com:8443/path"),
            "user.example.com"
        );
        assert_eq!(clearbit_domain("example.com"), "example.com");
    }
}
