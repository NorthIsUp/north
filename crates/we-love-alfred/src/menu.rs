use std::collections::BTreeMap;
use std::fmt;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// A Script Filter response. Unknown top-level keys are preserved.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Menu {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cache: Option<MenuCache>,
    /// Seconds until Alfred reruns the Script Filter.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub rerun: Option<f64>,
    /// Session variables Alfred passes back on reruns.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub variables: BTreeMap<String, String>,
    pub items: Vec<Item>,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

/// Alfred's own result cache settings.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct MenuCache {
    pub seconds: u64,
    pub loosereload: bool,
}

impl Default for MenuCache {
    fn default() -> Self {
        Self {
            seconds: 3600,
            loosereload: true,
        }
    }
}

/// One Script Filter row. Empty strings and `None`s are omitted; unknown keys are preserved.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Item {
    pub title: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub subtitle: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub arg: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub uid: String,
    #[serde(rename = "match", default, skip_serializing_if = "String::is_empty")]
    pub match_text: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub autocomplete: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub valid: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub icon: Option<Icon>,
    /// Overrides while a modifier is held, keyed `alt`, `cmd`, `ctrl`, `shift`, `fn` or a combo like `cmd+alt`.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub mods: BTreeMap<String, Modifier>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub text: Option<Text>,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

impl Item {
    /// A row that can't be actioned, for messages and empty results.
    pub fn message(title: impl Into<String>, subtitle: impl Into<String>) -> Self {
        Self {
            title: title.into(),
            subtitle: subtitle.into(),
            valid: Some(false),
            ..Self::default()
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Icon {
    #[serde(rename = "type", default, skip_serializing_if = "Option::is_none")]
    pub kind: Option<IconType>,
    pub path: String,
}

impl Icon {
    pub fn path(path: impl Into<String>) -> Self {
        Self {
            kind: None,
            path: path.into(),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum IconType {
    /// Use the icon of the file at `path`.
    Fileicon,
    /// Use the icon of the UTI named by `path`.
    Filetype,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Modifier {
    #[serde(default)]
    pub subtitle: String,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

impl From<String> for Modifier {
    fn from(subtitle: String) -> Self {
        Self {
            subtitle,
            extra: Map::new(),
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Text {
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub copy: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub largetype: String,
}

impl FromIterator<Item> for Menu {
    fn from_iter<I: IntoIterator<Item = Item>>(items: I) -> Self {
        Self {
            items: items.into_iter().collect(),
            ..Self::default()
        }
    }
}

impl fmt::Display for Menu {
    /// The Script Filter JSON.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&serde_json::to_string(self).map_err(|_| fmt::Error)?)
    }
}

impl Menu {
    /// Keep items whose `match` (or `title`) contains every query token as a
    /// case-insensitive subsequence, best matches first.
    ///
    /// Drops `cache` so Alfred never reuses one query's results for another.
    ///
    /// ```
    /// use we_love_alfred::{Item, Menu};
    ///
    /// let item = |title: &str| Item { title: title.into(), ..Item::default() };
    /// let menu = Menu::from_iter([item("Hello"), item("Other")]);
    /// assert_eq!(menu.filter("hello").items, [item("Hello")]);
    /// ```
    #[must_use]
    pub fn filter(mut self, query: &str) -> Self {
        let tokens: Vec<String> = query
            .to_lowercase()
            .split_whitespace()
            .map(str::to_owned)
            .collect();
        let mut ranked: Vec<(u32, Item)> = self
            .items
            .into_iter()
            .filter_map(|item| {
                let title = item.title.to_lowercase();
                let text = if item.match_text.is_empty() {
                    title.clone()
                } else {
                    item.match_text.to_lowercase()
                };
                let total = tokens
                    .iter()
                    .map(|token| score(token, &title, &text))
                    .sum::<Option<u32>>()?;
                Some((total, item))
            })
            .collect();
        // Stable, so equally good matches keep the builder's order.
        ranked.sort_by_key(|(total, _)| *total);
        self.items = ranked.into_iter().map(|(_, item)| item).collect();
        self.cache = None;
        self
    }

    /// Show a non-actionable `title` row instead of an empty menu.
    #[must_use]
    pub fn or_message(mut self, title: &str) -> Self {
        if self.items.is_empty() {
            self.items.push(Item::message(title, ""));
        }
        self
    }
}

/// Lower is better: title word prefix, title substring, match substring, scattered letters.
fn score(token: &str, title: &str, text: &str) -> Option<u32> {
    if title.split_whitespace().any(|word| word.starts_with(token)) {
        Some(0)
    } else if title.contains(token) {
        Some(1)
    } else if text.contains(token) {
        Some(2)
    } else {
        is_subsequence(token, text).then_some(3)
    }
}

/// Every character of `needle` appears in order in `haystack`.
pub(crate) fn is_subsequence(needle: &str, haystack: &str) -> bool {
    let mut rest = haystack.chars();
    needle.chars().all(|c| rest.any(|h| h == c))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn item(title: &str, match_text: &str) -> Item {
        Item {
            title: title.into(),
            match_text: match_text.into(),
            ..Item::default()
        }
    }

    #[test]
    fn filters_match_and_title() {
        let menu = Menu {
            cache: Some(MenuCache::default()),
            items: vec![
                item("Production deploy", "production deploy"),
                item("Open dashboard", ""),
            ],
            ..Menu::default()
        };
        let filtered = menu.clone().filter("prd dpl");
        assert_eq!(
            filtered.items,
            [item("Production deploy", "production deploy")]
        );
        assert_eq!(filtered.cache, None);
        assert_eq!(menu.filter("dsbrd").items, [item("Open dashboard", "")]);
    }

    #[test]
    fn ranks_title_matches_above_scattered_letters() {
        let menu = Menu::from_iter([
            item(
                "user.workflow.A59C",
                "code /tmp/a1-m2-p3-l4-i5-t6-u7-d8-e9/workspace",
            ),
            item("Experiments + Feature Flags", "experiments amplitude flags"),
            item("Clamp utility", ""),
            item("Amplitude", ""),
        ]);
        let titles: Vec<_> = menu
            .filter("amplitude")
            .items
            .into_iter()
            .map(|i| i.title)
            .collect();
        assert_eq!(
            titles,
            [
                "Amplitude",
                "Experiments + Feature Flags",
                "user.workflow.A59C"
            ]
        );
    }

    #[test]
    fn serializes_mods_variables_and_unknown_keys() {
        let raw = r#"{"rerun":0.1,"variables":{"a":"1"},"items":[{"title":"A","mods":{"alt":{"subtitle":"x"}},"quicklookurl":"q"}],"skipknowledge":true}"#;
        let menu: Menu = serde_json::from_str(raw).unwrap();
        assert_eq!(menu.items[0].mods["alt"].subtitle, "x");
        assert_eq!(menu.to_string(), raw);
    }

    #[test]
    fn empty_menu_shows_message() {
        assert_eq!(
            Menu::default().or_message("Nothing").to_string(),
            r#"{"items":[{"title":"Nothing","valid":false}]}"#
        );
    }
}
