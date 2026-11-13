//! `[[route]]`s: queries matched by keyword or pattern and answered live, by replacing the
//! process, showing items, or querying SQLite.

use std::collections::BTreeMap;
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::time::{Duration, SystemTime};

use futures_util::future::{BoxFuture, FutureExt};
use regex::Regex;
use serde::Deserialize;
use toml::{Table, Value};

use crate::cache::{expand_home, with_suffix};
use crate::config::ItemConfig;
use crate::feature::{After, Context, Feature, split_word};
use crate::job::{Job, Status};
use crate::populate::{self, Populate};
use crate::query::{Params, QueryPlan};
use crate::template::Scope;
use crate::{Error, Item, ItemBuilder, Menu, Result};

/// Rebuilds a query route's database: `db-populate <route index> <db>`.
pub const POPULATE_COMMAND: &str = "db-populate";
const BUILDING: &str = "Building the index";
/// How soon a failed database build is retried.
const BUILD_RETRY: Duration = Duration::from_secs(60);

/// One `[[route]]`. See the crate README for the TOML.
#[derive(Debug, Clone, Deserialize)]
#[serde(try_from = "RawRoute")]
pub struct Route {
    matcher: Matcher,
    action: Action,
}

#[derive(Debug, Clone)]
enum Matcher {
    /// The first word, case-insensitively; binds `{keyword}`, `{value}` and `{rest}`.
    Keywords(BTreeMap<String, String>),
    /// The whole query; binds `{0}`, `{1}`, … and named groups.
    Pattern(Regex),
}

#[derive(Debug, Clone)]
enum Action {
    Exec {
        argv: Vec<String>,
        env: BTreeMap<String, String>,
    },
    Items(Vec<ItemConfig>),
    Query(QuerySpec),
}

/// A route that reads SQLite: `sql` against `db`, each row rendering `items`.
#[derive(Debug, Clone)]
pub(crate) struct QuerySpec {
    pub db: String,
    pub sql: String,
    pub empty_sql: Option<String>,
    pub cache_copy: bool,
    pub populate: Option<Populating>,
    pub error: String,
    pub items: Vec<ItemConfig>,
}

/// How a query route builds its database, and how often to rebuild it in the background.
#[derive(Debug, Clone)]
pub(crate) struct Populating {
    pub with: Populate,
    pub every: Option<Duration>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawRoute {
    #[serde(default)]
    keywords: BTreeMap<String, String>,
    pattern: Option<String>,
    #[serde(default)]
    exec: Vec<String>,
    #[serde(default)]
    env: BTreeMap<String, String>,
    #[serde(default, rename = "item")]
    items: Vec<ItemConfig>,
    db: Option<String>,
    sql: Option<String>,
    empty_sql: Option<String>,
    #[serde(default)]
    cache_copy: bool,
    populate: Option<Populate>,
    refresh_every: Option<u64>,
    error: Option<String>,
}

impl TryFrom<RawRoute> for Route {
    type Error = String;

    fn try_from(raw: RawRoute) -> Result<Self, String> {
        let matcher = match (raw.keywords.is_empty(), raw.pattern) {
            (false, None) => Matcher::Keywords(raw.keywords),
            (true, Some(pattern)) => {
                Matcher::Pattern(Regex::new(&pattern).map_err(|e| e.to_string())?)
            }
            _ => return Err("a route needs exactly one of keywords, pattern".into()),
        };
        let querying = raw.db.is_some() || raw.sql.is_some();
        let query_only = raw.empty_sql.is_some()
            || raw.cache_copy
            || raw.populate.is_some()
            || raw.refresh_every.is_some()
            || raw.error.is_some();
        let action = match (raw.exec.is_empty(), querying) {
            (false, false) if raw.items.is_empty() && !query_only => Action::Exec { argv: raw.exec, env: raw.env },
            (true, true) if raw.env.is_empty() => {
                let (Some(db), Some(sql)) = (raw.db, raw.sql) else { return Err("a query route needs both db and sql".into()) };
                if raw.items.is_empty() {
                    return Err("a query route needs [[route.item]]s to render its rows".into());
                }
                let populate = match (raw.populate, raw.refresh_every) {
                    (Some(with), every) => Some(Populating { with, every: every.map(Duration::from_secs) }),
                    (None, Some(_)) => return Err("refresh_every needs populate".into()),
                    (None, None) => None,
                };
                Action::Query(QuerySpec {
                    db,
                    sql,
                    empty_sql: raw.empty_sql,
                    cache_copy: raw.cache_copy,
                    populate,
                    error: raw.error.unwrap_or_else(|| "Query failed".into()),
                    items: raw.items,
                })
            }
            (true, false) if !raw.items.is_empty() && raw.env.is_empty() && !query_only => Action::Items(raw.items),
            _ => return Err("a route needs exactly one of exec, sql, or [[route.item]]s alone; env goes with exec, \
                             and empty_sql, cache_copy, populate, refresh_every and error with sql"
                .into()),
        };
        Ok(Self { matcher, action })
    }
}

impl Matcher {
    /// The runtime values a match binds, `{query}` always among them.
    fn matches(&self, query: &str) -> Option<BTreeMap<String, Value>> {
        let mut bindings = BTreeMap::from([("query".to_owned(), Value::from(query))]);
        match self {
            Self::Pattern(regex) => {
                let captures = regex.captures(query)?;
                for (i, name) in regex.capture_names().enumerate() {
                    let value = Value::from(captures.get(i).map_or("", |m| m.as_str()));
                    if let Some(name) = name {
                        bindings.insert(name.to_owned(), value.clone());
                    }
                    bindings.insert(i.to_string(), value);
                }
            }
            Self::Keywords(keywords) => {
                let (word, rest) = split_word(query);
                let (keyword, value) = keywords
                    .iter()
                    .find(|(k, _)| k.eq_ignore_ascii_case(word))?;
                bindings.insert("keyword".into(), Value::from(keyword.as_str()));
                bindings.insert("value".into(), Value::from(value.as_str()));
                bindings.insert("rest".into(), Value::from(rest));
            }
        }
        Some(bindings)
    }
}

/// What a matched route does, rendered for one query.
#[derive(Debug)]
pub(crate) enum RouteAction<'a> {
    Exec {
        argv: Vec<String>,
        env: BTreeMap<String, String>,
    },
    Items(Vec<ItemBuilder>),
    Query(Box<QueryPlan<'a>>),
}

/// Every `[[route]]`, first match wins.
pub(crate) struct Routes {
    pub routes: Vec<Route>,
    pub vars: Table,
}

impl Routes {
    /// The first matching route, rendered for `query`.
    pub fn action(&self, query: &str) -> Option<Result<RouteAction<'_>>> {
        self.routes.iter().enumerate().find_map(|(index, route)| {
            let captured = route.matcher.matches(query)?;
            Some(self.render(index, route, query, captured))
        })
    }

    fn render<'a>(
        &'a self,
        index: usize,
        route: &'a Route,
        query: &str,
        captured: BTreeMap<String, Value>,
    ) -> Result<RouteAction<'a>> {
        let none = BTreeMap::new();
        let scope = Scope {
            vars: &self.vars,
            bindings: &none,
            literals: &captured,
        };
        Ok(match &route.action {
            Action::Exec { argv, env } => RouteAction::Exec {
                argv: argv
                    .iter()
                    .map(|arg| scope.render(arg))
                    .collect::<Result<_>>()?,
                env: env
                    .iter()
                    .map(|(k, v)| Ok((k.clone(), scope.render(v)?)))
                    .collect::<Result<_>>()?,
            },
            Action::Items(items) => RouteAction::Items(expand(items, &self.vars, &captured)?),
            Action::Query(spec) => {
                let params = Params::new(
                    captured
                        .get("rest")
                        .and_then(Value::as_str)
                        .unwrap_or(query),
                );
                let sql = spec
                    .empty_sql
                    .as_ref()
                    .filter(|_| params.is_empty())
                    .unwrap_or(&spec.sql);
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
                RouteAction::Query(Box::new(QueryPlan {
                    db: expand_home(&scope.render(&spec.db)?),
                    sql: sql_scope.render(sql)?,
                    route: index,
                    spec,
                    vars: &self.vars,
                    params,
                    literals: captured,
                }))
            }
        })
    }

    /// The spinner while a missing database builds in the background, else `None`. A stale
    /// database is rebuilt in the background while it keeps answering.
    async fn prepare(plan: &QueryPlan<'_>) -> Option<Menu> {
        let populate = plan.spec.populate.as_ref()?;
        let job = populate_job(&plan.db);
        let args = [
            POPULATE_COMMAND.into(),
            plan.route.to_string().into(),
            plan.db.clone().into_os_string(),
        ];
        let Ok(meta) = tokio::fs::metadata(&plan.db).await else {
            let started = job.start(args, BUILD_RETRY, BUILDING).await;
            let status = job
                .status()
                .await
                .unwrap_or_else(|| Status::running(BUILDING));
            // A failed build shows its error; it's retried once BUILD_RETRY has passed.
            return Some(if status.running || started {
                status.menu("Results appear when it's done")
            } else {
                Menu::from_iter([Item::message(&plan.spec.error, status.message)])
            });
        };
        let age = meta
            .modified()
            .ok()
            .and_then(|m| SystemTime::now().duration_since(m).ok())
            .unwrap_or_default();
        if let Some(every) = populate.every
            && age >= every
        {
            job.start(args, every, "Refreshing the index").await;
        }
        None
    }

    async fn query(plan: QueryPlan<'_>, ctx: &Context) -> Menu {
        if let Some(building) = Self::prepare(&plan).await {
            return building;
        }
        let error = plan.spec.error.clone();
        match plan.run().await {
            Ok(items) => ctx.live(items).await.or_message("No matches"),
            Err(e) => Menu::from_iter([Item::message(error, e.to_string())]),
        }
    }
}

/// Progress of building `db`, shown while queries wait for it.
fn populate_job(db: &Path) -> Job {
    Job::at(with_suffix(db, ".populate.json"))
}

impl Feature for Routes {
    fn command<'a>(
        &'a self,
        ctx: &'a Context,
        args: &'a [String],
    ) -> Option<BoxFuture<'a, Result<After>>> {
        let [command, route, db] = args else {
            return None;
        };
        (command == POPULATE_COMMAND).then(|| {
            async move {
                let populate = route
                    .parse::<usize>()
                    .ok()
                    .and_then(|i| self.routes.get(i))
                    .and_then(|r| match &r.action {
                        Action::Query(spec) => spec.populate.as_ref(),
                        _ => None,
                    })
                    .ok_or(Error::Usage("db-populate <route> <db>"))?;
                let job = populate_job(Path::new(db));
                let _ = job.report(&Status::running(BUILDING)).await;
                match populate::build(&populate.with, Path::new(db), &ctx.populators).await {
                    Ok(()) => {
                        job.clear().await;
                        Ok(After::Exit)
                    }
                    Err(e) => {
                        let _ = job.report(&Status::finished(e.to_string())).await;
                        Err(e)
                    }
                }
            }
            .boxed()
        })
    }

    fn answer<'a>(
        &'a self,
        ctx: &'a Context,
        query: &'a str,
    ) -> Option<BoxFuture<'a, Result<Menu>>> {
        let action = self.action(query)?;
        Some(
            async move {
                match action? {
                    RouteAction::Exec { argv, env } => {
                        let (program, args) = argv
                            .split_first()
                            .ok_or(Error::Config("empty route exec".into()))?;
                        Err(std::process::Command::new(program)
                            .args(args)
                            .envs(env)
                            .exec()
                            .into())
                    }
                    RouteAction::Items(items) => Ok(ctx.live(items).await),
                    RouteAction::Query(plan) => Ok(Self::query(*plan, ctx).await),
                }
            }
            .boxed(),
        )
    }
}

/// Every item, once per `each` combination, with `literals` bound verbatim.
pub(crate) fn expand(
    items: &[ItemConfig],
    vars: &Table,
    literals: &BTreeMap<String, Value>,
) -> Result<Vec<ItemBuilder>> {
    let mut out = Vec::new();
    for item in items {
        out.extend(item.expand(vars, literals)?);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use super::*;
    use crate::cache::cache_dir;
    use crate::{Config, Icons};

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

    fn routes(config: &Config) -> Routes {
        Routes {
            routes: config.routes.clone(),
            vars: config.vars.clone(),
        }
    }

    #[test]
    fn routes_keywords_and_patterns() {
        let config: Config = EXAMPLE.parse().unwrap();
        let routes = routes(&config);
        let Some(RouteAction::Exec { argv, env }) =
            routes.action("RX metformin 500").transpose().unwrap()
        else {
            panic!()
        };
        assert_eq!(&argv[4..], ["rxnorm", "metformin 500"]);
        assert_eq!(env["prefix"], "copy:");
        let Some(RouteAction::Items(items)) = routes.action("clr1234567890").transpose().unwrap()
        else {
            panic!()
        };
        assert_eq!(items[0].title, "Open CLR-1234567890");
        assert!(routes.action("github").transpose().unwrap().is_none());
    }

    #[test]
    fn rejects_bad_routes() {
        for bad in [
            "[[route]]\npattern = '('",
            "[[route]]\nexec = ['x']",
            "[[route]]\nkeywords = { a = '' }",
            "[[route]]\nkeywords = { a = '' }\nexec = ['x']\nsql = 'select 1'",
            "[[route]]\nkeywords = { a = '' }\nsql = 'select 1'\n[[route.item]]\ntitle = 'x'\narg = 'x'",
            "[[route]]\nkeywords = { a = '' }\nexec = ['x']\nerror = 'nope'",
            "[[route]]\nkeywords = { a = '' }\ndb = 'a.db'\nsql = 'select 1'\nrefresh_every = 60\n[[route.item]]\ntitle = 'x'\narg = 'x'",
        ] {
            assert!(bad.parse::<Config>().is_err(), "{bad}");
        }
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
        let routes = routes(config);
        let Some(RouteAction::Query(plan)) = routes.action(text).transpose()? else {
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
}
