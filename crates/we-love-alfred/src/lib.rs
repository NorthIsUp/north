#![doc = include_str!("../README.md")]

mod cache;
mod cleanup;
mod config;
pub mod editor;
mod error;
mod feature;
pub mod github;
mod icons;
mod item;
pub mod job;
mod menu;
pub mod okta;
mod populate;
mod query;
mod route;
pub mod shell;
mod sources;
pub mod tailscale;
mod template;
pub mod update;
mod workflow;

pub use cache::{Cache, cache_dir};
pub use config::{Config, Exec, IconSpec, ItemAction, ItemConfig};
pub use error::{Error, Result};
pub use feature::{After, Context, Feature};
pub use icons::{IconPack, IconSource, Icons};
pub use item::ItemBuilder;
pub use job::{Job, Status};
pub use menu::{Icon, IconType, Item, Menu, MenuCache, Modifier, Text};
pub use populate::{DataSource, Origin, Populate, Populator};
pub use route::Route;
pub use sources::Sources;
pub use workflow::Workflow;

/// Serializes tests that spawn processes: a child forked by another test thread
/// briefly inherits open fds, so a held refresh lock looks taken.
#[cfg(test)]
pub(crate) async fn serial() -> tokio::sync::MutexGuard<'static, ()> {
    static LOCK: tokio::sync::Mutex<()> = tokio::sync::Mutex::const_new(());
    LOCK.lock().await
}
