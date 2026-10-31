"""Okta app tiles as Alfred items, as an opt-in mixin for `AlfredWorkflow`.

Okta needs a public native OIDC app with the device authorization and refresh
token grants and the `okta.users.read.self` API scope granted. Until the user
connects, the menu shows one connect item; it runs the workflow script with
`okta-login`, which should call `OktaAppsMixin.okta_login()` and rebuild the
menu. The rotating refresh token lives in the macOS Keychain, and the app list
is cached for `okta_apps_ttl`.
"""

from __future__ import annotations

import asyncio
import shlex
import sys
from asyncio import create_subprocess_exec, sleep
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal, Self
from uuid import uuid4

import httpx
from anyio import Path as AsyncPath
from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter, ValidationError
from we_love.alfred.fast import cache_path
from we_love.alfred.workflow import AlfredWorkflow

if TYPE_CHECKING:
    from collections.abc import Sequence

__lazy_modules__ = ("httpx",)

SCOPE = "offline_access okta.users.read.self"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


class OktaDeviceCode(BaseModel):
    device_code: str
    verification_uri_complete: str
    expires_in: timedelta = Field(gt=timedelta())
    interval: timedelta = Field(default=timedelta(seconds=5), gt=timedelta())


class OktaOAuthError(BaseModel):
    error: str


class OktaTokens(BaseModel):
    access_token: str
    refresh_token: str


class OktaAppLink(BaseModel, populate_by_name=True):
    label: str
    link_url: str = Field(alias="linkUrl")
    logo_url: str = Field("", alias="logoUrl")
    app_name: str = Field(alias="appName")
    hidden: bool = False


APP_LINKS = TypeAdapter(list[OktaAppLink])


class OktaAppsCache(BaseModel):
    v: Literal[1] = 1
    fetched_at: AwareDatetime
    links: list[OktaAppLink]

    @classmethod
    async def load(cls, path: AsyncPath) -> Self | None:
        try:
            return cls.model_validate_json(await path.read_text())
        except (OSError, ValidationError):
            return None

    def is_fresh(self, ttl: timedelta) -> bool:
        return datetime.now(UTC) - self.fetched_at < ttl

    async def save(self, path: AsyncPath) -> None:
        await path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            await temporary.write_text(self.model_dump_json(by_alias=True))
            await temporary.replace(path)
        finally:
            await temporary.unlink(missing_ok=True)


async def keychain(*args: str, stdin: str | None = None) -> str | None:
    """Run `security`; secrets go through stdin (`security -i`) so they never reach argv."""
    proc = await create_subprocess_exec(
        "/usr/bin/security",
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate(stdin.encode() if stdin is not None else None)
    return stdout.decode().strip() if proc.returncode == 0 else None


class OktaAppsMixin(AlfredWorkflow):
    """Mix into an `AlfredWorkflow` and pass `add_okta_items` to `builder()` to list the user's Okta apps."""

    okta_org: str = ""
    okta_client_id: str = ""
    okta_keychain_service: str = "alfred-okta"
    okta_apps_ttl: timedelta = timedelta(days=1)
    okta_connect_title: str = "Okta — connect to Okta and fetch applications list"

    async def resolve_okta_client_id(self) -> str | None:
        """Override to look the client ID up elsewhere, e.g. a secrets store."""
        return self.okta_client_id or None

    def okta_login_command(self) -> Sequence[str]:
        """The command the connect item runs; the script must handle `okta-login`."""
        return [sys.executable, sys.argv[0], "okta-login"]

    def okta_http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.okta_org)

    @property
    def okta_cache(self) -> AsyncPath:
        return AsyncPath(cache_path(f"{self.okta_keychain_service}-apps"))

    @property
    def _okta_keychain(self) -> tuple[str, ...]:
        return ("-s", self.okta_keychain_service, "-a", self.okta_org)

    async def _store_refresh_token(self, token: str) -> None:
        result = await keychain("-i", stdin=shlex.join(["add-generic-password", "-U", *self._okta_keychain, "-w", token]) + "\n")
        if result is None:
            raise RuntimeError("Could not save the Okta refresh token in Keychain")

    async def okta_login(self) -> None:
        """Device authorization grant: open Okta's approval page, keep the refresh token, then cache the apps."""
        if (client_id := await self.resolve_okta_client_id()) is None or not self.okta_org:
            raise RuntimeError("Okta is not configured: set okta_org and an Okta client ID")
        async with self.okta_http() as session:
            response = await session.post("/oauth2/v1/device/authorize", data={"client_id": client_id, "scope": SCOPE})
            device = OktaDeviceCode.model_validate_json(response.raise_for_status().content)
            browser = await create_subprocess_exec("open", device.verification_uri_complete)
            if await browser.wait() != 0:
                raise RuntimeError("Could not open the Okta authorization page")
            async with asyncio.timeout(device.expires_in.total_seconds()):
                while True:
                    await sleep(device.interval.total_seconds())
                    response = await session.post(
                        "/oauth2/v1/token",
                        data={"client_id": client_id, "grant_type": DEVICE_GRANT, "device_code": device.device_code},
                    )
                    if response.is_success:
                        await self._store_refresh_token(OktaTokens.model_validate_json(response.content).refresh_token)
                        break
                    error = OktaOAuthError.model_validate_json(response.content).error
                    if error == "slow_down":
                        device.interval += timedelta(seconds=5)
                    if error not in {"authorization_pending", "slow_down"}:
                        response.raise_for_status()
        await self.fetch_okta_apps(client_id)

    async def fetch_okta_apps(self, client_id: str) -> OktaAppsCache | None:
        """Exchange the Keychain refresh token and cache the user's app tiles; None when not connected."""
        if (refresh_token := await keychain("find-generic-password", *self._okta_keychain, "-w")) is None:
            return None
        async with self.okta_http() as session:
            response = await session.post(
                "/oauth2/v1/token",
                data={"client_id": client_id, "grant_type": "refresh_token", "refresh_token": refresh_token, "scope": SCOPE},
            )
            if response.status_code in {400, 401}:
                self.logger.warning("Okta refresh token rejected: %s", response.status_code)
                return None
            tokens = OktaTokens.model_validate_json(response.raise_for_status().content)
            # Refresh tokens may rotate, so the old one can stop working after the leeway.
            await self._store_refresh_token(tokens.refresh_token)
            response = await session.get("/api/v1/users/me/appLinks", headers={"Authorization": f"Bearer {tokens.access_token}"})
            links = APP_LINKS.validate_json(response.raise_for_status().content)
        apps = OktaAppsCache(fetched_at=datetime.now(UTC), links=[link for link in links if not link.hidden])
        await apps.save(self.okta_cache)
        return apps

    async def add_okta_items(self) -> None:
        """App tiles from the cache, refetched once it is older than `okta_apps_ttl`; a connect item until connected."""
        if not self.okta_org:
            return
        apps = await OktaAppsCache.load(self.okta_cache)
        if apps is None or not apps.is_fresh(self.okta_apps_ttl):
            if (client_id := await self.resolve_okta_client_id()) is None:
                return
            try:
                apps = await self.fetch_okta_apps(client_id)
            except httpx.HTTPError as e:
                # Keep serving the stale tiles through an Okta outage.
                self.logger.warning("Okta app refresh failed: %s", e)
        if apps is None:
            self.add_exec(
                self.okta_connect_title,
                shlex.join(self.okta_login_command()),
                subtitle="Approve in the browser to list your Okta apps",
                match="okta connect sign in login",
            )
            return
        for link in apps.links:
            self.add_url(link.label, link.link_url, subtitle="Okta", urlicon=link.logo_url, match=f"okta {link.label} {link.app_name}")
