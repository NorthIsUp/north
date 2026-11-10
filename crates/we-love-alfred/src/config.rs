//! Declarative menus: static items, loops, keyword routes and built-in providers from TOML.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::time::Duration;

use futures_util::future;
use regex::Regex;
use serde::Deserialize;
use tokio::fs;
use toml::{Table, Value};

use crate::cache::{cache_dir, expand_home};
use crate::editor::Editor;
use crate::github::PullRequestCache;
use crate::okta::Okta;
use crate::populate::Populate;
use crate::query::{Params, QueryPlan};
use crate::shell::join;
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
    pub github: Option<GithubConfig>,
    pub update: Option<Updater>,
    pub okta: Option<Okta>,
    pub tailscale: Option<Tailscale>,
    pub sources: Option<Sources>,
    /// Remote icon archives that `icon = { pack = "<name>/<file>" }` reads from lazily.
    #[serde(default)]
    pub icon_packs: BTreeMap<String, IconPack>,
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
    /// Text for ⌘C.
    pub copy: Option<String>,
    /// Text for ⌘L; defaults to nothing.
    pub largetype: Option<String>,
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
    /// SQLite database `sql` reads, relative to the workflow folder; opened read-only.
    pub db: Option<String>,
    /// Rendered with `[vars]`, `{keyword}` and `{value}` only; the query text is bound as `:query`,
    /// `:fts`, `:words` and `:first`. Each row renders the `[[route.item]]`s with its columns.
    pub sql: Option<String>,
    /// Run instead of `sql` when the query has no words, e.g. to list everything.
    pub empty_sql: Option<String>,
    /// Query a copy in the cache dir, refreshed when `db` changes.
    #[serde(default)]
    pub cache_copy: bool,
    /// How to build `db` when it's missing: the name of a function registered with
    /// [`crate::Workflow::populate`], or a JSON `file`/`url` piped through a `jq` filter.
    pub populate: Option<Populate>,
    /// Rebuild `db` with `populate` in the background once it's older than this many seconds.
    #[serde(default, deserialize_with = "optional_seconds")]
    pub refresh_every: Option<Duration>,
    /// Title of the row shown when the query fails; its subtitle is the error.
    pub error: Option<String>,
}

fn optional_seconds<'de, D: serde::Deserializer<'de>>(
    d: D,
) -> std::result::Result<Option<Duration>, D::Error> {
    Option::<u64>::deserialize(d).map(|s| s.map(Duration::from_secs))
}

/// What a matched route does.
#[derive(Debug)]
pub enum RouteAction {
    Exec {
        argv: Vec<String>,
        env: BTreeMap<String, String>,
    },
    Items(Vec<ItemBuilder>),
    Query(Box<QueryPlan>),
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
            if route.sql.is_some() != route.db.is_some()
                || (route.sql.is_some() && (!route.exec.is_empty() || route.items.is_empty()))
            {
                return Err(Error::Config(
                    "a query route needs db, sql and [[route.item]]s, and no exec".into(),
                ));
            }
            if route.sql.is_none()
                && (route.populate.is_some()
                    || route.refresh_every.is_some()
                    || route.error.is_some())
            {
                return Err(Error::Config(
                    "populate, refresh_every and error need a query route (db and sql)".into(),
                ));
            }
            if route.refresh_every.is_some() && route.populate.is_none() {
                return Err(Error::Config("refresh_every needs populate".into()));
            }
            if let Some(Populate::Data(source)) = &route.populate
                && source.file.is_some() == source.url.is_some()
            {
                return Err(Error::Config(
                    "populate needs exactly one of file, url".into(),
                ));
            }
        }
        Ok(config)
    }
}

impl Config {
    /// Read and validate a config file.
    ///
    /// # Errors
    ///
    /// I/O errors reading `path`, and the same errors as parsing with [`str::parse`].
    pub async fn load(path: impl AsRef<Path>) -> Result<Self> {
        fs::read_to_string(path).await?.parse()
    }

    /// The `[[item]]`s with templates rendered and loops expanded.
    ///
    /// # Errors
    ///
    /// [`Error::Template`] for an unknown variable, and [`Error::Config`] for an item without exactly one of `url`, `exec`, `arg`.
    pub fn items(&self) -> Result<Vec<ItemBuilder>> {
        let mut items = Vec::new();
        for item in &self.items {
            items.extend(item.expand(&self.vars, &BTreeMap::new())?);
        }
        Ok(items)
    }

    /// The first route matching `query`.
    ///
    /// # Errors
    ///
    /// [`Error::Regex`] for an invalid pattern, and template errors from rendering the route's items or command.
    pub fn route(&self, query: &str) -> Result<Option<RouteAction>> {
        let none = BTreeMap::new();
        for (index, route) in self.routes.iter().enumerate() {
            let Some(captured) = route.matches(query)? else {
                continue;
            };
            let scope = Scope {
                vars: &self.vars,
                bindings: &none,
                literals: &captured,
            };
            if let (Some(db), Some(sql)) = (&route.db, &route.sql) {
                let params = Params::new(
                    captured
                        .get("rest")
                        .and_then(Value::as_str)
                        .unwrap_or(query),
                );
                let sql = route
                    .empty_sql
                    .as_ref()
                    .filter(|_| params.is_empty())
                    .unwrap_or(sql);
                // SQL sees config values only: never the query text or regex captures.
                let trusted: BTreeMap<String, Value> = captured
                    .iter()
                    .filter(|(k, _)| matches!(k.as_str(), "keyword" | "value"))
                    .map(|(k, v)| (k.clone(), v.clone()))
                    .collect();
                let sql_scope = Scope {
                    vars: &self.vars,
                    bindings: &none,
                    literals: &trusted,
                };
                return Ok(Some(RouteAction::Query(Box::new(QueryPlan {
                    db: expand_home(&scope.render(db)?),
                    sql: sql_scope.render(sql)?,
                    params,
                    cache_copy: route.cache_copy,
                    route: index,
                    populate: route.populate.clone(),
                    refresh_every: route.refresh_every,
                    error: route.error.clone(),
                    items: route.items.clone(),
                    vars: self.vars.clone(),
                    literals: captured,
                }))));
            }
            return Ok(Some(if route.exec.is_empty() {
                let mut items = Vec::new();
                for item in &route.items {
                    items.extend(item.expand(&self.vars, &captured)?);
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
        Ok(None)
    }

    /// `[sources]` items, checking paths concurrently.
    ///
    /// # Errors
    ///
    /// Template errors in `paths`, or [`Error::Config`] if the glob task panics.
    pub async fn source_items(&self) -> Result<Vec<ItemBuilder>> {
        let Some(sources) = &self.sources else {
            return Ok(Vec::new());
        };
        let none = BTreeMap::new();
        let scope = Scope {
            vars: &self.vars,
            bindings: &none,
            literals: &none,
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
    use std::path::{Path, PathBuf};

    use super::*;
    use crate::{Icons, Item, Menu};

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

    /// A clara-style FTS5 code table in a temp dir.
    fn codes_db(dir: &Path, name: &str) -> PathBuf {
        let path = dir.join(name);
        let db = rusqlite::Connection::open(&path).unwrap();
        db.execute_batch(
            r#"create virtual table snomed using fts5(title, subtitle unindexed, code unindexed, aliases, tokenize="unicode61 tokenchars '.-'", prefix='1 2 3');
               insert into snomed values ('Heart attack (22298006)', 'Disorder', '22298006', 'MI | myocardial infarction');
               insert into snomed values ('Heart failure (84114007)', 'Disorder', '84114007', '');
               insert into snomed values ('Attack of {braces} (1)', 'Odd', '1', '');"#,
        )
        .unwrap();
        path
    }

    fn query_config(db: &Path, cache_copy: bool) -> Config {
        format!(
            r#"
            [[route]]
            keywords = {{ snomed = "snomed", sct = "snomed" }}
            db = "{db}"
            cache_copy = {cache_copy}
            sql = "select title, subtitle, code from {{value}} where {{value}} match :fts order by lower(title) not like :words || ' (%', rank limit 50"
            empty_sql = "select title, subtitle, code from {{value}} limit 2"
            [[route.item]]
            title = "{{title}}"
            subtitle = "{{subtitle}} · {{keyword}}"
            arg = "copy:{{code}}"
            copy = "{{code}}"
            uid = ""
            "#,
            db = db.display()
        )
        .parse()
        .unwrap()
    }

    async fn query(config: &Config, text: &str) -> Result<Vec<Item>> {
        let Some(RouteAction::Query(plan)) = config.route(text)? else {
            panic!("not a query route: {text}")
        };
        let icons = Icons::new("/nonexistent");
        Ok(Menu::build(plan.run().await?, &icons).await.items)
    }

    #[tokio::test]
    async fn sqlite_routes_bind_the_query_and_render_rows() {
        let dir = tempfile::tempdir().unwrap();
        let config = query_config(&codes_db(dir.path(), "codes.db"), false);
        let items = query(&config, "snomed heart attack").await.unwrap();
        assert_eq!(items.len(), 1);
        let item = &items[0];
        assert_eq!(
            (
                item.title.as_str(),
                item.arg.as_str(),
                item.subtitle.as_str()
            ),
            (
                "Heart attack (22298006)",
                "copy:22298006",
                "Disorder · snomed"
            )
        );
        assert_eq!(
            serde_json::to_value(item).unwrap()["text"],
            serde_json::json!({"copy": "22298006"})
        );
        assert_eq!(
            item.uid, "",
            "uid = \"\" keeps Alfred from reordering results"
        );

        let titles = |items: Vec<Item>| items.into_iter().map(|i| i.title).collect::<Vec<_>>();
        let mut heart = titles(query(&config, "SCT heart").await.unwrap());
        heart.sort();
        assert_eq!(
            heart,
            ["Heart attack (22298006)", "Heart failure (84114007)"],
            "alias keywords share a route"
        );
        assert_eq!(
            titles(query(&config, "snomed attack {braces}").await.unwrap()),
            ["Attack of {braces} (1)"],
            "row and query braces stay text"
        );
        assert_eq!(
            query(&config, "snomed ').drop table snomed;--")
                .await
                .unwrap()
                .len(),
            0,
            "the query is only ever bound"
        );
        assert_eq!(
            query(&config, "snomed").await.unwrap().len(),
            2,
            "no words runs empty_sql"
        );
    }

    #[tokio::test]
    async fn sqlite_routes_report_bad_databases_and_copy_into_the_cache() {
        let dir = tempfile::tempdir().unwrap();
        let missing = query_config(&dir.path().join("missing.db"), false);
        assert!(matches!(
            query(&missing, "snomed x").await,
            Err(Error::Sqlite(_))
        ));
        let name = format!("we-love-test-{}.db", std::process::id());
        let copied = query_config(&codes_db(dir.path(), &name), true);
        assert_eq!(query(&copied, "snomed heart").await.unwrap().len(), 2);
        let local = cache_dir().join("db").join(&name);
        assert!(local.exists());
        std::fs::remove_file(local).unwrap();
        assert!(
            "[[route]]\nkeywords = { a = '' }\nsql = 'select 1'"
                .parse::<Config>()
                .is_err(),
            "sql needs db and items"
        );
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
