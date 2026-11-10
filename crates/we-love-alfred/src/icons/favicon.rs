//! A page's best icon, chosen the way the `favicon` library does.

use std::path::Path;
use std::sync::LazyLock;

use regex::Regex;
use reqwest::Url;

use super::Icons;
use crate::Icon;

impl Icons {
    /// The largest icon the page (or its site root) declares that downloads, else `/favicon.ico`
    /// on the host the page redirected to.
    pub(super) async fn favicon(&self, page: Url, dir: &Path) -> Option<Icon> {
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

    #[test]
    fn ranks_icon_links_like_the_favicon_library() {
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
    }
}
