#![doc = include_str!("../README.md")]

mod cache;
mod cleanup;
mod config;
pub mod editor;
mod error;
pub mod github;
mod icons;
mod item;
mod menu;
pub mod okta;
mod pack;
mod query;
pub mod shell;
pub mod tailscale;
mod template;
pub mod update;
mod workflow;

pub use cache::{Cache, cache_dir};
pub use config::Config;
pub use error::{Error, Result};
pub use icons::{IconPack, IconSource, Icons};
pub use item::ItemBuilder;
pub use menu::{Icon, IconType, Item, Menu, MenuCache, Modifier, Text};
pub use query::QueryPlan;
pub use workflow::{Provider, Workflow};

/// Serializes tests that spawn processes: a child forked by another test thread
/// briefly inherits open fds, so a held refresh lock looks taken.
#[cfg(test)]
pub(crate) async fn serial() -> tokio::sync::MutexGuard<'static, ()> {
    static LOCK: tokio::sync::Mutex<()> = tokio::sync::Mutex::const_new(());
    LOCK.lock().await
}
