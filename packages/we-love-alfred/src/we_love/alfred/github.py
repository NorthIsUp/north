"""Open GitHub PRs as Alfred items: `prs [@author] [terms]` and `#<number|text>`.

Stdlib only and synchronous, so a Script Filter can answer a keystroke from the
cache without importing pydantic, httpx or anyio. `gh pr list` output is cached
for `ttl` and refreshed by a detached `python -m we_love.alfred.github refresh`
once stale, so only the very first lookup waits on `gh`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

# GUI apps do not inherit the interactive shell's PATH, so `gh` may be missing from it.
TOOL_PATH = os.pathsep.join((
    os.environ.get("PATH", os.defpath),
    os.path.expanduser("~/.local/share/mise/shims"),
    os.path.expanduser("~/.local/bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
))


class AlfredText(TypedDict):
    copy: str
    largetype: str


class AlfredItem(TypedDict):
    title: str
    valid: bool
    subtitle: NotRequired[str]
    arg: NotRequired[str]
    autocomplete: NotRequired[str]
    text: NotRequired[AlfredText]


def fuzzy_match(terms: Iterable[str], text: str) -> bool:
    """Every term's characters appear in order in `text`, case-insensitively."""
    text = text.casefold()
    return all(re.search(".*?".join(map(re.escape, term.casefold())), text) for term in terms)


def menu_json(items: Sequence[AlfredItem], empty: str) -> str:
    """Script Filter JSON; a non-actionable `empty` row stands in for no results."""
    fallback: list[AlfredItem] = [{"title": empty, "valid": False}]
    return json.dumps({"items": list(items) or fallback})


def _age(path: Path) -> timedelta | None:
    try:
        return timedelta(seconds=time.time() - path.stat().st_mtime)
    except FileNotFoundError:
        return None


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    author: str
    is_draft: bool
    updated_at: datetime
    url: str

    @classmethod
    def from_json(cls, raw: object) -> Self:
        """One row of `gh pr list --json number,title,author,isDraft,updatedAt,url`."""
        match raw:
            case {
                "number": int(number),
                "title": str(title),
                "author": {"login": str(author)},
                "isDraft": bool(is_draft),
                "updatedAt": str(updated_at),
                "url": str(url),
            }:
                return cls(number, title, author, is_draft, datetime.fromisoformat(updated_at), url)
            case _:
                raise ValueError(f"unexpected PR payload: {raw!r}")

    @classmethod
    def list_from_json(cls, data: str) -> list[Self]:
        """All rows, most recently updated first."""
        match json.loads(data):
            case list(rows):
                return sorted(map(cls.from_json, rows), key=lambda pr: pr.updated_at, reverse=True)
            case other:
                raise ValueError(f"expected a list of PRs, got {type(other).__name__}")

    def matches(self, terms: Iterable[str]) -> bool:
        return fuzzy_match(terms, f"{self.number} {self.title}")

    def item(self) -> AlfredItem:
        draft = " · draft" if self.is_draft else ""
        return {
            "title": f"#{self.number} {self.title}",
            "subtitle": f"@{self.author}{draft} · updated {self.updated_at:%Y-%m-%d}",
            "arg": f"open {self.url}",
            "autocomplete": f"#{self.number}",
            "valid": True,
            "text": {"copy": self.url, "largetype": self.title},
        }


@dataclass(frozen=True)
class PullRequestCache:
    """Open PRs for `repo`, cached at `path` and refreshed in the background once older than `ttl`."""

    repo: str
    path: Path
    ttl: timedelta = timedelta(hours=1)
    retry_every: timedelta = timedelta(minutes=1)
    limit: int = 1000

    @property
    def warming_path(self) -> Path:
        # Left in place after a refresh, so a failing `gh` is retried at most once per `retry_every`.
        return self.path.with_name(self.path.name + ".warming")

    def fetch(self) -> None:
        """Run `gh` now and atomically replace the cache; a payload that won't parse is never written."""
        gh = shutil.which("gh", path=TOOL_PATH) or "gh"
        out = subprocess.run(
            [
                gh,
                "pr",
                "list",
                "-R",
                self.repo,
                "--state",
                "open",
                "--limit",
                str(self.limit),
                "--json",
                "number,title,author,isDraft,updatedAt,url",
            ],
            capture_output=True,
            text=True,
            timeout=25,
            env={**os.environ, "PATH": TOOL_PATH},
            check=False,
        )
        if out.returncode:
            raise RuntimeError(out.stderr.strip() or "gh pr list failed")
        PullRequest.list_from_json(out.stdout)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(out.stdout)
        tmp.replace(self.path)

    def is_fresh(self) -> bool:
        return (cached := _age(self.path)) is not None and cached < self.ttl

    def warm(self) -> None:
        """Start a detached refresh if the cache is stale and no refresh started within `retry_every`."""
        if self.is_fresh():
            return
        if (warming := _age(self.warming_path)) is not None and warming < self.retry_every:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.warming_path.touch()
        subprocess.Popen(
            [sys.executable, "-m", __name__, "refresh", self.repo, str(self.path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    def load(self) -> list[PullRequest]:
        """Cached PRs, even if stale; fetches synchronously only when there is no cache yet."""
        if _age(self.path) is None:
            self.fetch()
        return PullRequest.list_from_json(self.path.read_text())

    def search_items(self, args: str, *, keyword: str = "prs") -> list[AlfredItem]:
        """`[@author] [terms]`; an `@author` matching no login lists authors to autocomplete instead."""
        prs = self.load()
        words = args.split()
        authors = [word[1:] for word in words if word.startswith("@")]
        terms = [word for word in words if not word.startswith("@")]
        logins = sorted({pr.author for pr in prs}, key=str.casefold)
        known = {login.casefold() for login in logins}

        if pending := [author for author in authors if author.casefold() not in known]:
            return [
                {
                    "title": f"@{login}",
                    "subtitle": f"{sum(pr.author == login for pr in prs)} open PRs",
                    "autocomplete": f"{keyword} @{login} ",
                    "valid": False,
                }
                for login in logins
                if fuzzy_match([pending[-1]], login)
            ]

        wanted = {author.casefold() for author in authors}
        return [pr.item() for pr in prs if (not wanted or pr.author.casefold() in wanted) and pr.matches(terms)]

    def number_items(self, needle: str) -> list[AlfredItem]:
        """Text after `#`: digits narrow by number prefix, anything else by title."""
        needle = needle.strip()
        items = [pr.item() for pr in self.load() if (str(pr.number).startswith(needle) if needle.isdigit() else pr.matches(needle.split()))]
        if needle.isdigit() and not any(item.get("autocomplete") == f"#{needle}" for item in items):
            # Closed and merged PRs are not cached; still offer the direct link, after any open matches.
            items.append(self.link_item(int(needle)))
        return items

    def link_item(self, number: int) -> AlfredItem:
        url = f"https://github.com/{self.repo}/pull/{number}"
        return {"title": f"Open PR #{number}", "subtitle": url, "arg": f"open {url}", "valid": True}


def main(argv: Sequence[str]) -> None:
    match list(argv):
        case ["refresh", repo, path]:
            PullRequestCache(repo=repo, path=Path(path)).fetch()
        case _:
            raise SystemExit("usage: python -m we_love.alfred.github refresh <owner/repo> <cache.json>")


if __name__ == "__main__":
    main(sys.argv[1:])
