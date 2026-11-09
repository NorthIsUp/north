use std::io;

/// Everything this crate can fail with.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    #[error(transparent)]
    Toml(#[from] toml::de::Error),
    #[error(transparent)]
    Regex(#[from] regex::Error),
    #[error(transparent)]
    Http(#[from] reqwest::Error),
    #[error("invalid config: {0}")]
    Config(String),
    #[error("template {template:?}: unknown variable {name:?}")]
    Template { template: String, name: String },
    #[error("cache name must be a filename without directory separators: {0:?}")]
    InvalidCacheName(String),
    #[error("{program} failed: {stderr}")]
    Command { program: String, stderr: String },
    #[error("{0} timed out")]
    Timeout(String),
    #[error("usage: {0}")]
    Usage(&'static str),
    #[error("Okta is not configured: set org and a client ID")]
    OktaNotConfigured,
    #[error("Okta OAuth error: {0}")]
    OktaOAuth(String),
    #[error("could not save the Okta refresh token in Keychain")]
    Keychain,
    #[error("could not open {0}")]
    Open(String),
}

pub type Result<T, E = Error> = std::result::Result<T, E>;
