#![doc = include_str!("../README.md")]

pub mod cleanup;
pub mod editor;
mod error;
pub mod fast;
pub mod github;
mod menu;
pub mod okta;
mod shell;
pub mod workflow;

pub use error::{Error, Result};
pub use menu::{Icon, IconType, Menu, MenuCache, MenuItem, Modifier, Text};
pub use workflow::{IconSource, Item, Workflow};

/// Serializes tests that spawn processes: a child forked by another test thread
/// briefly inherits open fds, so a held refresh lock looks taken.
#[cfg(test)]
pub(crate) fn serial() -> std::sync::MutexGuard<'static, ()> {
    static LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
    LOCK.lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
}
