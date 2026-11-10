//! Okta app tiles as Alfred items.
//!
//! Okta needs a public native OIDC app with the device authorization and
//! refresh token grants and the `okta.users.read.self` API scope granted.
//! Until the user connects, [`Okta::items`] yields one connect item running
//! `<binary> okta-login`, which [`crate::Workflow`] routes to [`Okta::login`].
//! The rotating refresh token lives in the macOS Keychain.

use std::future::Future;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;

use chrono::{DateTime, Utc};
use reqwest::{Client, Response, StatusCode};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Deserializer, Serialize};
use tokio::fs;
use tokio::io::AsyncWriteExt;
use tokio::process::Command;
use tokio::time::{Instant, sleep};

use crate::cache::{atomic_write, cache_dir};
use crate::shell::{join, output, tool};
use crate::{Error, IconSource, Item, ItemBuilder, Result};

/// The argument [`crate::Workflow`] routes to [`Okta::login`].
pub const LOGIN_COMMAND: &str = "okta-login";
const SCOPE: &str = "offline_access okta.users.read.self";
const DEVICE_GRANT: &str = "urn:ietf:params:oauth:grant-type:device_code";
/// RFC 8628 §3.5: `slow_down` adds five seconds to every later poll.
const SLOW_DOWN: Duration = Duration::from_secs(5);

/// Stores the Okta refresh token.
pub trait Keychain: Send + Sync {
    fn find(&self, service: &str, account: &str) -> impl Future<Output = Option<String>> + Send;
    fn store(
        &self,
        service: &str,
        account: &str,
        secret: &str,
    ) -> impl Future<Output = Result<()>> + Send;
}

/// The macOS login keychain via `/usr/bin/security`.
#[derive(Debug, Clone, Copy, Default)]
pub struct SecurityKeychain;

impl Keychain for SecurityKeychain {
    async fn find(&self, service: &str, account: &str) -> Option<String> {
        let mut command = Command::new("/usr/bin/security");
        command
            .args(["find-generic-password", "-s", service, "-a", account, "-w"])
            .stderr(Stdio::null());
        output(&mut command, Duration::from_secs(10))
            .await
            .ok()
            .map(|s| s.trim().to_owned())
    }

    /// The secret goes through `security -i` on stdin, so it never reaches argv.
    async fn store(&self, service: &str, account: &str, secret: &str) -> Result<()> {
        let mut child = Command::new("/usr/bin/security")
            .arg("-i")
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()?;
        let mut stdin = child.stdin.take().expect("piped stdin");
        stdin
            .write_all(add_password_line(service, account, secret).as_bytes())
            .await?;
        drop(stdin);
        if child.wait().await?.success() {
            Ok(())
        } else {
            Err(Error::Keychain)
        }
    }
}

fn add_password_line(service: &str, account: &str, secret: &str) -> String {
    join([
        "add-generic-password",
        "-U",
        "-s",
        service,
        "-a",
        account,
        "-w",
        secret,
    ]) + "\n"
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OktaAppLink {
    pub label: String,
    pub link_url: String,
    #[serde(default)]
    pub logo_url: String,
    pub app_name: String,
    #[serde(default)]
    pub hidden: bool,
}

/// The user's visible app tiles and when they were fetched.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OktaAppsCache {
    v: u8,
    /// Must carry a timezone; naive timestamps are rejected.
    pub fetched_at: DateTime<Utc>,
    pub links: Vec<OktaAppLink>,
}

impl OktaAppsCache {
    #[must_use]
    pub fn new(links: Vec<OktaAppLink>) -> Self {
        Self {
            v: 1,
            fetched_at: Utc::now(),
            links,
        }
    }

    /// `None` for a missing, malformed, or other-version cache.
    pub async fn load(path: &Path) -> Option<Self> {
        let cache: Self = serde_json::from_slice(&fs::read(path).await.ok()?).ok()?;
        (cache.v == 1).then_some(cache)
    }

    #[must_use]
    pub fn is_fresh(&self, ttl: Duration) -> bool {
        (Utc::now() - self.fetched_at)
            .to_std()
            .is_ok_and(|age| age < ttl)
    }

    /// Atomically write the cache to `path`.
    ///
    /// # Errors
    ///
    /// I/O errors creating the directory or writing the file.
    pub async fn save(&self, path: &Path) -> Result<()> {
        atomic_write(path, &serde_json::to_vec(self)?).await
    }
}

#[derive(Deserialize)]
struct DeviceCode {
    #[serde(rename = "device_code")]
    code: String,
    verification_uri_complete: String,
    expires_in: u64,
    #[serde(default = "default_interval")]
    interval: u64,
}

fn default_interval() -> u64 {
    5
}

#[derive(Deserialize)]
struct OAuthError {
    error: String,
}

#[derive(Deserialize)]
struct Tokens {
    access_token: String,
    refresh_token: String,
}

/// Okta settings, deserializable from the `[okta]` config table.
///
/// ```toml
/// [okta]
/// org = "https://example.okta.com"
/// client_id = "0oa..."                           # or:
/// client_id_command = ["pulumi", "env", "open", "org/env", "OKTA_CLIENT_ID", "--format", "string"]
/// keychain_service = "alfred-okta"
/// apps_ttl = 86400                                # seconds
/// ```
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Okta<K = SecurityKeychain> {
    /// Empty disables Okta items.
    pub org: String,
    #[serde(default)]
    pub client_id: Option<String>,
    /// Prints the client ID when `client_id` is unset; run with Alfred's tool PATH.
    #[serde(default)]
    pub client_id_command: Vec<String>,
    #[serde(default = "default_service")]
    pub keychain_service: String,
    #[serde(default = "default_ttl", deserialize_with = "seconds")]
    pub apps_ttl: Duration,
    #[serde(default = "default_title")]
    pub connect_title: String,
    #[serde(skip, default = "default_cache")]
    pub cache: PathBuf,
    #[serde(skip)]
    pub keychain: K,
}

fn default_service() -> String {
    "alfred-okta".into()
}

fn default_ttl() -> Duration {
    Duration::from_secs(24 * 60 * 60)
}

fn default_title() -> String {
    "Okta — connect to Okta and fetch applications list".into()
}

fn default_cache() -> PathBuf {
    cache_dir().join("alfred-okta-apps.json")
}

pub(crate) fn seconds<'de, D: Deserializer<'de>>(d: D) -> Result<Duration, D::Error> {
    u64::deserialize(d).map(Duration::from_secs)
}

impl Okta {
    pub fn new(org: impl Into<String>) -> Self {
        Self {
            org: org.into(),
            client_id: None,
            client_id_command: Vec::new(),
            keychain_service: default_service(),
            apps_ttl: default_ttl(),
            connect_title: default_title(),
            cache: default_cache(),
            keychain: SecurityKeychain,
        }
    }
}

impl<K: Keychain> Okta<K> {
    /// Swap the token store, e.g. for tests.
    pub fn with_keychain<T: Keychain>(self, keychain: T) -> Okta<T> {
        let Self {
            org,
            client_id,
            client_id_command,
            keychain_service,
            apps_ttl,
            connect_title,
            cache,
            keychain: _,
        } = self;
        Okta {
            org,
            client_id,
            client_id_command,
            keychain_service,
            apps_ttl,
            connect_title,
            cache,
            keychain,
        }
    }

    /// `client_id`, else the output of `client_id_command`.
    pub async fn client_id(&self) -> Option<String> {
        if let Some(id) = self.client_id.as_ref().filter(|id| !id.is_empty()) {
            return Some(id.clone());
        }
        let (program, args) = self.client_id_command.split_first()?;
        let id = output(tool(program).args(args), Duration::from_secs(25))
            .await
            .ok()?;
        Some(id.trim().to_owned()).filter(|id| !id.is_empty())
    }

    fn url(&self, path: &str) -> String {
        format!("{}{path}", self.org.trim_end_matches('/'))
    }

    fn client() -> Client {
        Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
            .expect("static client config is valid")
    }

    /// Device authorization grant: open Okta's approval page, keep the refresh token, then cache the apps.
    ///
    /// # Errors
    ///
    /// [`Error::OktaNotConfigured`] without an org and client ID, [`Error::Http`] or [`Error::OktaOAuth`] from Okta, [`Error::Open`] if the browser won't open, [`Error::Timeout`] when the code expires, and [`Error::Keychain`] if the token can't be saved.
    pub async fn login(&self) -> Result<()> {
        let client_id = self
            .client_id()
            .await
            .filter(|_| !self.org.is_empty())
            .ok_or(Error::OktaNotConfigured)?;
        let client = Self::client();
        let authorize = [("client_id", client_id.as_str()), ("scope", SCOPE)];
        let device: DeviceCode = json(
            client
                .post(self.url("/oauth2/v1/device/authorize"))
                .form(&authorize)
                .send()
                .await?,
        )
        .await?;
        if device.expires_in == 0 || device.interval == 0 {
            return Err(Error::OktaOAuth(
                "device code expires_in and interval must be positive".into(),
            ));
        }
        if !Command::new("open")
            .arg(&device.verification_uri_complete)
            .status()
            .await?
            .success()
        {
            return Err(Error::Open(device.verification_uri_complete));
        }
        let deadline = Instant::now() + Duration::from_secs(device.expires_in);
        let mut interval = Duration::from_secs(device.interval);
        loop {
            sleep(interval).await;
            if Instant::now() >= deadline {
                return Err(Error::Timeout("Okta device authorization".into()));
            }
            let form = [
                ("client_id", client_id.as_str()),
                ("grant_type", DEVICE_GRANT),
                ("device_code", &device.code),
            ];
            let response = client
                .post(self.url("/oauth2/v1/token"))
                .form(&form)
                .send()
                .await?;
            if response.status().is_success() {
                let tokens: Tokens = response.json().await?;
                self.keychain
                    .store(&self.keychain_service, &self.org, &tokens.refresh_token)
                    .await?;
                break;
            }
            let error = response.json::<OAuthError>().await?.error;
            interval = next_interval(&error, interval).ok_or(Error::OktaOAuth(error))?;
        }
        self.fetch_apps(&client_id).await?;
        Ok(())
    }

    /// Exchange the Keychain refresh token and cache the visible app tiles; `None` when not connected.
    ///
    /// # Errors
    ///
    /// [`Error::Http`] for transport failures and error statuses other than a rejected token, [`Error::Keychain`] if the rotated token can't be saved, and I/O errors writing the cache.
    pub async fn fetch_apps(&self, client_id: &str) -> Result<Option<OktaAppsCache>> {
        let Some(refresh_token) = self.keychain.find(&self.keychain_service, &self.org).await
        else {
            return Ok(None);
        };
        let client = Self::client();
        let form = [
            ("client_id", client_id),
            ("grant_type", "refresh_token"),
            ("refresh_token", &refresh_token),
            ("scope", SCOPE),
        ];
        let response = client
            .post(self.url("/oauth2/v1/token"))
            .form(&form)
            .send()
            .await?;
        if matches!(
            response.status(),
            StatusCode::BAD_REQUEST | StatusCode::UNAUTHORIZED
        ) {
            log::warn!("Okta refresh token rejected: {}", response.status());
            return Ok(None);
        }
        let tokens: Tokens = json(response).await?;
        // Refresh tokens may rotate, so the old one can stop working after the leeway.
        self.keychain
            .store(&self.keychain_service, &self.org, &tokens.refresh_token)
            .await?;
        let links: Vec<OktaAppLink> = json(
            client
                .get(self.url("/api/v1/users/me/appLinks"))
                .bearer_auth(&tokens.access_token)
                .send()
                .await?,
        )
        .await?;
        let apps = OktaAppsCache::new(links.into_iter().filter(|link| !link.hidden).collect());
        apps.save(&self.cache).await?;
        Ok(Some(apps))
    }

    /// App tiles from the cache, refetched once older than `apps_ttl`; a connect item until connected.
    ///
    /// An Okta outage keeps serving the stale tiles.
    ///
    /// # Errors
    ///
    /// Non-HTTP errors from [`Okta::fetch_apps`], such as a failed Keychain write.
    pub async fn items(&self) -> Result<Vec<ItemBuilder>> {
        if self.org.is_empty() {
            return Ok(Vec::new());
        }
        let mut apps = OktaAppsCache::load(&self.cache).await;
        if !apps.as_ref().is_some_and(|a| a.is_fresh(self.apps_ttl)) {
            let Some(client_id) = self.client_id().await else {
                return Ok(Vec::new());
            };
            match self.fetch_apps(&client_id).await {
                Ok(fetched) => apps = fetched,
                Err(e @ Error::Http(_)) => log::warn!("Okta app refresh failed: {e}"),
                Err(e) => return Err(e),
            }
        }
        let Some(apps) = apps else {
            let exe = std::env::current_exe()
                .map(|p| p.display().to_string())
                .unwrap_or_default();
            let connect = Item::exec(&self.connect_title, join([exe.as_str(), LOGIN_COMMAND]))
                .subtitle("Approve in the browser to list your Okta apps")
                .match_text("okta connect sign in login");
            return Ok(vec![connect]);
        };
        Ok(apps
            .links
            .into_iter()
            .map(|link| {
                let item = Item::url(&link.label, &link.link_url)
                    .subtitle("Okta")
                    .match_text(format!("okta {} {}", link.label, link.app_name));
                if link.logo_url.is_empty() {
                    item
                } else {
                    item.icon(IconSource::Url(link.logo_url))
                }
            })
            .collect())
    }
}

/// The poll interval after a pending device-flow response; `None` ends the flow.
fn next_interval(error: &str, interval: Duration) -> Option<Duration> {
    match error {
        "authorization_pending" => Some(interval),
        "slow_down" => Some(interval + SLOW_DOWN),
        _ => None,
    }
}

async fn json<T: DeserializeOwned>(response: Response) -> Result<T> {
    Ok(response.error_for_status()?.json().await?)
}

#[cfg(test)]
mod tests {
    use std::io::{BufRead, BufReader, Read, Write};
    use std::net::TcpListener;
    use std::sync::{Arc, Mutex};

    use super::*;

    const SENTRY: &str = r#"{"label": "Sentry", "linkUrl": "https://example.okta.com/home/sentry/1/2", "logoUrl": "", "appName": "sentry", "hidden": false}"#;
    const HIDDEN: &str = r#"{"label": "Hidden", "linkUrl": "https://example.okta.com/home/hidden/3/4", "logoUrl": "", "appName": "hidden", "hidden": true}"#;
    const CONNECT: &str = "Okta — connect to Okta and fetch applications list";
    const DAY: chrono::Duration = chrono::Duration::days(1);

    #[derive(Clone, Default)]
    struct FakeKeychain {
        token: Option<String>,
        writes: Arc<Mutex<Vec<String>>>,
        fail_writes: bool,
    }

    impl Keychain for FakeKeychain {
        fn find(&self, _: &str, _: &str) -> impl Future<Output = Option<String>> + Send {
            std::future::ready(self.token.clone())
        }

        fn store(&self, _: &str, _: &str, secret: &str) -> impl Future<Output = Result<()>> + Send {
            let stored = if self.fail_writes {
                Err(Error::Keychain)
            } else {
                self.writes.lock().unwrap().push(secret.to_owned());
                Ok(())
            };
            std::future::ready(stored)
        }
    }

    /// Okta stand-in: rotates `refresh-1`, rejects other refresh tokens, serves app links for `access`.
    fn okta_api() -> String {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        std::thread::spawn(move || {
            for stream in listener.incoming().flatten() {
                let mut reader = BufReader::new(stream);
                let mut head = String::new();
                while reader.read_line(&mut head).unwrap_or(0) > 2 {}
                let length = head
                    .lines()
                    .find_map(|l| {
                        l.to_lowercase()
                            .strip_prefix("content-length: ")
                            .map(|n| n.trim().parse().unwrap())
                    })
                    .unwrap_or(0);
                let mut body = vec![0; length];
                reader.read_exact(&mut body).unwrap();
                let body = String::from_utf8(body).unwrap();
                let (status, payload) = match head.split_whitespace().nth(1).unwrap_or_default() {
                    "/oauth2/v1/token" if body.contains("refresh_token=refresh-1") => (
                        200,
                        r#"{"access_token": "access", "refresh_token": "rotated"}"#.to_owned(),
                    ),
                    "/oauth2/v1/token" => (400, r#"{"error": "invalid_grant"}"#.to_owned()),
                    "/api/v1/users/me/appLinks"
                        if head.to_lowercase().contains("bearer access") =>
                    {
                        (200, format!("[{SENTRY}, {HIDDEN}]"))
                    }
                    _ => (500, String::new()),
                };
                let mut stream = reader.into_inner();
                let _ = write!(
                    stream,
                    "HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{payload}",
                    payload.len()
                );
            }
        });
        base
    }

    struct Fixture {
        _dir: tempfile::TempDir,
        okta: Okta<FakeKeychain>,
    }

    /// Okta at `org`, its app cache in a temp dir, optionally holding `cached` links fetched `age` ago.
    fn fixture(
        org: &str,
        keychain: FakeKeychain,
        cached: Option<(&str, chrono::Duration)>,
    ) -> Fixture {
        let dir = tempfile::tempdir().unwrap();
        let mut okta = Okta::new(org).with_keychain(keychain);
        okta.client_id = Some("client".into());
        okta.cache = dir.path().join("apps.json");
        if let Some((links, age)) = cached {
            let fetched_at = (Utc::now() - age).to_rfc3339();
            std::fs::write(
                &okta.cache,
                format!(r#"{{"v": 1, "fetched_at": "{fetched_at}", "links": [{links}]}}"#),
            )
            .unwrap();
        }
        Fixture { _dir: dir, okta }
    }

    fn stored(token: &str) -> FakeKeychain {
        FakeKeychain {
            token: Some(token.into()),
            ..FakeKeychain::default()
        }
    }

    async fn titles(okta: &Okta<FakeKeychain>) -> Vec<String> {
        okta.items()
            .await
            .unwrap()
            .into_iter()
            .map(|item| item.title)
            .collect()
    }

    #[tokio::test]
    async fn fresh_cache_serves_tiles_without_okta() {
        let f = fixture(
            "http://127.0.0.1:9",
            FakeKeychain::default(),
            Some((SENTRY, chrono::Duration::zero())),
        );
        assert_eq!(titles(&f.okta).await, ["Sentry"]);
    }

    #[tokio::test]
    async fn not_connected_shows_connect_item() {
        let f = fixture("http://127.0.0.1:9", FakeKeychain::default(), None);
        assert_eq!(titles(&f.okta).await, [CONNECT]);
    }

    #[tokio::test]
    async fn stale_cache_refetches_rotates_token_and_drops_hidden() {
        let keychain = stored("refresh-1");
        let f = fixture(&okta_api(), keychain.clone(), Some(("", DAY * 2)));
        assert_eq!(titles(&f.okta).await, ["Sentry"]);
        assert_eq!(*keychain.writes.lock().unwrap(), ["rotated"]);
        let cache = OktaAppsCache::load(&f.okta.cache).await.unwrap();
        assert_eq!(
            cache
                .links
                .iter()
                .map(|l| l.label.as_str())
                .collect::<Vec<_>>(),
            ["Sentry"]
        );
    }

    #[tokio::test]
    async fn rejected_refresh_token_shows_connect_item() {
        let f = fixture(&okta_api(), stored("revoked"), None);
        assert_eq!(titles(&f.okta).await, [CONNECT]);
    }

    #[tokio::test]
    async fn unconfigured_org_adds_nothing() {
        let f = fixture("", FakeKeychain::default(), None);
        assert_eq!(titles(&f.okta).await, Vec::<String>::new());
    }

    #[tokio::test]
    async fn okta_outage_keeps_stale_tiles() {
        // Nothing listens on the discard port, so the refresh fails to connect.
        let f = fixture(
            "http://127.0.0.1:9",
            stored("refresh-1"),
            Some((SENTRY, DAY * 2)),
        );
        assert_eq!(titles(&f.okta).await, ["Sentry"]);
    }

    #[tokio::test]
    async fn failed_keychain_write_is_reported() {
        let f = fixture(
            &okta_api(),
            FakeKeychain {
                fail_writes: true,
                ..stored("refresh-1")
            },
            None,
        );
        assert!(matches!(
            f.okta.fetch_apps("client").await,
            Err(Error::Keychain)
        ));
    }

    #[test]
    fn deserializes_from_toml_with_defaults() {
        let okta: Okta =
            toml::from_str("org = 'https://example.okta.com'\nclient_id_command = ['echo', 'x']")
                .unwrap();
        assert_eq!(
            (okta.keychain_service.as_str(), okta.apps_ttl),
            ("alfred-okta", default_ttl())
        );
        assert!(toml::from_str::<Okta>("org = 'x'\ntypo = 1").is_err());
    }

    #[tokio::test]
    async fn client_id_command_supplies_the_id() {
        let _serial = crate::serial().await;
        let okta: Okta =
            toml::from_str("org = 'x'\nclient_id_command = ['echo', '0oa123']").unwrap();
        assert_eq!(okta.client_id().await.as_deref(), Some("0oa123"));
    }

    #[test]
    fn app_links_and_cache_validate() {
        let link: OktaAppLink = serde_json::from_str(SENTRY).unwrap();
        assert_eq!(
            serde_json::from_str::<OktaAppLink>(&serde_json::to_string(&link).unwrap()).unwrap(),
            link
        );
        assert!(
            serde_json::from_str::<OktaAppsCache>(
                r#"{"v": 1, "fetched_at": "2026-01-01T00:00:00", "links": []}"#
            )
            .is_err()
        );
        assert!(
            serde_json::from_str::<OktaAppsCache>(
                r#"{"v": 1, "fetched_at": "2026-01-01T00:00:00+00:00", "links": []}"#
            )
            .is_ok()
        );
    }

    #[test]
    fn slow_down_backs_off_by_five_seconds() {
        let second = Duration::from_secs(1);
        assert_eq!(next_interval("authorization_pending", second), Some(second));
        assert_eq!(
            next_interval("slow_down", second),
            Some(Duration::from_secs(6))
        );
        assert_eq!(next_interval("access_denied", second), None);
    }

    #[test]
    fn keychain_secret_goes_through_stdin_line() {
        assert_eq!(
            add_password_line("alfred-okta", "https://example.okta.com", "rotated"),
            "add-generic-password -U -s alfred-okta -a https://example.okta.com -w rotated\n"
        );
    }
}
