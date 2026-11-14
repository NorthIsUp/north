//! Run a Script Filter: internal commands, live answers, then the cached menu.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use futures_util::future::{self, BoxFuture, FutureExt};

use crate::cache::wants_clear;
use crate::feature::{After, Context, Feature, Items, Keyword, Provider};
use crate::route::Routes;
use crate::{Cache, Config, Icons, ItemBuilder, Menu, Result};

/// Skips the cache and rebuilds; passed to background refreshes.
pub const NO_CACHE: &str = "--no-cache";

/// A Script Filter assembled from a [`Config`] and any Rust [`Feature`]s.
///
/// Features answer in order: updates (alone or after any keyword, so routes never hide them), the
/// config's routes, yours, then the built-in integrations. Any answer gains a "clear cache" row when
/// the query fuzzily names it (`py clear`, `py cache`).
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
    cache: Cache,
    /// `[update] clear_cache`: clear every cache once per new workflow version.
    clear_on_update: bool,
    ctx: Context,
    packs: BTreeMap<String, crate::IconPack>,
    /// Every workflow's own commands (updates), answered before anything else.
    system: Vec<Box<dyn Feature>>,
    /// The config's routes and `[[item]]`s.
    declared: Vec<Box<dyn Feature>>,
    custom: Vec<Box<dyn Feature>>,
    builtin: Vec<Box<dyn Feature>>,
}

impl Workflow {
    /// A workflow for `config`, caching under its `cache` name or the bundle ID.
    ///
    /// # Errors
    ///
    /// [`crate::Error::InvalidCacheName`] when neither gives a valid cache name, and
    /// [`crate::Error::Template`] for an unknown variable in the `[[item]]`s or `[sources]`.
    pub fn new(config: Config) -> Result<Self> {
        let cache = match &config.cache {
            Some(name) => Cache::named(name)?,
            None => Cache::for_workflow()?,
        };
        let items = config.items()?;
        let Config {
            vars,
            routes,
            github,
            update,
            okta,
            tailscale,
            sources,
            icon_packs,
            ..
        } = config;
        let mut builtin: Vec<Box<dyn Feature>> = Vec::new();
        if let Some(sources) = sources {
            builtin.push(Box::new(sources.render(&vars)?));
        }
        builtin.extend(okta.map(|f| Box::new(f) as Box<dyn Feature>));
        builtin.extend(tailscale.map(|f| Box::new(f) as Box<dyn Feature>));
        builtin.extend(github.map(|f| Box::new(f) as Box<dyn Feature>));
        Ok(Self {
            cache,
            clear_on_update: update.as_ref().is_some_and(|u| u.clear_cache),
            ctx: Context {
                icons: Icons::default().with_packs(icon_packs.clone()),
                populators: BTreeMap::new(),
            },
            packs: icon_packs,
            system: update
                .into_iter()
                .map(|f| Box::new(f) as Box<dyn Feature>)
                .collect(),
            declared: vec![Box::new(Routes { routes, vars }), Box::new(Items(items))],
            custom: Vec::new(),
            builtin,
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
        self.ctx.icons = icons.with_packs(self.packs.clone());
        self
    }

    #[must_use]
    pub fn cache(mut self, cache: Cache) -> Self {
        self.cache = cache;
        self
    }

    /// Add a feature; it answers after the config's routes and before the built-ins.
    #[must_use]
    pub fn feature(mut self, feature: impl Feature + 'static) -> Self {
        self.custom.push(Box::new(feature));
        self
    }

    /// Add the items `provider` returns to the full (cached) menu.
    #[must_use]
    pub fn provider<F, Fut>(self, provider: F) -> Self
    where
        F: Fn() -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<Vec<ItemBuilder>>> + Send + 'static,
    {
        self.feature(Provider(provider))
    }

    /// Answer queries starting with `keyword` live, bypassing the cache; the handler gets the rest.
    #[must_use]
    pub fn keyword<F, Fut>(self, keyword: impl Into<String>, handler: F) -> Self
    where
        F: Fn(String) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<Menu>> + Send + 'static,
    {
        self.feature(Keyword {
            keyword: keyword.into(),
            handler,
        })
    }

    /// Register `function` under `name` for query routes with `populate = "<name>"`: it gets a
    /// path and must write the complete database there.
    #[must_use]
    pub fn populate<F, Fut>(mut self, name: impl Into<String>, function: F) -> Self
    where
        F: Fn(PathBuf) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<()>> + Send + 'static,
    {
        self.ctx
            .populators
            .insert(name.into(), Box::new(move |db| function(db).boxed()));
        self
    }

    /// Updates, then the config's routes and items, then yours, then the
    /// built-in integrations.
    fn features(&self) -> impl Iterator<Item = &dyn Feature> {
        let system = self.system.iter().map(AsRef::as_ref);
        system.chain(
            self.declared
                .iter()
                .chain(&self.custom)
                .chain(&self.builtin)
                .map(AsRef::as_ref),
        )
    }

    /// Handle one Script Filter invocation; `args` excludes the program name.
    ///
    /// # Errors
    ///
    /// A failing internal command or live answer (including a route whose `exec` can't start),
    /// and I/O errors writing the cache.
    pub async fn run(&self, args: impl IntoIterator<Item = String>) -> Result<()> {
        let args: Vec<String> = args.into_iter().collect();
        if self.clear_on_update
            && let Ok(version) = std::env::var("alfred_workflow_version")
            && !version.is_empty()
            && let Err(e) = self
                .cache
                .clear_on_new_version(&self.ctx.icons, &version)
                .await
        {
            log::warn!("clearing caches for {version} failed: {e}");
        }
        let rebuild = match self.features().find_map(|f| f.command(&self.ctx, &args)) {
            Some(command) => match command.await? {
                After::Exit => return Ok(()),
                After::Rebuild => true,
            },
            None => args.first().is_some_and(|a| a == NO_CACHE),
        };
        let query = args[usize::from(rebuild)..].join(" ").trim().to_owned();
        if !rebuild {
            future::join_all(self.features().map(|f| f.background(&self.ctx))).await;
            if let Some(answer) = self.answer(&query) {
                println!("{}", answer.await?);
                return Ok(());
            }
        }
        let menu = match self.cache.read().await {
            Some(menu) if !rebuild => {
                self.cache.refresh([NO_CACHE]).await;
                menu
            }
            _ => {
                let menu = self.build().await;
                self.cache.write(&menu).await?;
                menu
            }
        };
        println!("{}", menu.filter(&query));
        Ok(())
    }

    /// The first feature's live answer, with "clear cache" appended when the query fuzzily names it.
    fn answer<'a>(&'a self, query: &'a str) -> Option<BoxFuture<'a, Result<Menu>>> {
        let answer = self.features().find_map(|f| f.answer(&self.ctx, query))?;
        Some(
            async move {
                let mut menu = answer.await?;
                if wants_clear(query) {
                    // A placeholder like "No matches" says nothing once the clear row is there.
                    menu.items.retain(|item| item.valid != Some(false));
                    let icons = &self.ctx.icons;
                    menu.items
                        .push(self.cache.clear_item(icons).build(icons).await);
                }
                Ok(menu)
            }
            .boxed(),
        )
    }

    /// The full menu: every feature's items, gathered concurrently, then "clear cache".
    ///
    /// A failing feature is logged and skipped, so one outage can't blank the menu.
    pub async fn build(&self) -> Menu {
        let mut items = Vec::new();
        for result in future::join_all(self.features().map(|f| f.items(&self.ctx))).await {
            match result {
                Ok(more) => items.extend(more),
                Err(e) => log::warn!("menu items failed: {e}"),
            }
        }
        items.push(self.cache.clear_item(&self.ctx.icons));
        Menu::build(items, &self.ctx.icons).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Error, Item};

    fn titles(menu: Option<Menu>) -> Vec<String> {
        menu.map(|m| m.items.into_iter().map(|i| i.title).collect())
            .unwrap_or_default()
    }

    /// The live answer, as `run` would print it.
    async fn answer(workflow: &Workflow, query: &str) -> Option<Menu> {
        Some(workflow.answer(query)?.await.unwrap())
    }

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
            .items
            .into_iter()
            .map(|i| i.title)
            .collect();
        assert_eq!(titles, ["Static", "Dynamic", "clear cache"]);
    }

    #[tokio::test]
    async fn query_routes_populate_missing_databases() {
        // Spawns background builds.
        let _serial = crate::serial().await;
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
        let populate = |route: &str, db: &str| {
            let db = dir.path().join(db).display().to_string();
            workflow.run(["db-populate".to_owned(), route.to_owned(), db])
        };
        // A missing database builds in the background while the query shows a spinner.
        let building = answer(&workflow, "who grace").await.unwrap();
        assert!(
            building.items[0].title.ends_with("Building the index"),
            "{building:?}"
        );
        assert_eq!(building.rerun, Some(crate::job::RERUN));
        populate("0", "people.db").await.unwrap();
        assert_eq!(
            titles(answer(&workflow, "who grace").await),
            ["Grace"],
            "built from file + jq"
        );
        populate("1", "fn.db").await.unwrap();
        assert_eq!(titles(answer(&workflow, "fn").await), ["42"]);
        // A failed build shows the route's error instead of spinning forever.
        answer(&workflow, "broken").await.unwrap();
        assert!(populate("2", "broken.db").await.is_err());
        let broken = answer(&workflow, "broken").await.unwrap();
        assert_eq!(broken.items[0].title, "Broken search failed");
        assert!(
            broken.items[0].subtitle.contains("missing-function"),
            "{}",
            broken.items[0].subtitle
        );
        assert_eq!(broken.rerun, None);
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
    async fn update_wins_over_routes_and_clear_cache_joins_them() {
        let _serial = crate::serial().await;
        let config: Config = r#"
            cache = "test"
            [update]
            repo = "owner/repo"
            asset = "x.alfredworkflow"
            [[route]]
            keywords = { py = "" }
            [[route.item]]
            title = "Search {rest}"
            arg = "{rest}"
        "#
        .parse()
        .unwrap();
        let workflow = Workflow::new(config)
            .unwrap()
            .icons(Icons::new("/nonexistent"));
        let update = answer(&workflow, "py update").await.unwrap();
        assert!(
            update.variables.contains_key("we_love_update_started"),
            "{update:?}"
        );
        for query in ["py clear", "py cache", "py cache clear", "py Clear Cache"] {
            assert_eq!(
                titles(answer(&workflow, query).await),
                [format!("Search {}", &query[3..]), "clear cache".into()]
            );
        }
        assert_eq!(titles(answer(&workflow, "py dict").await), ["Search dict"]);
        assert_eq!(
            titles(answer(&workflow, "py update dict").await),
            ["Search update dict"]
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
            titles(answer(&workflow, "Deploy  main").await),
            ["deploy main"]
        );
        assert_eq!(titles(answer(&workflow, "go home").await), ["Go home"]);
        assert!(answer(&workflow, "anything else").await.is_none());
    }
}
