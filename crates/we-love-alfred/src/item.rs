use futures_util::future;
use sha2::{Digest, Sha256};

use crate::{IconSource, Icons, Item, Menu, MenuCache, Modifier};

#[derive(Debug, Clone, PartialEq, Eq)]
enum Action {
    Arg(String),
    Url(String),
    Exec(String),
}

/// An item whose icon hasn't been resolved yet. Unset fields get defaults when built:
/// `uid` hashes title, subtitle and arg; `match` joins them; `autocomplete` is the arg.
#[derive(Debug, Clone, PartialEq, Eq)]
#[must_use]
pub struct ItemBuilder {
    action: Action,
    pub(crate) title: String,
    subtitle: Option<String>,
    icon: Option<IconSource>,
    uid: Option<String>,
    match_text: Option<String>,
    autocomplete: Option<String>,
    mods: Vec<(String, String)>,
}

impl Item {
    /// Passes `arg` to the workflow's next action.
    pub fn arg(title: impl Into<String>, arg: impl Into<String>) -> ItemBuilder {
        ItemBuilder::new(Action::Arg(arg.into()), title)
    }

    /// Opens `url` (upgraded to https); the icon defaults to the page's favicon.
    pub fn url(title: impl Into<String>, url: impl Into<String>) -> ItemBuilder {
        ItemBuilder::new(
            Action::Url(url.into().replace("http://", "https://")),
            title,
        )
    }

    /// Runs `command` through `zsh://`; the icon defaults to the terminal glyph.
    pub fn exec(title: impl Into<String>, command: impl Into<String>) -> ItemBuilder {
        ItemBuilder::new(Action::Exec(command.into()), title)
    }
}

impl ItemBuilder {
    fn new(action: Action, title: impl Into<String>) -> Self {
        Self {
            action,
            title: title.into(),
            subtitle: None,
            icon: None,
            uid: None,
            match_text: None,
            autocomplete: None,
            mods: Vec::new(),
        }
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

    /// Text the query is matched against instead of the title.
    pub fn match_text(mut self, text: impl Into<String>) -> Self {
        self.match_text = Some(text.into());
        self
    }

    pub fn autocomplete(mut self, autocomplete: impl Into<String>) -> Self {
        self.autocomplete = Some(autocomplete.into());
        self
    }

    /// Subtitle while `modifier` (`alt`, `cmd`, `cmd+alt`, …) is held.
    pub fn modifier(mut self, modifier: impl Into<String>, subtitle: impl Into<String>) -> Self {
        self.mods.push((modifier.into(), subtitle.into()));
        self
    }

    /// Resolve the icon and fill in defaults.
    pub async fn build(self, icons: &Icons) -> Item {
        let Self {
            action,
            title,
            subtitle,
            icon,
            uid,
            match_text,
            autocomplete,
            mods,
        } = self;
        let (subtitle, arg, default_icon) = match action {
            Action::Arg(arg) => (subtitle.unwrap_or_default(), arg, None),
            Action::Url(url) => (
                subtitle.unwrap_or_else(|| format!("open {title} in browser ({url})")),
                format!("open {url}"),
                Some(IconSource::Favicon(url)),
            ),
            Action::Exec(command) => (
                subtitle.unwrap_or_else(|| command.clone()),
                format!("zsh://{command}"),
                Some(IconSource::Glyph("terminal".into())),
            ),
        };
        let icon = match icon.or(default_icon) {
            Some(source) => icons.resolve(&source).await,
            None => None,
        };
        Item {
            icon,
            uid: uid.unwrap_or_else(|| uid_for(&title, &subtitle, &arg)),
            match_text: match_text.unwrap_or_else(|| format!("{title} {subtitle} {arg}")),
            autocomplete: autocomplete.unwrap_or_else(|| arg.clone()),
            mods: mods
                .into_iter()
                .map(|(key, subtitle)| (key, Modifier::from(subtitle)))
                .collect(),
            title,
            subtitle,
            arg,
            ..Item::default()
        }
    }
}

impl Menu {
    /// Build every item concurrently, keeping their order, with Alfred's default cache settings.
    pub async fn build(items: impl IntoIterator<Item = ItemBuilder>, icons: &Icons) -> Self {
        Self {
            cache: Some(MenuCache::default()),
            ..future::join_all(items.into_iter().map(|item| item.build(icons)))
                .await
                .into_iter()
                .collect()
        }
    }
}

/// SHA-256 of `"{title} {subtitle} {arg}"`, hex encoded.
fn uid_for(title: &str, subtitle: &str, arg: &str) -> String {
    Sha256::digest(format!("{title} {subtitle} {arg}"))
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Icon, IconType};

    #[tokio::test]
    async fn items_get_defaults_and_mods() {
        let icons = Icons::new("/nonexistent");
        let menu = Menu::build(
            [
                Item::exec("list", "ls -la"),
                Item::url("Docs", "http://example.com")
                    .icon(IconSource::FileType("public.html".into()))
                    .modifier("alt", "alt text"),
                Item::arg("Easy", "arg")
                    .subtitle("sub")
                    .uid("fixed")
                    .match_text("m")
                    .autocomplete("auto"),
            ],
            &icons,
        )
        .await;
        let [exec, url, easy] = menu.items.as_slice() else {
            panic!("{menu:?}")
        };

        assert_eq!(
            (exec.arg.as_str(), exec.subtitle.as_str()),
            ("zsh://ls -la", "ls -la")
        );
        assert_eq!(exec.uid, uid_for("list", "ls -la", "zsh://ls -la"));
        assert_eq!(exec.match_text, "list ls -la zsh://ls -la");
        assert_eq!(exec.autocomplete, "zsh://ls -la");
        assert_eq!(exec.icon, None, "no glyphs configured");

        assert_eq!(url.arg, "open https://example.com");
        assert_eq!(url.subtitle, "open Docs in browser (https://example.com)");
        assert_eq!(
            url.icon,
            Some(Icon {
                kind: Some(IconType::Filetype),
                path: "public.html".into()
            })
        );
        let json = serde_json::to_value(url).unwrap();
        assert_eq!(
            json["mods"],
            serde_json::json!({"alt": {"subtitle": "alt text"}})
        );

        assert_eq!(
            (
                easy.uid.as_str(),
                easy.match_text.as_str(),
                easy.autocomplete.as_str()
            ),
            ("fixed", "m", "auto")
        );
        assert_eq!(menu.cache, Some(MenuCache::default()));
    }
}
