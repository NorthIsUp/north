use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// A Script Filter response. Unknown top-level keys are preserved.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Menu {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cache: Option<MenuCache>,
    pub items: Vec<MenuItem>,
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
pub struct MenuItem {
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub alt: Option<Modifier>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cmd: Option<Modifier>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub text: Option<Text>,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
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

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Text {
    pub copy: String,
    pub largetype: String,
}

impl Menu {
    /// Keep items whose `match` (or `title`) contains every query token as a
    /// case-insensitive subsequence, best matches first.
    ///
    /// Drops `cache` so Alfred never reuses one query's results for another.
    ///
    /// ```
    /// use we_love_alfred::{Menu, MenuItem};
    ///
    /// let item = |title: &str| MenuItem { title: title.into(), ..Default::default() };
    /// let menu = Menu { items: vec![item("Hello"), item("Other")], ..Default::default() };
    /// assert_eq!(menu.filter("hello").items, [item("Hello")]);
    /// ```
    #[must_use]
    pub fn filter(mut self, query: &str) -> Self {
        let tokens: Vec<String> = query
            .to_lowercase()
            .split_whitespace()
            .map(str::to_owned)
            .collect();
        let mut ranked: Vec<(u32, MenuItem)> = self
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

    fn item(title: &str, match_text: &str) -> MenuItem {
        MenuItem {
            title: title.into(),
            match_text: match_text.into(),
            ..Default::default()
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
            ..Default::default()
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
        let menu = Menu {
            items: vec![
                item(
                    "user.workflow.A59C",
                    "code /tmp/a1-m2-p3-l4-i5-t6-u7-d8-e9/workspace",
                ),
                item("Experiments + Feature Flags", "experiments amplitude flags"),
                item("Clamp utility", ""),
                item("Amplitude", ""),
            ],
            ..Default::default()
        };
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
    fn unknown_keys_round_trip() {
        let raw = r#"{"rerun":1.0,"items":[{"title":"A","quicklookurl":"x"}]}"#;
        let menu: Menu = serde_json::from_str(raw).unwrap();
        assert_eq!(
            serde_json::to_string(&menu).unwrap(),
            r#"{"items":[{"title":"A","quicklookurl":"x"}],"rerun":1.0}"#
        );
    }
}
