//! Open GitHub PRs as Alfred items: `prs [@author] [terms]` and `#<number|text>`.
//!
//! `gh pr list` output is cached for `ttl` and refreshed by a detached copy of
//! the current binary once stale, so only the very first lookup waits on `gh`.
//! [`Github`] is the `[github]` config and the [`Feature`] that answers and refreshes.

use std::collections::BTreeSet;
use std::ffi::OsString;
use std::path::PathBuf;
use std::sync::LazyLock;
use std::time::{Duration, SystemTime};

use chrono::{DateTime, FixedOffset};
use futures_util::future::{BoxFuture, FutureExt};
use regex::Regex;
use serde::Deserialize;
use tokio::fs;
use tokio::process::Command;

use crate::cache::{atomic_write, cache_dir, spawn_self, with_suffix};
use crate::feature::{After, Context, Feature, split_word};
use crate::menu::is_subsequence;
use crate::shell::{output, tool};
use crate::{Error, Item, Menu, Result, Text};

/// First argument of the detached refresh command.
pub const REFRESH_COMMAND: &str = "github-refresh";
const USAGE: &str = "github-refresh <owner/repo> <cache.json> [--limit N]";
const GH_TIMEOUT: Duration = Duration::from_secs(25);
/// A bare PR number, optionally after `pr`.
static PR_NUMBER: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)^(?:pr\s*)?(\d{1,6})$").expect("valid regex"));

/// Every term's characters appear in order in `text`, case-insensitively.
pub fn fuzzy_match<S: AsRef<str>>(terms: &[S], text: &str) -> bool {
    let text = text.to_lowercase();
    terms
        .iter()
        .all(|term| is_subsequence(&term.as_ref().to_lowercase(), &text))
}

/// One row of `gh pr list --json number,title,author,isDraft,updatedAt,url`.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(try_from = "Row")]
pub struct PullRequest {
    pub number: u64,
    pub title: String,
    pub author: String,
    pub is_draft: bool,
    pub updated_at: DateTime<FixedOffset>,
    pub url: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Row {
    number: u64,
    title: String,
    author: Author,
    is_draft: bool,
    updated_at: String,
    url: String,
}

#[derive(Deserialize)]
struct Author {
    login: String,
}

impl TryFrom<Row> for PullRequest {
    type Error = String;

    fn try_from(row: Row) -> Result<Self, String> {
        let updated_at = DateTime::parse_from_rfc3339(&row.updated_at)
            .map_err(|e| format!("PR updatedAt must be RFC 3339 with a timezone: {e}"))?;
        Ok(Self {
            number: row.number,
            title: row.title,
            author: row.author.login,
            is_draft: row.is_draft,
            updated_at,
            url: row.url,
        })
    }
}

impl PullRequest {
    /// All rows, most recently updated first.
    ///
    /// # Errors
    ///
    /// [`Error::Json`] when `data` isn't a list of `gh pr list` rows with timezone-aware `updatedAt`.
    pub fn list_from_json(data: &str) -> Result<Vec<Self>> {
        let mut prs: Vec<Self> = serde_json::from_str(data)?;
        prs.sort_by_key(|pr| std::cmp::Reverse(pr.updated_at));
        Ok(prs)
    }

    pub fn matches<S: AsRef<str>>(&self, terms: &[S]) -> bool {
        fuzzy_match(terms, &format!("{} {}", self.number, self.title))
    }

    #[must_use]
    pub fn item(&self) -> Item {
        let draft = if self.is_draft { " · draft" } else { "" };
        Item {
            title: format!("#{} {}", self.number, self.title),
            subtitle: format!(
                "@{}{draft} · updated {}",
                self.author,
                self.updated_at.format("%Y-%m-%d")
            ),
            arg: format!("open {}", self.url),
            autocomplete: format!("#{}", self.number),
            valid: Some(true),
            text: Some(Text {
                copy: self.url.clone(),
                largetype: self.title.clone(),
            }),
            ..Item::default()
        }
    }
}

/// Open PRs for `repo`, cached at `path` and refreshed in the background once older than `ttl`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PullRequestCache {
    pub repo: String,
    pub path: PathBuf,
    pub ttl: Duration,
    /// Minimum gap between background refresh attempts, including failed ones.
    pub retry_every: Duration,
    pub limit: u32,
}

impl PullRequestCache {
    pub fn new(repo: impl Into<String>, path: impl Into<PathBuf>) -> Self {
        Self {
            repo: repo.into(),
            path: path.into(),
            ttl: Duration::from_secs(3600),
            retry_every: Duration::from_secs(60),
            limit: 1000,
        }
    }

    /// Left in place after a refresh, so a failing `gh` is retried at most once per `retry_every`.
    #[must_use]
    pub fn warming_path(&self) -> PathBuf {
        with_suffix(&self.path, ".warming")
    }

    /// Run `gh` now and atomically replace the cache; a payload that won't parse is never written.
    ///
    /// # Errors
    ///
    /// [`Error::Command`] or [`Error::Timeout`] from `gh`, [`Error::Json`] for an unparseable payload, and I/O errors writing the cache.
    pub async fn fetch(&self) -> Result<()> {
        self.fetch_with(tool("gh")).await
    }

    async fn fetch_with(&self, mut gh: Command) -> Result<()> {
        let limit = self.limit.to_string();
        gh.args([
            "pr", "list", "-R", &self.repo, "--state", "open", "--limit", &limit,
        ]);
        gh.args(["--json", "number,title,author,isDraft,updatedAt,url"]);
        let stdout = output(&mut gh, GH_TIMEOUT).await?;
        PullRequest::list_from_json(&stdout)?;
        atomic_write(&self.path, stdout.as_bytes()).await
    }

    pub async fn is_fresh(&self) -> bool {
        let modified = fs::metadata(&self.path).await.and_then(|m| m.modified());
        modified.is_ok_and(|m| SystemTime::now().duration_since(m).unwrap_or_default() < self.ttl)
    }

    /// Start a detached refresh if the cache is stale; returns whether one started.
    pub async fn warm(&self) -> bool {
        !self.is_fresh().await && self.schedule_refresh().await
    }

    async fn schedule_refresh(&self) -> bool {
        spawn_self(self.refresh_args(), &self.warming_path(), self.retry_every).await
    }

    /// The detached refresh's arguments, handled by [`Github`]'s command.
    fn refresh_args(&self) -> Vec<OsString> {
        let limit = self.limit.to_string();
        [REFRESH_COMMAND, &self.repo]
            .map(OsString::from)
            .into_iter()
            .chain([self.path.clone().into_os_string()])
            .chain(["--limit", &limit].map(OsString::from))
            .collect()
    }

    /// Cached PRs, even stale ones; a miss or malformed cache yields none. Never waits on `gh`.
    pub async fn load(&self) -> Vec<PullRequest> {
        let cached = fs::read_to_string(&self.path)
            .await
            .map_err(Error::from)
            .and_then(|d| PullRequest::list_from_json(&d));
        if let Ok(prs) = cached {
            self.warm().await;
            prs
        } else {
            self.schedule_refresh().await;
            Vec::new()
        }
    }

    /// `[@author] [terms]`; an `@author` matching no login lists authors to autocomplete instead.
    pub async fn search_items(&self, args: &str, keyword: &str) -> Vec<Item> {
        let prs = self.load().await;
        let (authors, terms): (Vec<&str>, Vec<&str>) =
            args.split_whitespace().partition(|w| w.starts_with('@'));
        let authors: Vec<String> = authors.iter().map(|a| a[1..].to_lowercase()).collect();
        let mut logins: Vec<&str> = prs
            .iter()
            .map(|pr| pr.author.as_str())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        logins.sort_by_key(|login| login.to_lowercase());

        if let Some(pending) = authors
            .iter()
            .rfind(|a| !logins.iter().any(|l| l.to_lowercase() == **a))
        {
            return logins
                .iter()
                .filter(|login| fuzzy_match(&[pending], login))
                .map(|login| Item {
                    autocomplete: format!("{keyword} @{login} "),
                    ..Item::message(
                        format!("@{login}"),
                        format!(
                            "{} open PRs",
                            prs.iter().filter(|pr| pr.author == *login).count()
                        ),
                    )
                })
                .collect();
        }

        prs.iter()
            .filter(|pr| authors.is_empty() || authors.contains(&pr.author.to_lowercase()))
            .filter(|pr| pr.matches(&terms))
            .map(PullRequest::item)
            .collect()
    }

    /// Text after `#`: digits narrow by number prefix, anything else by title.
    pub async fn number_items(&self, needle: &str) -> Vec<Item> {
        let needle = needle.trim();
        let number = needle
            .bytes()
            .all(|b| b.is_ascii_digit())
            .then(|| needle.parse::<u64>().ok())
            .flatten();
        let terms: Vec<&str> = needle.split_whitespace().collect();
        let mut items: Vec<Item> = self
            .load()
            .await
            .iter()
            .filter(|pr| match number {
                Some(_) => pr.number.to_string().starts_with(needle),
                None => pr.matches(&terms),
            })
            .map(PullRequest::item)
            .collect();
        if let Some(number) = number
            && !items
                .iter()
                .any(|item| item.autocomplete == format!("#{needle}"))
        {
            // Closed and merged PRs are not cached; still offer the direct link, after any open matches.
            items.push(self.link_item(number));
        }
        items
    }

    #[must_use]
    pub fn link_item(&self, number: u64) -> Item {
        let url = format!("https://github.com/{}/pull/{number}", self.repo);
        Item {
            title: format!("Open PR #{number}"),
            arg: format!("open {url}"),
            subtitle: url,
            valid: Some(true),
            ..Item::default()
        }
    }
}

/// The cache a detached refresh's arguments (after [`REFRESH_COMMAND`]) describe.
fn refresh_target(rest: &[String]) -> Result<PullRequestCache> {
    match rest {
        [repo, path] => Ok(PullRequestCache::new(repo.as_str(), path)),
        [repo, path, flag, limit] if flag == "--limit" => {
            let limit = limit.parse().map_err(|_| Error::Usage(USAGE))?;
            Ok(PullRequestCache {
                limit,
                ..PullRequestCache::new(repo.as_str(), path)
            })
        }
        _ => Err(Error::Usage(USAGE)),
    }
}

/// `[github]`: open PRs via `gh`, searched with `<keyword> [@author] [terms]`, `#<number|text>` or a bare number.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Github {
    pub repo: String,
    #[serde(default = "default_keyword")]
    pub keyword: String,
    #[serde(default = "default_limit")]
    pub limit: u32,
}

fn default_keyword() -> String {
    "prs".into()
}

fn default_limit() -> u32 {
    1000
}

impl Github {
    #[must_use]
    pub fn cache(&self) -> PullRequestCache {
        let path = cache_dir().join(format!("{}-prs.json", self.repo.replace('/', "-")));
        PullRequestCache {
            limit: self.limit,
            ..PullRequestCache::new(&self.repo, path)
        }
    }
}

impl Feature for Github {
    fn command<'a>(
        &'a self,
        _ctx: &'a Context,
        args: &'a [String],
    ) -> Option<BoxFuture<'a, Result<After>>> {
        let (command, rest) = args.split_first()?;
        (command == REFRESH_COMMAND).then(|| {
            async move {
                refresh_target(rest)?.fetch().await?;
                Ok(After::Exit)
            }
            .boxed()
        })
    }

    fn answer<'a>(
        &'a self,
        _ctx: &'a Context,
        query: &'a str,
    ) -> Option<BoxFuture<'a, Result<Menu>>> {
        let (word, rest) = split_word(query);
        let prs = self.cache();
        let empty = if prs.path.exists() {
            "No matching open PRs"
        } else {
            "Loading open PRs…"
        };
        if word.eq_ignore_ascii_case(&self.keyword) {
            return Some(
                async move {
                    Ok(Menu::from_iter(prs.search_items(rest, &self.keyword).await)
                        .or_message(empty))
                }
                .boxed(),
            );
        }
        if let Some(needle) = query.strip_prefix('#') {
            return Some(async move { Ok(Menu::from_iter(prs.number_items(needle).await).or_message(empty)) }.boxed());
        }
        let number = PR_NUMBER.captures(query).and_then(|c| c[1].parse().ok())?;
        Some(async move { Ok(Menu::from_iter([prs.link_item(number)])) }.boxed())
    }

    fn background<'a>(&'a self, _ctx: &'a Context) -> BoxFuture<'a, ()> {
        async move {
            self.cache().warm().await;
        }
        .boxed()
    }
}

#[cfg(test)]
mod tests {
    use std::os::unix::fs::PermissionsExt;
    use std::path::Path;

    use chrono::{TimeZone, Utc};
    use serde_json::{Value, json};

    use super::*;

    fn row(number: u64, title: &str, author: &str, updated: &str, draft: bool) -> Value {
        json!({
            "number": number, "title": title, "author": {"login": author, "is_bot": false},
            "isDraft": draft, "updatedAt": updated, "url": format!("https://github.com/acme/app/pull/{number}"),
        })
    }

    fn rows() -> Value {
        json!([
            row(
                4468,
                "feat(fhir): ServiceRequest",
                "NorthIsUp",
                "2026-10-29T12:00:00Z",
                false
            ),
            row(
                4496,
                "refactor(notifications): channel updates",
                "NorthIsUp",
                "2026-10-30T12:00:00Z",
                true
            ),
            row(
                4401,
                "fix(labs): sandbox cap",
                "sarahrhodes-clara",
                "2026-10-01T12:00:00Z",
                false
            ),
        ])
    }

    /// A cache holding `rows()` aged `age`.
    fn cache(dir: &Path, age: Duration) -> PullRequestCache {
        let path = dir.join("prs.json");
        std::fs::write(&path, rows().to_string()).unwrap();
        std::fs::File::options()
            .write(true)
            .open(&path)
            .unwrap()
            .set_modified(SystemTime::now() - age)
            .unwrap();
        PullRequestCache::new("acme/app", path)
    }

    fn script(dir: &Path, name: &str, body: &str) -> PathBuf {
        let path = dir.join(name);
        std::fs::write(&path, format!("#!/bin/sh\n{body}\n")).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755)).unwrap();
        path
    }

    fn prefixes(items: &[Item]) -> Vec<&str> {
        items.iter().map(|i| &i.title[..5]).collect()
    }

    #[test]
    fn fuzzy_match_requires_every_term_in_order() {
        assert!(fuzzy_match(
            &["ntf", "chan"],
            "Notifications: channel updates"
        ));
        assert!(!fuzzy_match(&["tfn"], "fit"));
    }

    #[test]
    fn parses_and_rejects_rows() {
        let pr: PullRequest = serde_json::from_value(rows()[1].clone()).unwrap();
        assert_eq!(
            pr.updated_at,
            Utc.with_ymd_and_hms(2026, 10, 30, 12, 0, 0).unwrap()
        );
        assert_eq!(
            (pr.number, pr.is_draft, pr.author.as_str()),
            (4496, true, "NorthIsUp")
        );
        assert!(serde_json::from_value::<PullRequest>(json!({"number": "4468"})).is_err());
        assert!(
            serde_json::from_value::<PullRequest>(row(1, "t", "a", "2026-10-30T12:00:00", false))
                .is_err()
        );
        assert!(serde_json::from_value::<PullRequest>(json!({"number": true})).is_err());
        let numbers: Vec<_> = PullRequest::list_from_json(&rows().to_string())
            .unwrap()
            .iter()
            .map(|p| p.number)
            .collect();
        assert_eq!(numbers, [4496, 4468, 4401]);
    }

    #[test]
    fn item_links_and_autocompletes() {
        let item = serde_json::from_value::<PullRequest>(rows()[1].clone())
            .unwrap()
            .item();
        assert_eq!(item.title, "#4496 refactor(notifications): channel updates");
        assert_eq!(item.subtitle, "@NorthIsUp · draft · updated 2026-10-30");
        assert_eq!(item.arg, "open https://github.com/acme/app/pull/4496");
        assert_eq!(item.autocomplete, "#4496");
    }

    #[tokio::test]
    async fn search_and_number_items() {
        let dir = tempfile::tempdir().unwrap();
        let cache = cache(dir.path(), Duration::ZERO);
        assert_eq!(
            prefixes(&cache.search_items("", "prs").await),
            ["#4496", "#4468", "#4401"]
        );
        assert_eq!(
            prefixes(&cache.search_items("@northisup fhir", "prs").await),
            ["#4468"]
        );
        let authors = cache.search_items("@sar", "prs").await;
        assert_eq!(authors.len(), 1);
        assert_eq!(
            (authors[0].title.as_str(), authors[0].autocomplete.as_str()),
            ("@sarahrhodes-clara", "prs @sarahrhodes-clara ")
        );
        assert_eq!(prefixes(&cache.number_items("4468").await), ["#4468"]);
        assert_eq!(
            prefixes(&cache.number_items("44").await),
            ["#4496", "#4468", "#4401", "Open "]
        );
        assert_eq!(cache.number_items("12").await, [cache.link_item(12)]);
        assert_eq!(prefixes(&cache.number_items("labs").await), ["#4401"]);
    }

    #[tokio::test]
    async fn warm_spawns_once_per_retry_window_and_skips_fresh() {
        let _serial = crate::serial().await;
        let dir = tempfile::tempdir().unwrap();
        assert!(!cache(dir.path(), Duration::ZERO).warm().await);
        let stale = PullRequestCache {
            limit: 25,
            ..cache(dir.path(), Duration::from_secs(7200))
        };
        assert!(stale.warm().await);
        assert!(!stale.warm().await);
        let expected = [
            "github-refresh",
            "acme/app",
            &stale.path.display().to_string(),
            "--limit",
            "25",
        ];
        assert_eq!(stale.refresh_args(), expected.map(OsString::from));
    }

    #[tokio::test]
    async fn broken_or_missing_cache_serves_nothing_and_refreshes_once() {
        let _serial = crate::serial().await;
        let dir = tempfile::tempdir().unwrap();
        let cache = cache(dir.path(), Duration::ZERO);
        std::fs::write(&cache.path, "broken").unwrap();
        assert_eq!(cache.load().await, Vec::<PullRequest>::new());
        assert_eq!(cache.load().await, Vec::<PullRequest>::new());
        assert!(
            !cache.schedule_refresh().await,
            "second load should have hit the throttle"
        );
        let missing = PullRequestCache {
            path: dir.path().join("missing.json"),
            ..cache.clone()
        };
        assert_eq!(missing.load().await, Vec::<PullRequest>::new());
    }

    #[tokio::test]
    async fn fetch_replaces_only_with_valid_payload() {
        let _serial = crate::serial().await;
        let dir = tempfile::tempdir().unwrap();
        let cache = cache(dir.path(), Duration::ZERO);
        let previous = std::fs::read_to_string(&cache.path).unwrap();
        let bad = Command::new(script(dir.path(), "gh-bad", "echo 'not JSON'"));
        assert!(matches!(cache.fetch_with(bad).await, Err(Error::Json(_))));
        assert_eq!(std::fs::read_to_string(&cache.path).unwrap(), previous);
        let good = Command::new(script(
            dir.path(),
            "gh-good",
            &format!("echo '{}'", json!([rows()[2]])),
        ));
        cache.fetch_with(good).await.unwrap();
        assert_eq!(cache.load().await.len(), 1);
    }

    #[tokio::test]
    async fn github_handles_only_its_refresh_command() {
        let github = Github {
            repo: "acme/app".into(),
            keyword: "prs".into(),
            limit: 10,
        };
        let ctx = Context {
            icons: crate::Icons::new("/nonexistent"),
            populators: std::collections::BTreeMap::new(),
        };
        assert!(github.command(&ctx, &["nope".to_owned()]).is_none());
        let usage = github
            .command(&ctx, &[REFRESH_COMMAND.to_owned()])
            .unwrap()
            .await;
        assert!(matches!(usage, Err(Error::Usage(_))));
        assert!(github.answer(&ctx, "hello").is_none());
        assert!(
            github.answer(&ctx, "pr 12").is_some()
                && github.answer(&ctx, "#4").is_some()
                && github.answer(&ctx, "PRS x").is_some()
        );
    }
}
