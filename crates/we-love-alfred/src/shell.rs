//! Process helpers for Alfred's minimal environment.

use std::env;
use std::ffi::OsString;
use std::process::Stdio;
use std::time::Duration;

use tokio::process::Command;

use crate::cache::home;
use crate::{Error, Result};

/// Same rules as Python's `shlex.quote`: safe strings pass through unquoted.
#[must_use]
pub fn quote(s: &str) -> String {
    let safe = |c: char| c.is_ascii_alphanumeric() || "@%+=:,./_-".contains(c);
    if !s.is_empty() && s.chars().all(safe) {
        s.to_owned()
    } else {
        format!("'{}'", s.replace('\'', r#"'"'"'"#))
    }
}

pub fn join<S: AsRef<str>>(parts: impl IntoIterator<Item = S>) -> String {
    parts
        .into_iter()
        .map(|part| quote(part.as_ref()))
        .collect::<Vec<_>>()
        .join(" ")
}

/// `$PATH` plus mise, Homebrew and `~/.local/bin`: Alfred doesn't inherit the login shell's PATH.
#[must_use]
pub fn tool_path() -> OsString {
    let home = home();
    let current = env::var_os("PATH").unwrap_or_else(|| "/usr/bin:/bin".into());
    let extra = [
        home.join(".local/share/mise/shims"),
        home.join(".local/bin"),
        "/opt/homebrew/bin".into(),
        "/usr/local/bin".into(),
    ];
    env::join_paths(env::split_paths(&current).chain(extra)).unwrap_or(current)
}

/// A command found on [`tool_path`].
pub fn tool(program: impl AsRef<std::ffi::OsStr>) -> Command {
    let mut command = Command::new(program);
    command.env("PATH", tool_path());
    command
}

/// Stdout of `command`; a nonzero exit is an error carrying stderr. Killed after `timeout`.
///
/// # Errors
///
/// [`Error::Io`] if it can't start, [`Error::Timeout`] after `timeout`, and [`Error::Command`] for a nonzero exit.
pub async fn output(command: &mut Command, timeout: Duration) -> Result<String> {
    let program = command
        .as_std()
        .get_program()
        .to_string_lossy()
        .into_owned();
    let child = command.stdin(Stdio::null()).kill_on_drop(true).output();
    let out = tokio::time::timeout(timeout, child)
        .await
        .map_err(|_| Error::Timeout(program.clone()))??;
    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr).trim().to_owned();
        let stderr = if stderr.is_empty() {
            format!("exited with {}", out.status)
        } else {
            stderr
        };
        return Err(Error::Command { program, stderr });
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quotes_like_shlex() {
        assert_eq!(quote("plain/path-1.json"), "plain/path-1.json");
        assert_eq!(quote(""), "''");
        assert_eq!(quote("it's here"), r#"'it'"'"'s here'"#);
        assert_eq!(join(["open", "a b"]), "open 'a b'");
    }

    #[tokio::test]
    async fn output_reports_failures_and_timeouts() {
        let _serial = crate::serial().await;
        let sh = |script: &str| {
            let mut command = Command::new("/bin/sh");
            command.args(["-c", script]);
            command
        };
        assert_eq!(
            output(&mut sh("echo hi"), Duration::from_secs(5))
                .await
                .unwrap(),
            "hi\n"
        );
        let failed = output(&mut sh("echo denied >&2; exit 1"), Duration::from_secs(5)).await;
        assert!(matches!(failed, Err(Error::Command { stderr, .. }) if stderr == "denied"));
        assert!(matches!(
            output(&mut sh("sleep 5"), Duration::from_millis(50)).await,
            Err(Error::Timeout(_))
        ));
    }
}
