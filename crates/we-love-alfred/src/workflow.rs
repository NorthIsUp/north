//! Run a Script Filter: route the query, serve the cache, rebuild in the background.

use std::collections::BTreeMap;
use std::env;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;
use std::time::SystemTime;

use futures_util::future::{self, BoxFuture, FutureExt};
use regex::Regex;
use tokio::process::Command;

use crate::cache::{spawn_throttled, with_suffix};
use crate::config::RouteAction;
use crate::populate::{self, Populator};
use crate::{
    Cache, Config, Error, Icons, Item, ItemBuilder, Menu, QueryPlan, Result, github, okta, update,
};

/// A bare PR number, optionally after `pr`.
static PR_NUMBER: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)^(?:pr\s*)?(\d{1,6})$").expect("valid regex"));

/// Rebuilds a query route's database: `db-populate <route index> <db>`.
pub const POPULATE_COMMAND: &str = "db-populate";

/// Skips the cache and rebuilds; passed to background refreshes.
pub const NO_CACHE: &str = "--no-cache";

/// Contributes items to the full menu, concurrently with the others.
pub trait Provider: Send + Sync {
    fn items(&self) -> BoxFuture<'_, Result<Vec<ItemBuilder>>>;
}

impl<F, Fut> Provider for F
where
    F: Fn() -> Fut + Send + Sync,
    Fut: Future<Output = Result<Vec<ItemBuilder>>> + Send + 'static,
{
    fn items(&self) -> BoxFuture<'_, Result<Vec<ItemBuilder>>> {
        self().boxed()
    }
}

type Handler = Box<dyn Fn(String) -> BoxFuture<'static, Result<Menu>> + Send + Sync>;

/// A Script Filter built from a [`Config`] plus any Rust [`Provider`]s and keyword handlers.
///
/// ```no_run
/// use we_love_alfred::{Item, Menu, Workflow};
///
/// #[tokio::main(flavor = "current_thread")]
/// async fn main() -> we_love_alfred::Result<()> {
///     Workflow::load("workflow.toml")
///         .await?
///         .provider(|| async { Ok(vec![Item::url("Status", "https://status.example.com")]) })
///         .keyword("deploy", |query| async move { Ok(Menu::default().or_message(&format!("deploying {query}"))) })
///         .run(std::env::args().skip(1))
///         .await
/// }
/// ```
pub struct Workflow {
    config: Config,
    cache: Cache,
    icons: Icons,
    providers: Vec<Box<dyn Provider>>,
    keywords: Vec<(String, Handler)>,
    populators: BTreeMap<String, Populator>,
}

impl Workflow {
    /// A workflow for `config`, caching under its `cache` name or the bundle ID.
    ///
    /// # Errors
    ///
    /// [`Error::InvalidCacheName`] when neither gives a valid cache name.
    pub fn new(config: Config) -> Result<Self> {
        let cache = match &config.cache {
            Some(name) => Cache::named(name)?,
            None => Cache::for_workflow()?,
        };
        let icons = Icons::default().with_packs(config.icon_packs.clone());
        Ok(Self {
            config,
            cache,
            icons,
            providers: Vec::new(),
            keywords: Vec::new(),
            populators: BTreeMap::new(),
        })
    }

    /// [`Workflow::new`] for the config at `path`.
    ///
    /// # Errors
    ///
    /// The errors of [`Config::load`] and [`Workflow::new`].
    pub async fn load(path: impl AsRef<Path>) -> Result<Self> {
        Self::new(Config::load(path).await?)
    }

    #[must_use]
    pub fn icons(mut self, icons: Icons) -> Self {
        self.icons = icons.with_packs(self.config.icon_packs.clone());
        self
    }

    #[must_use]
    pub fn cache(mut self, cache: Cache) -> Self {
        self.cache = cache;
        self
    }

    /// Add items to the full (cached) menu.
    #[must_use]
    pub fn provider(mut self, provider: impl Provider + 'static) -> Self {
        self.providers.push(Box::new(provider));
        self
    }

    /// Answer queries starting with `keyword` live, bypassing the cache; the handler gets the rest.
    #[must_use]
    pub fn keyword<F, Fut>(mut self, keyword: impl Into<String>, handler: F) -> Self
    where
        F: Fn(String) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<Menu>> + Send + 'static,
    {
        self.keywords
            .push((keyword.into(), Box::new(move |rest| handler(rest).boxed())));
        self
    }

    /// Register `function` under `name` for query routes with `populate = "<name>"`: it gets a
    /// path and must write the complete database there.
    #[must_use]
    pub fn populate<F, Fut>(mut self, name: impl Into<String>, function: F) -> Self
    where
        F: Fn(PathBuf) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<()>> + Send + 'static,
    {
        self.populators
            .insert(name.into(), Box::new(move |db| function(db).boxed()));
        self
    }

    /// Handle one Script Filter invocation; `args` excludes the program name.
    ///
    /// # Errors
    ///
    /// Config and template errors, a failing internal command (`github-refresh`, `okta-login`, `self-update`), a route whose `exec` can't start, and I/O errors writing the cache.
    pub async fn run(&self, args: impl IntoIterator<Item = String>) -> Result<()> {
        let mut args: Vec<String> = args.into_iter().collect();
        if let Some(result) = github::dispatch(&args).await {
            return result;
        }
        let mut rebuild = false;
        match args.first().map(String::as_str) {
            Some(update::CHECK_COMMAND | update::FORCE_COMMAND) => {
                let updater = self
                    .config
                    .update
                    .as_ref()
                    .ok_or(Error::Config("no [update] table".into()))?;
                return updater.run(args[0] == update::FORCE_COMMAND).await;
            }
            Some(okta::LOGIN_COMMAND) => {
                self.config
                    .okta
                    .as_ref()
                    .ok_or(Error::Config("no [okta] table".into()))?
                    .login()
                    .await?;
                rebuild = true;
            }
            Some(POPULATE_COMMAND) => {
                let [_, route, db] = args.as_slice() else {
                    return Err(Error::Usage("db-populate <route> <db>"));
                };
                let populate = route
                    .parse::<usize>()
                    .ok()
                    .and_then(|i| self.config.routes.get(i))
                    .and_then(|r| r.populate.as_ref())
                    .ok_or(Error::Usage("db-populate <route> <db>"))?;
                return populate::build(populate, Path::new(db), &self.populators).await;
            }
            Some(NO_CACHE) => rebuild = true,
            _ => {}
        }
        if rebuild {
            args.remove(0);
        }
        let query = args.join(" ").trim().to_owned();
        if !rebuild && let Some(menu) = self.answer_live(&query).await? {
            println!("{menu}");
            return Ok(());
        }
        let menu = match self.cache.read().await {
            Some(menu) if !rebuild => {
                self.cache
                    .refresh(Command::new(env::current_exe()?).arg(NO_CACHE))
                    .await;
                menu
            }
            _ => {
                let menu = self.build().await?;
                self.cache.write(&menu).await?;
                menu
            }
        };
        println!("{}", menu.filter(&query));
        Ok(())
    }

    /// Build a missing database now; rebuild a stale one in the background.
    async fn prepare_db(&self, plan: &QueryPlan) -> Result<()> {
        let Some(populate) = &plan.populate else {
            return Ok(());
        };
        let Ok(meta) = tokio::fs::metadata(&plan.db).await else {
            return populate::build(populate, &plan.db, &self.populators).await;
        };
        let age = meta
            .modified()
            .ok()
            .and_then(|m| SystemTime::now().duration_since(m).ok())
            .unwrap_or_default();
        if let Some(every) = plan.refresh_every
            && age >= every
        {
            let mut command = Command::new(env::current_exe()?);
            command
                .arg(POPULATE_COMMAND)
                .arg(plan.route.to_string())
                .arg(&plan.db);
            spawn_throttled(&mut command, &with_suffix(&plan.db, ".populate.pid"), every).await;
        }
        Ok(())
    }

    /// A live answer: it depends on the query, so Alfred must not cache it.
    async fn live(&self, items: Vec<ItemBuilder>) -> Menu {
        Menu {
            cache: None,
            ..Menu::build(items, &self.icons).await
        }
    }

    /// Routes, keyword handlers, the update view and PR searches; `None` falls through to the menu.
    async fn answer_live(&self, query: &str) -> Result<Option<Menu>> {
        match self.config.route(query)? {
            Some(RouteAction::Exec { argv, env }) => {
                let (program, args) = argv
                    .split_first()
                    .ok_or(Error::Config("empty route exec".into()))?;
                return Err(std::process::Command::new(program)
                    .args(args)
                    .envs(env)
                    .exec()
                    .into());
            }
            Some(RouteAction::Items(items)) => return Ok(Some(self.live(items).await)),
            Some(RouteAction::Query(plan)) => {
                let title = plan.error.clone().unwrap_or_else(|| "Query failed".into());
                let ran = match self.prepare_db(&plan).await {
                    Ok(()) => plan.run().await,
                    Err(e) => Err(e),
                };
                return Ok(Some(match ran {
                    Ok(items) => self.live(items).await.or_message("No matches"),
                    Err(e) => Menu::from_iter([Item::message(title, e.to_string())]),
                }));
            }
            None => {}
        }
        let (word, rest) = query.split_once(char::is_whitespace).unwrap_or((query, ""));
        if let Some((_, handler)) = self
            .keywords
            .iter()
            .find(|(k, _)| k.eq_ignore_ascii_case(word))
        {
            return handler(rest.trim().to_owned()).await.map(Some);
        }
        if let Some(updater) = &self.config.update {
            if query.eq_ignore_ascii_case(&updater.keyword) {
                return updater.view().await.map(Some);
            }
            updater.check_in_background().await;
        }
        let Some(github) = &self.config.github else {
            return Ok(None);
        };
        let prs = github.cache();
        let empty = if prs.path.exists() {
            "No matching open PRs"
        } else {
            "Loading open PRs…"
        };
        if word.eq_ignore_ascii_case(&github.keyword) {
            return Ok(Some(
                Menu::from_iter(prs.search_items(rest, &github.keyword).await).or_message(empty),
            ));
        }
        if let Some(needle) = query.strip_prefix('#') {
            return Ok(Some(
                Menu::from_iter(prs.number_items(needle).await).or_message(empty),
            ));
        }
        prs.warm().await;
        if let Some(number) = PR_NUMBER.captures(query).and_then(|c| c[1].parse().ok()) {
            return Ok(Some(Menu::from_iter([prs.link_item(number)])));
        }
        Ok(None)
    }

    /// The full menu: config items, built-in sections and providers, gathered concurrently.
    ///
    /// A failing provider is logged and skipped, so one outage can't blank the menu.
    ///
    /// # Errors
    ///
    /// Template or config errors in the `[[item]]`s.
    pub async fn build(&self) -> Result<Menu> {
        let config = &self.config;
        let mut sources: Vec<BoxFuture<'_, Result<Vec<ItemBuilder>>>> =
            vec![config.source_items().boxed()];
        if let Some(okta) = &config.okta {
            sources.push(okta.items().boxed());
        }
        if let Some(tailscale) = &config.tailscale {
            sources.push(tailscale.items().boxed());
        }
        sources.extend(self.providers.iter().map(|p| p.items()));
        let mut items = config.items()?;
        let results = future::join_all(sources).await;
        for result in results {
            match result {
                Ok(more) => items.extend(more),
                Err(e) => log::warn!("menu provider failed: {e}"),
            }
        }
        items.push(self.cache.clear_item(&self.icons));
        Ok(Menu::build(items, &self.icons).await)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Item;

    #[tokio::test]
    async fn builds_config_providers_and_clear_item_and_survives_failures() {
        let config: Config = "cache = 'test'\n[[item]]\ntitle = 'Static'\narg = 'x'"
            .parse()
            .unwrap();
        let workflow = Workflow::new(config)
            .unwrap()
            .icons(Icons::new("/nonexistent"))
            .provider(|| async { Ok(vec![Item::arg("Dynamic", "y")]) })
            .provider(|| async { Err(Error::Config("down".into())) });
        let titles: Vec<String> = workflow
            .build()
            .await
            .unwrap()
            .items
            .into_iter()
            .map(|i| i.title)
            .collect();
        assert_eq!(titles, ["Static", "Dynamic", "clear cache"]);
    }

    #[tokio::test]
    async fn query_routes_populate_missing_databases() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path().join("people.json"),
            r#"{"people": [{"name": "Ada", "role": "eng"}, {"name": "Grace", "role": "admiral"}]}"#,
        )
        .unwrap();
        let config: Config = format!(
            r#"
            cache = "test"
            [[route]]
            keywords = {{ who = "" }}
            db = "{dir}/people.db"
            sql = "select name, role from people where people match :fts"
            error = "People search failed"
            populate = {{ file = "{dir}/people.json", jq = ".people[]", table = "people", fts = true }}
            [[route.item]]
            title = "{{name}}"
            subtitle = "{{role}}"
            arg = "{{name}}"

            [[route]]
            keywords = {{ fn = "" }}
            db = "{dir}/fn.db"
            sql = "select x from t"
            populate = "numbers"
            [[route.item]]
            title = "{{x}}"
            arg = "{{x}}"

            [[route]]
            keywords = {{ broken = "" }}
            db = "{dir}/broken.db"
            sql = "select 1"
            error = "Broken search failed"
            populate = "missing-function"
            [[route.item]]
            title = "x"
            arg = "x"
            "#,
            dir = dir.path().display()
        )
        .parse()
        .unwrap();
        let workflow = Workflow::new(config)
            .unwrap()
            .icons(Icons::new("/nonexistent"))
            .populate("numbers", |db: PathBuf| async move {
                rusqlite::Connection::open(db)?
                    .execute_batch("create table t(x); insert into t values (42);")?;
                Ok(())
            });
        let titles = |menu: Option<Menu>| {
            menu.unwrap()
                .items
                .into_iter()
                .map(|i| i.title)
                .collect::<Vec<_>>()
        };
        assert_eq!(
            titles(workflow.answer_live("who grace").await.unwrap()),
            ["Grace"]
        );
        assert!(
            dir.path().join("people.db").exists(),
            "built from file + jq"
        );
        assert_eq!(titles(workflow.answer_live("fn").await.unwrap()), ["42"]);
        let broken = workflow.answer_live("broken").await.unwrap().unwrap();
        assert_eq!(broken.items[0].title, "Broken search failed");
        assert!(
            broken.items[0].subtitle.contains("missing-function"),
            "{}",
            broken.items[0].subtitle
        );
        assert!(
            workflow
                .run([
                    "db-populate".to_owned(),
                    "1".to_owned(),
                    dir.path().join("again.db").display().to_string()
                ])
                .await
                .is_ok()
        );
        assert!(
            dir.path().join("again.db").exists(),
            "the background rebuild command"
        );
    }

    #[tokio::test]
    async fn keywords_and_routes_answer_live() {
        let config: Config = "cache = 'test'\n[[route]]\npattern = '^go (.+)$'\n[[route.item]]\ntitle = 'Go {1}'\narg = '{1}'"
            .parse()
            .unwrap();
        let workflow = Workflow::new(config)
            .unwrap()
            .icons(Icons::new("/nonexistent"))
            .keyword("deploy", |rest| async move {
                Ok(Menu::from_iter([Item::message(
                    format!("deploy {rest}"),
                    "",
                )]))
            });
        let titles = |menu: Option<Menu>| {
            menu.unwrap()
                .items
                .into_iter()
                .map(|i| i.title)
                .collect::<Vec<_>>()
        };
        assert_eq!(
            titles(workflow.answer_live("Deploy  main").await.unwrap()),
            ["deploy main"]
        );
        assert_eq!(
            titles(workflow.answer_live("go home").await.unwrap()),
            ["Go home"]
        );
        assert!(
            workflow
                .answer_live("anything else")
                .await
                .unwrap()
                .is_none()
        );
    }
}
