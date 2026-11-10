//! Declarative workflows: the TOML schema, `[vars]` templates and `[[item]]`s.

use std::collections::BTreeMap;
use std::path::Path;
use std::str::FromStr;

use serde::Deserialize;
use tokio::fs;
use toml::{Table, Value};

use crate::github::Github;
use crate::okta::Okta;
use crate::route::{Route, expand};
use crate::shell::join;
use crate::sources::Sources;
use crate::tailscale::Tailscale;
use crate::template::{Scope, product};
use crate::update::Updater;
use crate::{Error, IconPack, IconSource, Item, ItemBuilder, Result};

/// A workflow described in TOML. See the crate README for the full format.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    /// Cache name; defaults to `$alfred_workflow_bundleid`.
    pub cache: Option<String>,
    /// Values for `{name}` templates. Strings may reference other vars and `{env.NAME}`.
    #[serde(default)]
    pub vars: Table,
    #[serde(default, rename = "item")]
    pub items: Vec<ItemConfig>,
    #[serde(default, rename = "route")]
    pub routes: Vec<Route>,
    pub github: Option<Github>,
    pub update: Option<Updater>,
    pub okta: Option<Okta>,
    pub tailscale: Option<Tailscale>,
    pub sources: Option<Sources>,
    /// Remote icon archives that `icon = { pack = "<name>/<file>" }` reads from lazily.
    #[serde(default)]
    pub icon_packs: BTreeMap<String, IconPack>,
}

/// One `[[item]]`. Every string is a template.
#[derive(Debug, Clone, Deserialize)]
#[serde(try_from = "RawItem")]
pub struct ItemConfig {
    pub title: String,
    pub action: ItemAction,
    pub subtitle: Option<String>,
    pub icon: Option<IconSpec>,
    pub uid: Option<String>,
    pub match_text: Option<String>,
    pub autocomplete: Option<String>,
    /// Text for ⌘C.
    pub copy: Option<String>,
    /// Text for ⌘L; defaults to nothing.
    pub largetype: Option<String>,
    /// Subtitles per modifier: `mods = { alt = "…" }`.
    pub mods: BTreeMap<String, String>,
    /// Repeat the item for every combination of these lists, binding each value to its name.
    pub each: BTreeMap<String, Vec<Value>>,
}

/// What an item does: exactly one of `url`, `exec` or `arg` in TOML.
#[derive(Debug, Clone)]
pub enum ItemAction {
    Url(String),
    Exec(Exec),
    Arg(String),
}

#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum Exec {
    /// A zsh command.
    Shell(String),
    /// An argv list, shell-quoted into a command.
    Argv(Vec<String>),
}

#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum IconSpec {
    One(IconSource),
    /// The first that resolves.
    FirstOf(Vec<IconSource>),
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawItem {
    title: String,
    url: Option<String>,
    exec: Option<Exec>,
    arg: Option<String>,
    subtitle: Option<String>,
    icon: Option<IconSpec>,
    uid: Option<String>,
    #[serde(rename = "match")]
    match_text: Option<String>,
    autocomplete: Option<String>,
    copy: Option<String>,
    largetype: Option<String>,
    #[serde(default)]
    mods: BTreeMap<String, String>,
    #[serde(default)]
    each: BTreeMap<String, Vec<Value>>,
}

impl TryFrom<RawItem> for ItemConfig {
    type Error = String;

    fn try_from(raw: RawItem) -> Result<Self, String> {
        let action = match (raw.url, raw.exec, raw.arg) {
            (Some(url), None, None) => ItemAction::Url(url),
            (None, Some(exec), None) => ItemAction::Exec(exec),
            (None, None, Some(arg)) => ItemAction::Arg(arg),
            _ => {
                return Err(format!(
                    "item {:?} needs exactly one of url, exec, arg",
                    raw.title
                ));
            }
        };
        Ok(Self {
            title: raw.title,
            action,
            subtitle: raw.subtitle,
            icon: raw.icon,
            uid: raw.uid,
            match_text: raw.match_text,
            autocomplete: raw.autocomplete,
            copy: raw.copy,
            largetype: raw.largetype,
            mods: raw.mods,
            each: raw.each,
        })
    }
}

impl FromStr for Config {
    type Err = Error;

    fn from_str(toml: &str) -> Result<Self> {
        Ok(toml::from_str(toml)?)
    }
}

impl Config {
    /// Read and validate a config file.
    ///
    /// # Errors
    ///
    /// I/O errors reading `path`, and [`Error::Toml`] for invalid TOML or an invalid item or route.
    pub async fn load(path: impl AsRef<Path>) -> Result<Self> {
        fs::read_to_string(path).await?.parse()
    }

    /// The `[[item]]`s with templates rendered and loops expanded.
    ///
    /// # Errors
    ///
    /// [`Error::Template`] for an unknown variable.
    pub fn items(&self) -> Result<Vec<ItemBuilder>> {
        expand(&self.items, &self.vars, &BTreeMap::new())
    }
}

impl ItemConfig {
    /// One item per `each` combination; `literals` are runtime values bound verbatim.
    pub(crate) fn expand(
        &self,
        vars: &Table,
        literals: &BTreeMap<String, Value>,
    ) -> Result<Vec<ItemBuilder>> {
        product(&self.each)
            .iter()
            .map(|bindings| {
                self.build(Scope {
                    vars,
                    bindings,
                    literals,
                })
            })
            .collect()
    }

    fn build(&self, scope: Scope<'_>) -> Result<ItemBuilder> {
        let r = |s: &str| scope.render(s);
        let title = r(&self.title)?;
        let mut item = match &self.action {
            ItemAction::Url(url) => Item::url(title, r(url)?),
            ItemAction::Exec(Exec::Shell(command)) => Item::exec(title, r(command)?),
            ItemAction::Exec(Exec::Argv(argv)) => Item::exec(
                title,
                join(argv.iter().map(|a| r(a)).collect::<Result<Vec<_>>>()?),
            ),
            ItemAction::Arg(arg) => Item::arg(title, r(arg)?),
        };
        if let Some(subtitle) = &self.subtitle {
            item = item.subtitle(r(subtitle)?);
        }
        if let Some(icon) = &self.icon {
            item = item.icon(match icon {
                IconSpec::One(source) => source.try_map(&r)?,
                IconSpec::FirstOf(sources) => IconSource::FirstOf(
                    sources
                        .iter()
                        .map(|s| s.try_map(&r))
                        .collect::<Result<_>>()?,
                ),
            });
        }
        if let Some(uid) = &self.uid {
            item = item.uid(r(uid)?);
        }
        if let Some(text) = &self.match_text {
            item = item.match_text(r(text)?);
        }
        if let Some(autocomplete) = &self.autocomplete {
            item = item.autocomplete(r(autocomplete)?);
        }
        if self.copy.is_some() || self.largetype.is_some() {
            let text = |t: &Option<String>| t.as_deref().map_or(Ok(String::new()), r);
            item = item.text(text(&self.copy)?, text(&self.largetype)?);
        }
        for (modifier, subtitle) in &self.mods {
            item = item.modifier(modifier, r(subtitle)?);
        }
        Ok(item)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Icons, Menu};

    const EXAMPLE: &str = r#"
        cache = "example"

        [vars]
        domain = "console.example.com"
        region = "us-east-1"

        [[item]]
        title = "Errors"
        subtitle = "Sentry"
        url = "http://sentry.example.com"
        icon = { filetype = "public.html" }

        [[item]]
        title = "{account.name} — {service}"
        url = "https://{domain}/{service}?account={account.id}&region={region}"
        icon = [{ path = "./icons/Arch_*{service}*" }, { filetype = "public.folder" }]
        each.account = [{ id = "111", name = "prod" }, { id = "222", name = "dev" }]
        each.service = ["s3", "rds"]

        [[item]]
        title = "Search {set}"
        exec = ["osascript", "-e", "search \"{set} \""]
        match = "{set}"
        each.set = ["icd10"]

        [[route]]
        keywords = { icd10 = "icd10", rx = "rxnorm" }
        exec = ["/bin/zsh", "-c", "source ./codes.zsh \"$1\" \"$2\"", "_", "{value}", "{rest}"]
        env = { prefix = "copy:" }

        [[route]]
        pattern = '(?i)^clr-?(\d{10})$'
        [[route.item]]
        title = "Open CLR-{1}"
        url = "https://ehr.example.com/patients/CLR-{1}"
    "#;

    #[tokio::test]
    async fn expands_items_and_loops() {
        let config: Config = EXAMPLE.parse().unwrap();
        let items = config.items().unwrap();
        let titles: Vec<&str> = items.iter().map(|i| i.title.as_str()).collect();
        assert_eq!(
            titles,
            [
                "Errors",
                "prod — s3",
                "prod — rds",
                "dev — s3",
                "dev — rds",
                "Search icd10"
            ]
        );
        let menu = Menu::build(items, &Icons::new("/nonexistent")).await;
        assert_eq!(
            menu.items[2].arg,
            "open https://console.example.com/rds?account=111&region=us-east-1"
        );
        assert_eq!(
            menu.items[2].icon.as_ref().unwrap().path,
            "public.folder",
            "falls through the missing glob"
        );
        assert_eq!(menu.items[5].arg, r#"zsh://osascript -e 'search "icd10 "'"#);
        assert_eq!(menu.items[5].match_text, "icd10");
    }

    #[test]
    fn rejects_bad_config() {
        assert!(
            "[[item]]
title = 'x'"
                .parse::<Config>()
                .is_err(),
            "an item needs url, exec or arg"
        );
        assert!("[[route]]\npattern = '('".parse::<Config>().is_err());
        assert!("[[route]]\nexec = ['x']".parse::<Config>().is_err());
        assert!("typo = 1".parse::<Config>().is_err());
        assert!(matches!(
            "[[item]]\ntitle = '{missing}'\narg = 'x'"
                .parse::<Config>()
                .unwrap()
                .items(),
            Err(Error::Template { .. })
        ));
    }

    #[test]
    fn readme_config_parses() {
        let readme = include_str!("../README.md");
        let toml = readme
            .split("```toml\n")
            .nth(1)
            .unwrap()
            .split("```")
            .next()
            .unwrap();
        let config: Config = toml.parse().unwrap();
        assert_eq!(config.items().unwrap().len(), 6);
        assert!(
            config.github.is_some()
                && config.update.is_some()
                && config.okta.is_some()
                && config.tailscale.is_some()
        );
    }
}
