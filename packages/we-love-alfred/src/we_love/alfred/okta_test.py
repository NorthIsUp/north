from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, override

import httpx
import pytest
from we_love.alfred import okta
from we_love.alfred.okta import OktaAppLink, OktaAppsCache, OktaAppsMixin

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

LINKS = [
    {"label": "Sentry", "linkUrl": "https://example.okta.com/home/sentry/1/2", "logoUrl": "", "appName": "sentry", "hidden": False},
    {"label": "Hidden", "linkUrl": "https://example.okta.com/home/hidden/3/4", "logoUrl": "", "appName": "hidden", "hidden": True},
]


class Keychain:
    """Stands in for `security`: one stored token, and every token written."""

    def __init__(self, token: str | None) -> None:
        self.token = token
        self.writes: list[str] = []

    async def __call__(self, *args: str, stdin: str | None = None) -> str | None:
        if stdin is not None:
            self.writes.append(stdin)
            return ""
        return self.token


class Workflow(OktaAppsMixin):
    okta_org: str = "https://example.okta.com"
    okta_client_id: str = "client"
    okta_down: bool = False

    @override
    def okta_http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.okta_org, transport=httpx.MockTransport(okta_outage if self.okta_down else okta_api))


def okta_outage(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(503)


def okta_api(request: httpx.Request) -> httpx.Response:
    match request.url.path:
        case "/oauth2/v1/token" if b"refresh_token=refresh-1" in request.content:
            return httpx.Response(200, json={"access_token": "access", "refresh_token": "rotated"})
        case "/oauth2/v1/token":
            return httpx.Response(400, json={"error": "invalid_grant"})
        case "/api/v1/users/me/appLinks" if request.headers["Authorization"] == "Bearer access":
            return httpx.Response(200, json=LINKS)
        case _:
            return httpx.Response(500)


@pytest.fixture
def keychain(monkeypatch: pytest.MonkeyPatch) -> Keychain:
    stub = Keychain(None)
    monkeypatch.setattr(okta, "keychain", stub)
    return stub


@pytest.fixture
def make_workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, keychain: Keychain) -> Callable[..., Workflow]:
    """A workflow whose app cache lives in tmp_path, aged `age` when `cached` holds links."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    def _make(*, cached: list[dict[str, object]] | None = None, age: timedelta = timedelta(), stored: str | None = None) -> Workflow:
        keychain.token = stored
        workflow = Workflow()
        if cached is not None:
            fetched_at = datetime.now(UTC) - age
            (tmp_path / "alfred").mkdir(exist_ok=True)
            (tmp_path / "alfred" / "alfred-okta-apps.json").write_text(
                json.dumps({"v": 1, "fetched_at": fetched_at.isoformat(), "links": cached})
            )
        return workflow

    return _make


async def titles(workflow: Workflow) -> list[str]:
    await workflow.add_okta_items()
    await workflow.process_items()
    return [item.title for item in workflow.menu_items]


async def test_fresh_cache_serves_tiles_without_okta(make_workflow: Callable[..., Workflow]) -> None:
    workflow = make_workflow(cached=LINKS[:1])
    assert await titles(workflow) == ["Sentry"]


async def test_not_connected_shows_connect_item(make_workflow: Callable[..., Workflow]) -> None:
    workflow = make_workflow()
    assert await titles(workflow) == ["Okta — connect to Okta and fetch applications list"]


async def test_stale_cache_refetches_rotates_token_and_drops_hidden(make_workflow: Callable[..., Workflow], keychain: Keychain) -> None:
    workflow = make_workflow(cached=[], age=timedelta(days=2), stored="refresh-1")
    assert await titles(workflow) == ["Sentry"]
    assert keychain.writes == ["add-generic-password -U -s alfred-okta -a https://example.okta.com -w rotated\n"]
    cache = await OktaAppsCache.load(workflow.okta_cache)
    assert cache is not None
    assert [link.label for link in cache.links] == ["Sentry"]


async def test_rejected_refresh_token_shows_connect_item(make_workflow: Callable[..., Workflow]) -> None:
    workflow = make_workflow(stored="revoked")
    assert await titles(workflow) == ["Okta — connect to Okta and fetch applications list"]


async def test_unconfigured_org_adds_nothing(make_workflow: Callable[..., Workflow]) -> None:
    workflow = make_workflow()
    workflow.okta_org = ""
    assert await titles(workflow) == []


def test_app_link_round_trips_by_alias() -> None:
    link = OktaAppLink.model_validate(LINKS[0])
    assert OktaAppLink.model_validate_json(link.model_dump_json(by_alias=True)) == link


async def test_okta_outage_keeps_stale_tiles(make_workflow: Callable[..., Workflow]) -> None:
    workflow = make_workflow(cached=LINKS[:1], age=timedelta(days=2), stored="refresh-1")
    workflow.okta_down = True
    assert await titles(workflow) == ["Sentry"]
