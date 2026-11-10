//! Self-update from GitHub releases, with a live progress view.
//!
//! Alfred can't update workflows outside its Gallery, so this downloads the
//! release's `.alfredworkflow` asset and opens it; Alfred then offers its own
//! update dialog. [`crate::Workflow`] runs a throttled background check and
//! shows progress for the configured keyword.

use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use reqwest::Client;
use reqwest::header::{ACCEPT, AUTHORIZATION, HeaderMap, HeaderValue};
use serde::{Deserialize, Serialize};
use tokio::fs::{self, File};
use tokio::io::AsyncWriteExt;
use tokio::process::Command;

use crate::cache::{atomic_write, cache_dir, spawn_throttled};
use crate::okta::seconds;
use crate::shell::{output, tool};
use crate::{Error, Item, Menu, Result};

/// Runs a check, skipping a release that was already offered.
pub const CHECK_COMMAND: &str = "self-update";
/// Runs a check that re-offers the latest release.
pub const FORCE_COMMAND: &str = "self-update-now";
const STARTED_VARIABLE: &str = "we_love_update_started";
const SPINNER: [char; 10] = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

/// The `[update]` config table.
///
/// ```toml
/// [update]
/// repo = "owner/my-workflow"
/// asset = "MyWorkflow.alfredworkflow"
/// keyword = "update"              # query showing live progress
/// check_every = 86400             # seconds between background checks
/// token_env = "update_github_token"
/// ```
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Updater {
    pub repo: String,
    pub asset: String,
    #[serde(default = "default_keyword")]
    pub keyword: String,
    #[serde(default = "default_interval", deserialize_with = "seconds")]
    pub check_every: Duration,
    /// Environment variable holding a GitHub token; else `gh auth token`.
    /// Not `GITHUB_TOKEN`, which `gh` would also pick up for everything else.
    #[serde(default = "default_token_env")]
    pub token_env: String,
    #[serde(default = "default_api")]
    pub api_url: String,
}

fn default_keyword() -> String {
    "update".into()
}

fn default_interval() -> Duration {
    Duration::from_secs(24 * 60 * 60)
}

fn default_token_env() -> String {
    "update_github_token".into()
}

fn default_api() -> String {
    "https://api.github.com".into()
}

/// Progress shared between the updater process and the live view.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Status {
    pub running: bool,
    pub message: String,
}

#[derive(Debug, Deserialize)]
struct Release {
    tag_name: String,
    assets: Vec<Asset>,
}

#[derive(Debug, Deserialize)]
struct Asset {
    name: String,
    url: String,
}

impl Updater {
    pub fn new(repo: impl Into<String>, asset: impl Into<String>) -> Self {
        Self {
            repo: repo.into(),
            asset: asset.into(),
            keyword: default_keyword(),
            check_every: default_interval(),
            token_env: default_token_env(),
            api_url: default_api(),
        }
    }

    fn state_path(&self, extension: &str) -> PathBuf {
        cache_dir().join(format!(
            "{}-update.{extension}",
            self.repo.replace('/', "-")
        ))
    }

    async fn report(&self, running: bool, message: impl Into<String>) -> Result<()> {
        let status = Status {
            running,
            message: message.into(),
        };
        // Atomic: the live view reads it ten times a second.
        atomic_write(&self.state_path("status"), &serde_json::to_vec(&status)?).await
    }

    pub async fn status(&self) -> Option<Status> {
        serde_json::from_slice(&fs::read(self.state_path("status")).await.ok()?).ok()
    }

    /// Start a background check unless one started within `check_every`.
    pub async fn check_in_background(&self) -> bool {
        let exe = std::env::current_exe().unwrap_or_default();
        spawn_throttled(
            Command::new(exe).arg(CHECK_COMMAND),
            &self.state_path("pid"),
            self.check_every,
        )
        .await
    }

    /// The live view: starts a forced update once per Alfred session, then redraws its progress.
    pub async fn view(&self) -> Result<Menu> {
        self.view_with(std::env::var_os(STARTED_VARIABLE).is_some())
            .await
    }

    async fn view_with(&self, started: bool) -> Result<Menu> {
        if !started {
            self.report(true, "Starting").await?;
            let exe = std::env::current_exe()?;
            spawn_throttled(
                Command::new(exe).arg(FORCE_COMMAND),
                &self.state_path("view.pid"),
                Duration::ZERO,
            )
            .await;
        }
        let status = self.status().await.unwrap_or(Status {
            running: true,
            message: "Starting".into(),
        });
        let title = if status.running {
            let tick = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis()
                / 100;
            format!(
                "{}  {}",
                SPINNER[(tick % SPINNER.len() as u128) as usize],
                status.message
            )
        } else {
            status.message
        };
        Ok(Menu {
            rerun: status.running.then_some(0.1),
            variables: [(STARTED_VARIABLE.to_owned(), "1".to_owned())].into(),
            ..Menu::from_iter([Item::message(title, "Workflow update")])
        })
    }

    /// Check for a newer release than `$alfred_workflow_version`, download it and open it.
    pub async fn run(&self, force: bool) -> Result<()> {
        let current = std::env::var("alfred_workflow_version")
            .ok()
            .filter(|v| !v.is_empty());
        let result = self.run_with(current.as_deref(), force).await;
        if let Err(e) = &result {
            self.report(false, format!("Update failed: {e}")).await?;
        }
        result
    }

    async fn run_with(&self, current: Option<&str>, force: bool) -> Result<()> {
        let Some(current) = current else {
            return self.report(false, "Not running inside Alfred").await;
        };
        self.report(true, "Checking GitHub for a new release")
            .await?;
        let client = self.client().await?;
        let latest = client
            .get(format!(
                "{}/repos/{}/releases/latest",
                self.api_url, self.repo
            ))
            .send()
            .await?;
        if !latest.status().is_success() {
            return self
                .report(
                    false,
                    format!(
                        "Couldn't read GitHub releases: set ${} or sign in to gh",
                        self.token_env
                    ),
                )
                .await;
        }
        let release: Release = latest.json().await?;
        if version_key(&release.tag_name) <= version_key(current) {
            return self.report(false, format!("{current} is up to date")).await;
        }
        let offered = self.state_path("tag");
        if !force
            && fs::read_to_string(&offered)
                .await
                .is_ok_and(|tag| tag.trim() == release.tag_name)
        {
            return self
                .report(false, format!("{} was already offered", release.tag_name))
                .await;
        }
        let Some(asset) = release.assets.iter().find(|a| a.name == self.asset) else {
            return self
                .report(
                    false,
                    format!("{} has no {} asset", release.tag_name, self.asset),
                )
                .await;
        };
        let bundle = self.state_path("download").join(&self.asset);
        self.download(&client, &asset.url, &bundle, &release.tag_name)
            .await?;
        fs::write(&offered, &release.tag_name).await?;
        if !Command::new("open").arg(&bundle).status().await?.success() {
            return Err(Error::Open(bundle.display().to_string()));
        }
        self.report(
            false,
            format!(
                "Opened the {} installer: accept Alfred's update dialog",
                release.tag_name
            ),
        )
        .await
    }

    async fn download(&self, client: &Client, url: &str, path: &PathBuf, tag: &str) -> Result<()> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).await?;
        }
        let mut response = client
            .get(url)
            .header(ACCEPT, "application/octet-stream")
            .send()
            .await?
            .error_for_status()?;
        let total = response.content_length().unwrap_or(0);
        let mut out = File::create(path).await?;
        let mut done = 0u64;
        while let Some(chunk) = response.chunk().await? {
            out.write_all(&chunk).await?;
            done += chunk.len() as u64;
            let percent = (done * 100)
                .checked_div(total)
                .map(|p| format!(" {p}%"))
                .unwrap_or_default();
            self.report(
                true,
                format!("Downloading {tag}{percent} ({} MB)", done >> 20),
            )
            .await?;
        }
        out.flush().await?;
        Ok(())
    }

    /// Authorization is dropped on the cross-origin redirect to the asset's storage URL.
    async fn client(&self) -> Result<Client> {
        let mut headers = HeaderMap::from_iter([(
            ACCEPT,
            HeaderValue::from_static("application/vnd.github+json"),
        )]);
        if let Some(token) = self.token().await
            && let Ok(value) = HeaderValue::from_str(&format!("Bearer {token}"))
        {
            headers.insert(AUTHORIZATION, value);
        }
        Ok(Client::builder()
            .user_agent("we-love-alfred")
            .default_headers(headers)
            .timeout(Duration::from_secs(60))
            .build()?)
    }

    async fn token(&self) -> Option<String> {
        if let Some(token) = std::env::var(&self.token_env)
            .ok()
            .filter(|t| !t.is_empty())
        {
            return Some(token);
        }
        let token = output(tool("gh").args(["auth", "token"]), Duration::from_secs(10))
            .await
            .ok()?;
        Some(token.trim().to_owned()).filter(|t| !t.is_empty())
    }
}

/// `v1.10.2` → `[1, 10, 2]`; non-numeric parts count as 0.
fn version_key(version: &str) -> Vec<u64> {
    version
        .trim_start_matches('v')
        .split('.')
        .map(|part| part.parse().unwrap_or(0))
        .collect()
}

#[cfg(test)]
mod tests {
    use std::io::{BufRead, BufReader, Write};
    use std::net::TcpListener;

    use super::*;

    fn releases_api(body: &'static str) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        std::thread::spawn(move || {
            for stream in listener.incoming().flatten() {
                let mut reader = BufReader::new(stream);
                let mut line = String::new();
                while reader.read_line(&mut line).unwrap_or(0) > 2 {}
                let mut stream = reader.into_inner();
                let _ = write!(
                    stream,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                );
            }
        });
        base
    }

    fn updater(test: &str, api_url: String) -> Updater {
        let repo = format!("test-{test}/{}", std::process::id());
        Updater {
            api_url,
            token_env: "WE_LOVE_TEST_TOKEN".into(),
            ..Updater::new(repo, "Test.alfredworkflow")
        }
    }

    #[test]
    fn versions_compare_numerically() {
        assert!(version_key("v1.10.0") > version_key("1.9.9"));
        assert_eq!(version_key("v2.0"), [2, 0]);
    }

    #[tokio::test]
    async fn reports_up_to_date_and_missing_assets() {
        // Runs `gh auth token` when the token variable is unset.
        let _serial = crate::serial().await;
        let up_to_date = updater(
            "run",
            releases_api(r#"{"tag_name": "v1.2.0", "assets": []}"#),
        );
        up_to_date.run_with(Some("1.2.0"), false).await.unwrap();
        assert_eq!(
            up_to_date.status().await.unwrap(),
            Status {
                running: false,
                message: "1.2.0 is up to date".into()
            }
        );

        up_to_date.run_with(Some("1.1.0"), false).await.unwrap();
        assert_eq!(
            up_to_date.status().await.unwrap().message,
            "v1.2.0 has no Test.alfredworkflow asset"
        );

        up_to_date.run_with(None, false).await.unwrap();
        assert_eq!(
            up_to_date.status().await.unwrap().message,
            "Not running inside Alfred"
        );
        let _ = std::fs::remove_file(up_to_date.state_path("status"));
    }

    #[tokio::test]
    async fn view_redraws_while_running() {
        let updater = updater("view", String::new());
        updater.report(true, "Downloading").await.unwrap();
        let view = updater.view_with(true).await.unwrap();
        assert_eq!(view.rerun, Some(0.1));
        assert!(view.items[0].title.ends_with("Downloading"));
        updater.report(false, "Done").await.unwrap();
        let view = updater.view_with(true).await.unwrap();
        assert_eq!((view.rerun, view.items[0].title.as_str()), (None, "Done"));
        let _ = std::fs::remove_file(updater.state_path("status"));
    }
}
