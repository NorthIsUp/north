use std::io;

/// Everything this crate can fail with.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    #[error(transparent)]
    Http(#[from] ureq::Error),
    #[error("HTTP status {0}")]
    HttpStatus(u16),
    #[error("cache name must be a filename without directory separators: {0:?}")]
    InvalidCacheName(String),
    #[error("{program} failed: {stderr}")]
    Command { program: String, stderr: String },
    #[error("{0} timed out")]
    Timeout(String),
    #[error("no source files provided")]
    NoSourceFiles,
    #[error("usage: {0}")]
    Usage(&'static str),
    #[error("Okta is not configured: set org and a client ID")]
    OktaNotConfigured,
    #[error("Okta OAuth error: {0}")]
    OktaOAuth(String),
    #[error("could not save the Okta refresh token in Keychain")]
    Keychain,
    #[error("could not open the Okta authorization page")]
    Browser,
}

pub type Result<T, E = Error> = std::result::Result<T, E>;
