//! Detached jobs whose progress Alfred redraws as a spinner until they finish.
//!
//! A [`Job`] re-runs this binary in the background, and that run reports into a
//! status file. Each keystroke (and each rerun Alfred makes while the job runs)
//! shows [`Status::menu`]: an animated spinner, a progress bar when there's a
//! percentage, and the final message once the job is done.

use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use tokio::fs;

use crate::cache::{atomic_write, spawn_self, with_suffix};
use crate::{Item, Menu, Result};

/// Seconds between Alfred's redraws while a job runs.
pub const RERUN: f64 = 0.1;
const SPINNER: [char; 10] = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

/// What a job last reported.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Status {
    pub running: bool,
    pub message: String,
    /// Percentage done, drawn as a bar in the subtitle.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub progress: Option<u8>,
}

impl Status {
    pub fn running(message: impl Into<String>) -> Self {
        Self {
            running: true,
            message: message.into(),
            progress: None,
        }
    }

    pub fn finished(message: impl Into<String>) -> Self {
        Self {
            running: false,
            message: message.into(),
            progress: None,
        }
    }

    /// The live view: a spinner and Alfred rerunning every [`RERUN`] seconds while running, the
    /// final message once done. The subtitle is the progress bar, else `subtitle`.
    #[must_use]
    pub fn menu(&self, subtitle: &str) -> Menu {
        let title = if self.running {
            format!("{}  {}", spinner(), self.message)
        } else {
            self.message.clone()
        };
        let subtitle = self
            .progress
            .map_or_else(|| subtitle.to_owned(), progress_bar);
        Menu {
            rerun: self.running.then_some(RERUN),
            ..Menu::from_iter([Item::message(title, subtitle)])
        }
    }
}

/// A detached run of this binary that reports its progress into a status file.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Job {
    status: PathBuf,
}

impl Job {
    pub fn at(status: impl Into<PathBuf>) -> Self {
        Self {
            status: status.into(),
        }
    }

    /// Re-run this binary with `args` unless a run started within `every`; returns whether one
    /// started, after reporting `message` for it.
    pub async fn start<I, S>(&self, args: I, every: Duration, message: &str) -> bool
    where
        I: IntoIterator<Item = S>,
        S: AsRef<std::ffi::OsStr>,
    {
        let started = spawn_self(args, &with_suffix(&self.status, ".pid"), every).await;
        if started {
            let _ = self.report(&Status::running(message)).await;
        }
        started
    }

    /// Record `status` for the live view.
    ///
    /// # Errors
    ///
    /// I/O errors writing the status file.
    pub async fn report(&self, status: &Status) -> Result<()> {
        // Atomic: the live view reads it ten times a second.
        atomic_write(&self.status, &serde_json::to_vec(status)?).await
    }

    pub async fn status(&self) -> Option<Status> {
        serde_json::from_slice(&fs::read(&self.status).await.ok()?).ok()
    }

    /// Forget the last status, e.g. once the job's result speaks for itself.
    pub async fn clear(&self) {
        let _ = fs::remove_file(&self.status).await;
    }
}

/// The spinner frame for now; frames advance every [`RERUN`] seconds.
fn spinner() -> char {
    let tick = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        / 100;
    SPINNER[usize::try_from(tick % SPINNER.len() as u128).unwrap_or_default()]
}

/// Fifty cells of 2% each: `▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▱▱…▱ 37%`. There is no partial ▰, so cells round down.
pub(crate) fn progress_bar(percent: u8) -> String {
    let percent = percent.min(100);
    let filled = usize::from(percent / 2);
    format!(
        "{}{} {percent}%",
        "▰".repeat(filled),
        "▱".repeat(50 - filled)
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn progress_bar_has_fifty_two_percent_cells() {
        assert_eq!(progress_bar(0), format!("{} 0%", "▱".repeat(50)));
        assert_eq!(
            progress_bar(37),
            format!("{}{} 37%", "▰".repeat(18), "▱".repeat(32))
        );
        assert_eq!(progress_bar(100), format!("{} 100%", "▰".repeat(50)));
        assert_eq!(progress_bar(250), progress_bar(100));
    }

    #[test]
    fn running_spins_and_reruns_finished_settles() {
        let running = Status::running("Building").menu("hold on");
        assert_eq!(running.rerun, Some(RERUN));
        assert!(
            running.items[0].title.ends_with("  Building")
                && SPINNER
                    .iter()
                    .any(|c| running.items[0].title.starts_with(*c))
        );
        assert_eq!(running.items[0].subtitle, "hold on");
        let done = Status::finished("Done").menu("hold on");
        assert_eq!((done.rerun, done.items[0].title.as_str()), (None, "Done"));
        let downloading = Status {
            progress: Some(50),
            ..Status::running("Downloading")
        }
        .menu("x");
        assert_eq!(downloading.items[0].subtitle, progress_bar(50));
    }

    #[tokio::test]
    async fn reports_round_trip_and_clear() {
        let dir = tempfile::tempdir().unwrap();
        let job = Job::at(dir.path().join("job.json"));
        assert_eq!(job.status().await, None);
        job.report(&Status::running("one")).await.unwrap();
        assert_eq!(job.status().await, Some(Status::running("one")));
        job.clear().await;
        assert_eq!(job.status().await, None);
    }
}
