//! Declarative menus: static items, loops, keyword routes and built-in providers from TOML.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::str::FromStr;

use futures_util::future;
use regex::Regex;
use serde::Deserialize;
use tokio::fs;
use toml::{Table, Value};

use crate::cache::{cache_dir, expand_home};
use crate::editor::Editor;
use crate::github::PullRequestCache;
use crate::okta::Okta;
use crate::shell::join;
use crate::tailscale::Tailscale;
use crate::template::{Scope, product};
use crate::update::Updater;
use crate::{Error, IconSource, Item, ItemBuilder, Result};

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
    pub github: Option<GithubConfig>,
    pub update: Option<Updater>,
    pub okta: Option<Okta>,
    pub tailscale: Option<Tailscale>,
    pub sources: Option<Sources>,
}

/// One `[[item]]`; exactly one of `url`, `exec`, `arg`. Every string is a template.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ItemConfig {
    pub title: String,
    pub url: Option<String>,
    /// A zsh command, or an argv list that gets shell-quoted.
    pub exec: Option<Exec>,
    pub arg: Option<String>,
    pub subtitle: Option<String>,
    pub icon: Option<IconSpec>,
    pub uid: Option<String>,
    #[serde(rename = "match")]
    pub match_text: Option<String>,
    pub autocomplete: Option<String>,
    /// Subtitles per modifier: `mods = { alt = "…" }`.
    #[serde(default)]
    pub mods: BTreeMap<String, String>,
    /// Repeat the item for every combination of these lists, binding each value to its name.
    #[serde(default)]
    pub each: BTreeMap<String, Vec<Value>>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum Exec {
    Shell(String),
    Argv(Vec<String>),
}

#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum IconSpec {
    One(IconSource),
    /// The first that resolves.
    FirstOf(Vec<IconSource>),
}

/// A `[[route]]`: queries it matches skip the cached menu.
///
/// Matches either the first word against `keywords` (binding `{keyword}`,
/// `{value}` and `{rest}`), or the whole query against `pattern` (binding
/// `{0}`, `{1}`, … and named groups). `{query}` is always bound. Then it
/// either replaces the process with `exec`, or shows its `[[route.item]]`s.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Route {
    #[serde(default)]
    pub keywords: BTreeMap<String, String>,
    pub pattern: Option<String>,
    #[serde(default)]
    pub exec: Vec<String>,
    #[serde(default)]
    pub env: BTreeMap<String, String>,
    #[serde(default, rename = "item")]
    pub items: Vec<ItemConfig>,
}

/// What a matched route does.
#[derive(Debug)]
pub enum RouteAction {
    Exec {
        argv: Vec<String>,
        env: BTreeMap<String, String>,
    },
    Items(Vec<ItemBuilder>),
}

/// `[github]`: open PRs via `gh`, searched with `<keyword> [@author] [terms]`, `#<number|text>` or a bare number.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GithubConfig {
    pub repo: String,
    #[serde(default = "default_pr_keyword")]
    pub keyword: String,
    #[serde(default = "default_limit")]
    pub limit: u32,
}

fn default_pr_keyword() -> String {
    "prs".into()
}

fn default_limit() -> u32 {
    1000
}

impl GithubConfig {
    pub fn cache(&self) -> PullRequestCache {
        let path = cache_dir().join(format!("{}-prs.json", self.repo.replace('/', "-")));
        PullRequestCache {
            limit: self.limit,
            ..PullRequestCache::new(&self.repo, path)
        }
    }
}

/// `[sources]`: one item per path and installed editor, preferring a `*.code-workspace` inside a directory.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Sources {
    /// Paths or glob patterns; `~/` and templates allowed. Missing paths are skipped.
    #[serde(default)]
    pub paths: Vec<String>,
}

impl FromStr for Config {
    type Err = Error;

    fn from_str(toml: &str) -> Result<Self> {
        let config: Self = toml::from_str(toml)?;
        for route in &config.routes {
            if let Some(pattern) = &route.pattern {
                Regex::new(pattern)?;
            }
            if route.keywords.is_empty() == route.pattern.is_none() {
                return Err(Error::Config(
                    "a route needs exactly one of keywords, pattern".into(),
                ));
            }
        }
        Ok(config)
    }
}

impl Config {
    pub async fn load(path: impl AsRef<Path>) -> Result<Self> {
        fs::read_to_string(path).await?.parse()
    }

    /// The `[[item]]`s with templates rendered and loops expanded.
    pub fn items(&self) -> Result<Vec<ItemBuilder>> {
        let mut items = Vec::new();
        for item in &self.items {
            items.extend(item.expand(&self.vars, &BTreeMap::new())?);
        }
        Ok(items)
    }

    /// The first route matching `query`.
    pub fn route(&self, query: &str) -> Result<Option<RouteAction>> {
        for route in &self.routes {
            if let Some(bindings) = route.matches(query)? {
                let scope = Scope {
                    vars: &self.vars,
                    bindings: &bindings,
                };
                return Ok(Some(if route.exec.is_empty() {
                    let mut items = Vec::new();
                    for item in &route.items {
                        items.extend(item.expand(&self.vars, &bindings)?);
                    }
                    RouteAction::Items(items)
                } else {
                    let argv = route
                        .exec
                        .iter()
                        .map(|arg| scope.render(arg))
                        .collect::<Result<_>>()?;
                    let env = route
                        .env
                        .iter()
                        .map(|(k, v)| Ok((k.clone(), scope.render(v)?)))
                        .collect::<Result<_>>()?;
                    RouteAction::Exec { argv, env }
                }));
            }
        }
        Ok(None)
    }

    /// `[sources]` items, checking paths concurrently.
    pub async fn source_items(&self) -> Result<Vec<ItemBuilder>> {
        let Some(sources) = &self.sources else {
            return Ok(Vec::new());
        };
        let scope = Scope {
            vars: &self.vars,
            bindings: &BTreeMap::new(),
        };
        let patterns: Vec<String> = sources
            .paths
            .iter()
            .map(|p| scope.render(p))
            .collect::<Result<_>>()?;
        let paths = tokio::task::spawn_blocking(move || {
            patterns
                .iter()
                .flat_map(|pattern| {
                    let pattern = expand_home(pattern).to_string_lossy().into_owned();
                    glob::glob(&pattern)
                        .into_iter()
                        .flatten()
                        .flatten()
                        .collect::<Vec<_>>()
                })
                .collect::<Vec<PathBuf>>()
        })
        .await
        .map_err(|e| Error::Config(format!("source glob task failed: {e}")))?;
        let targets = future::join_all(paths.iter().map(|path| workspace_or(path))).await;
        let editors = Editor::installed().await;
        Ok(targets
            .iter()
            .flat_map(|target| editors.iter().map(move |editor| editor.open(target)))
            .collect())
    }
}

/// The first `*.code-workspace` in a directory, else the path itself.
async fn workspace_or(path: &Path) -> PathBuf {
    if let Ok(mut entries) = fs::read_dir(path).await {
        while let Ok(Some(entry)) = entries.next_entry().await {
            if entry
                .path()
                .extension()
                .is_some_and(|e| e == "code-workspace")
            {
                return entry.path();
            }
        }
    }
    path.to_owned()
}

impl Route {
    fn matches(&self, query: &str) -> Result<Option<BTreeMap<String, Value>>> {
        let mut bindings = BTreeMap::from([("query".to_owned(), Value::from(query))]);
        if let Some(pattern) = &self.pattern {
            let regex = Regex::new(pattern)?;
            let Some(captures) = regex.captures(query) else {
                return Ok(None);
            };
            for (i, name) in regex.capture_names().enumerate() {
                let value = captures.get(i).map_or("", |m| m.as_str());
                bindings.insert(i.to_string(), Value::from(value));
                if let Some(name) = name {
                    bindings.insert(name.to_owned(), Value::from(value));
                }
            }
            return Ok(Some(bindings));
        }
        let (word, rest) = query.split_once(char::is_whitespace).unwrap_or((query, ""));
        let Some((keyword, value)) = self
            .keywords
            .iter()
            .find(|(k, _)| k.eq_ignore_ascii_case(word))
        else {
            return Ok(None);
        };
        bindings.insert("keyword".into(), Value::from(keyword.as_str()));
        bindings.insert("value".into(), Value::from(value.as_str()));
        bindings.insert("rest".into(), Value::from(rest.trim()));
        Ok(Some(bindings))
    }
}

impl ItemConfig {
    fn expand(&self, vars: &Table, outer: &BTreeMap<String, Value>) -> Result<Vec<ItemBuilder>> {
        product(&self.each)
            .into_iter()
            .map(|mut bindings| {
                for (k, v) in outer {
                    bindings.entry(k.clone()).or_insert_with(|| v.clone());
                }
                self.build(Scope {
                    vars,
                    bindings: &bindings,
                })
            })
            .collect()
    }

    fn build(&self, scope: Scope<'_>) -> Result<ItemBuilder> {
        let r = |s: &str| scope.render(s);
        let title = r(&self.title)?;
        let mut item = match (&self.url, &self.exec, &self.arg) {
            (Some(url), None, None) => Item::url(title, r(url)?),
            (None, Some(Exec::Shell(command)), None) => Item::exec(title, r(command)?),
            (None, Some(Exec::Argv(argv)), None) => Item::exec(
                title,
                join(argv.iter().map(|a| r(a)).collect::<Result<Vec<_>>>()?),
            ),
            (None, None, Some(arg)) => Item::arg(title, r(arg)?),
            _ => {
                return Err(Error::Config(format!(
                    "item {:?} needs exactly one of url, exec, arg",
                    self.title
                )));
            }
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
    fn routes_keywords_and_patterns() {
        let config: Config = EXAMPLE.parse().unwrap();
        let Some(RouteAction::Exec { argv, env }) = config.route("RX metformin 500").unwrap()
        else {
            panic!()
        };
        assert_eq!(&argv[4..], ["rxnorm", "metformin 500"]);
        assert_eq!(env["prefix"], "copy:");
        let Some(RouteAction::Items(items)) = config.route("clr1234567890").unwrap() else {
            panic!()
        };
        assert_eq!(items[0].title, "Open CLR-1234567890");
        assert!(config.route("github").unwrap().is_none());
    }

    #[test]
    fn rejects_bad_config() {
        assert!(matches!(
            "[[item]]\ntitle = 'x'".parse::<Config>().map(|c| c.items()),
            Ok(Err(Error::Config(_)))
        ));
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
        assert_eq!(config.items().unwrap().len(), 5);
        assert!(
            config.github.is_some()
                && config.update.is_some()
                && config.okta.is_some()
                && config.tailscale.is_some()
        );
    }

    #[tokio::test]
    async fn sources_glob_and_prefer_workspaces() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join("app")).unwrap();
        std::fs::write(dir.path().join("app/app.code-workspace"), "{}").unwrap();
        std::fs::create_dir_all(dir.path().join("lib")).unwrap();
        let config = Config {
            sources: Some(Sources {
                paths: vec![format!("{}/*", dir.path().display())],
            }),
            ..Config::default()
        };
        let installed = Editor::installed().await.len();
        let items = config.source_items().await.unwrap();
        assert_eq!(items.len(), 2 * installed);
        if installed > 0 {
            assert_eq!(items[0].title, "app.code-workspace");
        }
    }
}
