//! Okta app tiles as Alfred items.
//!
//! Okta needs a public native OIDC app with the device authorization and
//! refresh token grants and the `okta.users.read.self` API scope granted.
//! Until the user connects, the menu shows one connect item running
//! [`Okta::login_command`]; the binary should call [`Okta::login`] for it and
//! rebuild the menu. The rotating refresh token lives in the macOS Keychain,
//! and the app list is cached for [`Okta::apps_ttl`].

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};
use std::{env, fs, thread};

use chrono::{DateTime, Utc};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use ureq::http::Response;
use ureq::{Agent, Body};

use crate::fast::{atomic_write, cache_path};
use crate::shell::join;
use crate::workflow::{IconSource, Item, Workflow};
use crate::{Error, Result};

const SCOPE: &str = "offline_access okta.users.read.self";
const DEVICE_GRANT: &str = "urn:ietf:params:oauth:grant-type:device_code";
/// RFC 8628 §3.5: `slow_down` adds five seconds to every later poll.
const SLOW_DOWN: Duration = Duration::from_secs(5);

/// Stores the Okta refresh token.
pub trait Keychain: Send + Sync {
    fn find(&self, service: &str, account: &str) -> Option<String>;
    fn store(&self, service: &str, account: &str, secret: &str) -> Result<()>;
}

/// The macOS login keychain via `/usr/bin/security`.
#[derive(Debug, Clone, Copy, Default)]
pub struct SecurityKeychain;

impl Keychain for SecurityKeychain {
    fn find(&self, service: &str, account: &str) -> Option<String> {
        let out = Command::new("/usr/bin/security")
            .args(["find-generic-password", "-s", service, "-a", account, "-w"])
            .stderr(Stdio::null())
            .output()
            .ok()?;
        out.status
            .success()
            .then(|| String::from_utf8_lossy(&out.stdout).trim().to_owned())
    }

    /// The secret goes through `security -i` on stdin, so it never reaches argv.
    fn store(&self, service: &str, account: &str, secret: &str) -> Result<()> {
        use std::io::Write;
        let mut child = Command::new("/usr/bin/security")
            .arg("-i")
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()?;
        let line = add_password_line(service, account, secret);
        child
            .stdin
            .take()
            .expect("piped stdin")
            .write_all(line.as_bytes())?;
        if child.wait()?.success() {
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
    pub fn new(links: Vec<OktaAppLink>) -> Self {
        Self {
            v: 1,
            fetched_at: Utc::now(),
            links,
        }
    }

    /// `None` for a missing, malformed, or other-version cache.
    pub fn load(path: &Path) -> Option<Self> {
        let cache: Self = serde_json::from_slice(&fs::read(path).ok()?).ok()?;
        (cache.v == 1).then_some(cache)
    }

    pub fn is_fresh(&self, ttl: Duration) -> bool {
        (Utc::now() - self.fetched_at)
            .to_std()
            .is_ok_and(|age| age < ttl)
    }

    pub fn save(&self, path: &Path) -> Result<()> {
        atomic_write(path, &serde_json::to_vec(self)?)
    }
}

#[derive(Deserialize)]
struct DeviceCode {
    device_code: String,
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

/// Okta settings and credentials for listing app tiles.
pub struct Okta {
    /// e.g. `https://example.okta.com`; empty disables Okta items.
    pub org: String,
    pub client_id: Option<String>,
    pub keychain_service: String,
    /// Where app tiles are cached; defaults to `alfred-okta-apps.json` in the [cache dir](cache_path).
    pub cache: PathBuf,
    pub apps_ttl: Duration,
    pub connect_title: String,
    /// What the connect item runs; it must end up calling [`Okta::login`].
    pub login_command: Vec<String>,
    pub keychain: Box<dyn Keychain>,
}

impl Okta {
    pub fn new(org: impl Into<String>, client_id: impl Into<String>) -> Self {
        let exe = env::current_exe()
            .map(|p| p.display().to_string())
            .unwrap_or_default();
        Self {
            org: org.into(),
            client_id: Some(client_id.into()).filter(|id: &String| !id.is_empty()),
            keychain_service: "alfred-okta".into(),
            cache: cache_path(Some("alfred-okta-apps")).expect("constant cache name is valid"),
            apps_ttl: Duration::from_secs(24 * 60 * 60),
            connect_title: "Okta — connect to Okta and fetch applications list".into(),
            login_command: vec![exe, "okta-login".into()],
            keychain: Box::new(SecurityKeychain),
        }
    }

    fn url(&self, path: &str) -> String {
        format!("{}{path}", self.org.trim_end_matches('/'))
    }

    fn agent() -> Agent {
        Agent::config_builder()
            .http_status_as_error(false)
            .timeout_global(Some(Duration::from_secs(5)))
            .build()
            .into()
    }

    /// Device authorization grant: open Okta's approval page, keep the refresh token, then cache the apps.
    pub fn login(&self) -> Result<()> {
        let client_id = self
            .client_id
            .as_deref()
            .filter(|_| !self.org.is_empty())
            .ok_or(Error::OktaNotConfigured)?;
        let agent = Self::agent();
        let device: DeviceCode = json(
            agent
                .post(self.url("/oauth2/v1/device/authorize"))
                .send_form([("client_id", client_id), ("scope", SCOPE)])?,
        )?;
        if device.expires_in == 0 || device.interval == 0 {
            return Err(Error::OktaOAuth(
                "device code expires_in and interval must be positive".into(),
            ));
        }
        if !Command::new("open")
            .arg(&device.verification_uri_complete)
            .status()?
            .success()
        {
            return Err(Error::Browser);
        }
        let deadline = Instant::now() + Duration::from_secs(device.expires_in);
        let mut interval = Duration::from_secs(device.interval);
        loop {
            thread::sleep(interval);
            if Instant::now() >= deadline {
                return Err(Error::Timeout("Okta device authorization".into()));
            }
            let form = [
                ("client_id", client_id),
                ("grant_type", DEVICE_GRANT),
                ("device_code", &device.device_code),
            ];
            let mut response = agent.post(self.url("/oauth2/v1/token")).send_form(form)?;
            if response.status().is_success() {
                let tokens: Tokens = response.body_mut().read_json()?;
                self.keychain
                    .store(&self.keychain_service, &self.org, &tokens.refresh_token)?;
                break;
            }
            let error = response.body_mut().read_json::<OAuthError>()?.error;
            interval = next_interval(&error, interval).ok_or(Error::OktaOAuth(error))?;
        }
        self.fetch_apps(client_id)?;
        Ok(())
    }

    /// Exchange the Keychain refresh token and cache the visible app tiles; `None` when not connected.
    pub fn fetch_apps(&self, client_id: &str) -> Result<Option<OktaAppsCache>> {
        let Some(refresh_token) = self.keychain.find(&self.keychain_service, &self.org) else {
            return Ok(None);
        };
        let agent = Self::agent();
        let form = [
            ("client_id", client_id),
            ("grant_type", "refresh_token"),
            ("refresh_token", &refresh_token),
            ("scope", SCOPE),
        ];
        let response = agent.post(self.url("/oauth2/v1/token")).send_form(form)?;
        if matches!(response.status().as_u16(), 400 | 401) {
            log::warn!("Okta refresh token rejected: {}", response.status());
            return Ok(None);
        }
        let tokens: Tokens = json(response)?;
        // Refresh tokens may rotate, so the old one can stop working after the leeway.
        self.keychain
            .store(&self.keychain_service, &self.org, &tokens.refresh_token)?;
        let links: Vec<OktaAppLink> = json(
            agent
                .get(self.url("/api/v1/users/me/appLinks"))
                .header("Authorization", format!("Bearer {}", tokens.access_token))
                .call()?,
        )?;
        let apps = OktaAppsCache::new(links.into_iter().filter(|link| !link.hidden).collect());
        apps.save(&self.cache)?;
        Ok(Some(apps))
    }

    /// App tiles from the cache, refetched once older than `apps_ttl`; a connect item until connected.
    ///
    /// An Okta outage keeps serving the stale tiles.
    pub fn add_items(&self, workflow: &mut Workflow) -> Result<()> {
        if self.org.is_empty() {
            return Ok(());
        }
        let mut apps = OktaAppsCache::load(&self.cache);
        if !apps.as_ref().is_some_and(|a| a.is_fresh(self.apps_ttl)) {
            let Some(client_id) = &self.client_id else {
                return Ok(());
            };
            match self.fetch_apps(client_id) {
                Ok(fetched) => apps = fetched,
                Err(e @ (Error::Http(_) | Error::HttpStatus(_))) => {
                    log::warn!("Okta app refresh failed: {e}")
                }
                Err(e) => return Err(e),
            }
        }
        let Some(apps) = apps else {
            workflow.add(
                Item::exec(&self.connect_title, join(&self.login_command))
                    .subtitle("Approve in the browser to list your Okta apps")
                    .match_text("okta connect sign in login"),
            );
            return Ok(());
        };
        for link in apps.links {
            let mut item = Item::url(&link.label, &link.link_url)
                .subtitle("Okta")
                .match_text(format!("okta {} {}", link.label, link.app_name));
            if !link.logo_url.is_empty() {
                item = item.icon(IconSource::Url(link.logo_url));
            }
            workflow.add(item);
        }
        Ok(())
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

fn json<T: DeserializeOwned>(mut response: Response<Body>) -> Result<T> {
    let status = response.status();
    if !status.is_success() {
        return Err(Error::HttpStatus(status.as_u16()));
    }
    Ok(response.body_mut().read_json()?)
}

#[cfg(test)]
mod tests {
    use std::io::{BufRead, BufReader, Read, Write};
    use std::net::TcpListener;
    use std::sync::Mutex;

    use super::*;

    const SENTRY: &str = r#"{"label": "Sentry", "linkUrl": "https://example.okta.com/home/sentry/1/2", "logoUrl": "", "appName": "sentry", "hidden": false}"#;
    const HIDDEN: &str = r#"{"label": "Hidden", "linkUrl": "https://example.okta.com/home/hidden/3/4", "logoUrl": "", "appName": "hidden", "hidden": true}"#;
    const CONNECT: &str = "Okta — connect to Okta and fetch applications list";

    #[derive(Default)]
    struct FakeKeychain {
        token: Option<String>,
        writes: Mutex<Vec<String>>,
        fail_writes: bool,
    }

    impl Keychain for std::sync::Arc<FakeKeychain> {
        fn find(&self, _: &str, _: &str) -> Option<String> {
            self.token.clone()
        }

        fn store(&self, _: &str, _: &str, secret: &str) -> Result<()> {
            if self.fail_writes {
                return Err(Error::Keychain);
            }
            self.writes.lock().unwrap().push(secret.to_owned());
            Ok(())
        }
    }

    /// Okta stand-in: rotates `refresh-1`, rejects other refresh tokens, serves app links for `access`.
    fn okta_api() -> String {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        thread::spawn(move || {
            for stream in listener.incoming().flatten() {
                let mut reader = BufReader::new(stream);
                let mut head = String::new();
                while reader.read_line(&mut head).unwrap_or(0) > 2 && !head.ends_with("\r\n\r\n") {}
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
                let path = head.split_whitespace().nth(1).unwrap_or_default();
                let (status, payload) = match path {
                    "/oauth2/v1/token" if body.contains("refresh_token=refresh-1") => (
                        200,
                        r#"{"access_token": "access", "refresh_token": "rotated"}"#.to_owned(),
                    ),
                    "/oauth2/v1/token" => (400, r#"{"error": "invalid_grant"}"#.to_owned()),
                    "/api/v1/users/me/appLinks" if head.contains("Bearer access") => {
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
        okta: Okta,
        keychain: std::sync::Arc<FakeKeychain>,
    }

    /// Okta at `org`, its app cache in a temp dir, optionally holding `cached` links fetched `age` ago.
    fn fixture(
        org: &str,
        stored: Option<&str>,
        cached: Option<(&str, chrono::Duration)>,
    ) -> Fixture {
        let dir = tempfile::tempdir().unwrap();
        let keychain = std::sync::Arc::new(FakeKeychain {
            token: stored.map(str::to_owned),
            ..FakeKeychain::default()
        });
        let mut okta = Okta::new(org, "client");
        okta.keychain = Box::new(keychain.clone());
        okta.cache = dir.path().join("apps.json");
        if let Some((links, age)) = cached {
            let fetched_at = (Utc::now() - age).to_rfc3339();
            let raw = format!(r#"{{"v": 1, "fetched_at": "{fetched_at}", "links": [{links}]}}"#);
            fs::write(&okta.cache, raw).unwrap();
        }
        Fixture {
            _dir: dir,
            okta,
            keychain,
        }
    }

    /// Titles of the queued items; resolving them would fetch favicons.
    fn titles(okta: &Okta) -> Vec<String> {
        let mut workflow = Workflow::new();
        okta.add_items(&mut workflow).unwrap();
        workflow
            .pending
            .iter()
            .map(|item| item.title.clone())
            .collect()
    }

    const DAY: chrono::Duration = chrono::Duration::days(1);

    #[test]
    fn fresh_cache_serves_tiles_without_okta() {
        let f = fixture(
            "http://127.0.0.1:9",
            None,
            Some((SENTRY, chrono::Duration::zero())),
        );
        assert_eq!(titles(&f.okta), ["Sentry"]);
    }

    #[test]
    fn not_connected_shows_connect_item() {
        let f = fixture("http://127.0.0.1:9", None, None);
        assert_eq!(titles(&f.okta), [CONNECT]);
    }

    #[test]
    fn stale_cache_refetches_rotates_token_and_drops_hidden() {
        let f = fixture(&okta_api(), Some("refresh-1"), Some(("", DAY * 2)));
        assert_eq!(titles(&f.okta), ["Sentry"]);
        assert_eq!(*f.keychain.writes.lock().unwrap(), ["rotated"]);
        let cache = OktaAppsCache::load(&f.okta.cache).unwrap();
        assert_eq!(
            cache
                .links
                .iter()
                .map(|l| l.label.as_str())
                .collect::<Vec<_>>(),
            ["Sentry"]
        );
    }

    #[test]
    fn rejected_refresh_token_shows_connect_item() {
        let f = fixture(&okta_api(), Some("revoked"), None);
        assert_eq!(titles(&f.okta), [CONNECT]);
    }

    #[test]
    fn unconfigured_org_adds_nothing() {
        let mut f = fixture("", None, None);
        f.okta.org.clear();
        assert!(titles(&f.okta).is_empty());
    }

    #[test]
    fn okta_outage_keeps_stale_tiles() {
        // Nothing listens on the discard port, so the refresh fails to connect.
        let f = fixture(
            "http://127.0.0.1:9",
            Some("refresh-1"),
            Some((SENTRY, DAY * 2)),
        );
        assert_eq!(titles(&f.okta), ["Sentry"]);
    }

    #[test]
    fn failed_keychain_write_is_reported() {
        let mut f = fixture(&okta_api(), Some("refresh-1"), None);
        f.okta.keychain = Box::new(std::sync::Arc::new(FakeKeychain {
            token: Some("refresh-1".into()),
            fail_writes: true,
            ..FakeKeychain::default()
        }));
        assert!(matches!(f.okta.fetch_apps("client"), Err(Error::Keychain)));
    }

    #[test]
    fn app_link_round_trips_by_alias() {
        let link: OktaAppLink = serde_json::from_str(SENTRY).unwrap();
        assert_eq!(
            serde_json::from_str::<OktaAppLink>(&serde_json::to_string(&link).unwrap()).unwrap(),
            link
        );
    }

    #[test]
    fn naive_cache_time_is_rejected() {
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
    fn concurrent_cache_writes_are_atomic() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cache.json");
        let first = OktaAppsCache::new(vec![]);
        let second = OktaAppsCache::new(vec![serde_json::from_str(SENTRY).unwrap()]);
        thread::scope(|s| {
            s.spawn(|| first.save(&path).unwrap());
            s.spawn(|| second.save(&path).unwrap());
        });
        let loaded = OktaAppsCache::load(&path).unwrap();
        assert!(loaded == first || loaded == second);
        assert_eq!(
            fs::read_dir(dir.path()).unwrap().count(),
            1,
            "temporary files left behind"
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
