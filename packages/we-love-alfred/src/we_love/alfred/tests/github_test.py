"""Tests for the cached GitHub PR menu."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol

import pytest
from we_love.alfred import github
from we_love.alfred.github import PullRequest, PullRequestCache, fuzzy_match, menu_json

if TYPE_CHECKING:
    from pathlib import Path


def row(number: int, title: str, author: str, updated: str = "2026-10-30T12:00:00Z", *, draft: bool = False) -> dict[str, object]:
    return {
        "number": number,
        "title": title,
        "author": {"login": author, "name": author.title(), "is_bot": False},
        "isDraft": draft,
        "updatedAt": updated,
        "url": f"https://github.com/acme/app/pull/{number}",
    }


ROWS = [
    row(4468, "feat(fhir): ServiceRequest", "NorthIsUp", "2026-10-29T12:00:00Z"),
    row(4496, "refactor(notifications): channel updates", "NorthIsUp", "2026-10-30T12:00:00Z", draft=True),
    row(4401, "fix(labs): sandbox cap", "sarahrhodes-clara", "2026-10-01T12:00:00Z"),
]


class CacheFactory(Protocol):
    def __call__(self, rows: list[dict[str, object]] = ROWS, age: timedelta = timedelta()) -> PullRequestCache: ...


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    commands: list[list[str]] = []

    class Child:
        pid: int = 12345

    def spawn(command: list[str], *, stdin: int, stdout: int, stderr: int, start_new_session: bool, env: dict[str, str]) -> Child:
        commands.append(command)
        assert env["PYDANTIC_DISABLE_PLUGINS"] == "__all__"
        return Child()

    monkeypatch.setattr(github.subprocess, "Popen", spawn)
    return commands


@pytest.fixture
def make_cache(tmp_path: Path) -> CacheFactory:
    """A cache file holding `rows`, aged `age` so tests never reach `gh`."""

    def _make(rows: list[dict[str, object]] = ROWS, age: timedelta = timedelta()) -> PullRequestCache:
        path = tmp_path / "prs.json"
        path.write_text(json.dumps(rows), encoding="utf-8")
        mtime = time.time() - age.total_seconds()
        os.utime(path, (mtime, mtime))
        return PullRequestCache(repo="acme/app", path=path)

    return _make


def test_fuzzy_match_requires_every_term_in_order() -> None:
    assert fuzzy_match(["ntf", "chan"], "Notifications: channel updates")
    assert not fuzzy_match(["tfn"], "fit")


def test_from_json_parses_gh_row() -> None:
    pr = PullRequest.from_json(ROWS[1])
    assert pr == PullRequest(
        4496,
        "refactor(notifications): channel updates",
        "NorthIsUp",
        True,
        datetime(2026, 10, 30, 12, tzinfo=UTC),
        "https://github.com/acme/app/pull/4496",
    )


def test_from_json_rejects_malformed_row() -> None:
    with pytest.raises(ValueError, match="unexpected PR payload"):
        PullRequest.from_json({"number": "4468"})


def test_list_from_json_sorts_newest_first() -> None:
    assert [pr.number for pr in PullRequest.list_from_json(json.dumps(ROWS))] == [4496, 4468, 4401]


def test_item_links_and_autocompletes() -> None:
    item = PullRequest.from_json(ROWS[1]).item()
    assert item["title"] == "#4496 refactor(notifications): channel updates"
    assert item.get("subtitle") == "@NorthIsUp · draft · updated 2026-10-30"
    assert item.get("arg") == "open https://github.com/acme/app/pull/4496"
    assert item.get("autocomplete") == "#4496"


def test_search_lists_all_open_prs(make_cache: CacheFactory) -> None:
    assert [i["title"][:5] for i in make_cache().search_items("")] == ["#4496", "#4468", "#4401"]


def test_search_partial_author_lists_authors_to_autocomplete(make_cache: CacheFactory) -> None:
    items = make_cache().search_items("@sar")
    assert [(i["title"], i.get("autocomplete"), i["valid"]) for i in items] == [("@sarahrhodes-clara", "prs @sarahrhodes-clara ", False)]


def test_search_known_author_and_terms_filter_prs(make_cache: CacheFactory) -> None:
    assert [i["title"][:5] for i in make_cache().search_items("@northisup fhir")] == ["#4468"]


def test_number_prefix_narrows(make_cache: CacheFactory) -> None:
    assert [i["title"][:5] for i in make_cache().number_items("4468")] == ["#4468"]


def test_number_prefix_lists_open_matches_before_direct_link(make_cache: CacheFactory) -> None:
    assert [i["title"][:5] for i in make_cache().number_items("44")] == ["#4496", "#4468", "#4401", "Open "]


def test_number_not_in_cache_offers_direct_link(make_cache: CacheFactory) -> None:
    items = make_cache().number_items("12")
    assert items == [make_cache().link_item(12)]
    assert items[0].get("arg") == "open https://github.com/acme/app/pull/12"


def test_number_text_matches_titles(make_cache: CacheFactory) -> None:
    assert [i["title"][:5] for i in make_cache().number_items("labs")] == ["#4401"]


def test_menu_json_uses_fallback_when_empty() -> None:
    assert json.loads(menu_json([], "No matching open PRs")) == {"items": [{"title": "No matching open PRs", "valid": False}]}


def test_warm_skips_fresh_cache(make_cache: CacheFactory, spawned: list[list[str]]) -> None:
    make_cache().warm()
    assert spawned == []


def test_warm_spawns_once_per_retry_window(make_cache: CacheFactory, spawned: list[list[str]]) -> None:
    cache = make_cache(age=timedelta(hours=2))
    cache.warm()
    cache.warm()
    assert spawned == [[github.sys.executable, "-m", "we_love.alfred.github", "refresh", "acme/app", str(cache.path), "--limit", "1000"]]


def test_main_rejects_unknown_command() -> None:
    with pytest.raises(SystemExit, match="usage"):
        github.main(["nope"])


@pytest.fixture
def gh_output(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    responses: list[str] = [json.dumps(ROWS)]

    def run(
        command: list[str], *, capture_output: bool, text: bool, timeout: int, env: dict[str, str], check: bool
    ) -> github.subprocess.CompletedProcess[str]:
        return github.subprocess.CompletedProcess(command, 0, stdout=responses[0], stderr="")

    monkeypatch.setattr(github.subprocess, "run", run)
    return responses


def test_fetch_rejects_invalid_payload_without_replacing_cache(make_cache: CacheFactory, gh_output: list[str]) -> None:
    cache = make_cache()
    previous = cache.path.read_text(encoding="utf-8")
    gh_output[0] = "not JSON"
    with pytest.raises(ValueError, match="Expecting value"):
        cache.fetch()
    assert cache.path.read_text(encoding="utf-8") == previous


def test_load_rebuilds_corrupt_cache(make_cache: CacheFactory, gh_output: list[str]) -> None:
    cache = make_cache()
    cache.path.write_text("broken", encoding="utf-8")
    assert len(cache.load()) == len(ROWS)


def test_warm_preserves_custom_limit(tmp_path: Path, spawned: list[list[str]]) -> None:
    PullRequestCache(repo="acme/app", path=tmp_path / "cache.json", limit=25).warm()
    assert spawned[0][-2:] == ["--limit", "25"]


def test_from_json_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone"):
        PullRequest.from_json(row(1, "Example", "author", "2026-10-30T12:00:00"))
