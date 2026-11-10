//! The pieces a [`crate::Workflow`] is assembled from: config routes and items, the built-in
//! integrations, and Rust handlers all implement [`Feature`].

use std::collections::BTreeMap;

use futures_util::future::{self, BoxFuture, FutureExt};

use crate::populate::Populator;
use crate::{Icons, ItemBuilder, Menu, Result};

/// What the runner does once an internal command finishes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum After {
    Exit,
    /// Rebuild and print the menu, e.g. once a login has made new items available.
    Rebuild,
}

/// State shared by every feature during one invocation.
pub struct Context {
    pub icons: Icons,
    pub(crate) populators: BTreeMap<String, Populator>,
}

impl Context {
    /// A menu for a live answer: it depends on the query, so Alfred must not cache it.
    pub async fn live(&self, items: Vec<ItemBuilder>) -> Menu {
        Menu {
            cache: None,
            ..Menu::build(items, &self.icons).await
        }
    }
}

/// One part of a workflow. Every method defaults to doing nothing.
///
/// Deciding whether a command or query is yours is synchronous; the work happens in the future.
pub trait Feature: Send + Sync {
    /// Handle an internal command, such as a detached refresh, when `args[0]` is yours.
    fn command<'a>(
        &'a self,
        _ctx: &'a Context,
        _args: &'a [String],
    ) -> Option<BoxFuture<'a, Result<After>>> {
        None
    }

    /// Answer `query` live, bypassing the cached menu, when it's yours.
    fn answer<'a>(
        &'a self,
        _ctx: &'a Context,
        _query: &'a str,
    ) -> Option<BoxFuture<'a, Result<Menu>>> {
        None
    }

    /// Items for the full, cached menu.
    fn items<'a>(&'a self, _ctx: &'a Context) -> BoxFuture<'a, Result<Vec<ItemBuilder>>> {
        future::ready(Ok(Vec::new())).boxed()
    }

    /// Quick, throttled upkeep on every keystroke, such as starting a background refresh.
    fn background<'a>(&'a self, _ctx: &'a Context) -> BoxFuture<'a, ()> {
        future::ready(()).boxed()
    }
}

/// The first word of `query` and the trimmed rest.
pub(crate) fn split_word(query: &str) -> (&str, &str) {
    let (word, rest) = query.split_once(char::is_whitespace).unwrap_or((query, ""));
    (word, rest.trim())
}

/// Answers queries starting with `keyword`; the handler gets the rest.
pub(crate) struct Keyword<F> {
    pub keyword: String,
    pub handler: F,
}

impl<F, Fut> Feature for Keyword<F>
where
    F: Fn(String) -> Fut + Send + Sync,
    Fut: Future<Output = Result<Menu>> + Send + 'static,
{
    fn answer<'a>(
        &'a self,
        _ctx: &'a Context,
        query: &'a str,
    ) -> Option<BoxFuture<'a, Result<Menu>>> {
        let (word, rest) = split_word(query);
        word.eq_ignore_ascii_case(&self.keyword)
            .then(|| (self.handler)(rest.to_owned()).boxed())
    }
}

/// Adds the items a closure returns to the full menu.
pub(crate) struct Provider<F>(pub F);

impl<F, Fut> Feature for Provider<F>
where
    F: Fn() -> Fut + Send + Sync,
    Fut: Future<Output = Result<Vec<ItemBuilder>>> + Send + 'static,
{
    fn items<'a>(&'a self, _ctx: &'a Context) -> BoxFuture<'a, Result<Vec<ItemBuilder>>> {
        (self.0)().boxed()
    }
}

/// Fixed items, such as the config's expanded `[[item]]`s.
pub(crate) struct Items(pub Vec<ItemBuilder>);

impl Feature for Items {
    fn items<'a>(&'a self, _ctx: &'a Context) -> BoxFuture<'a, Result<Vec<ItemBuilder>>> {
        future::ready(Ok(self.0.clone())).boxed()
    }
}
