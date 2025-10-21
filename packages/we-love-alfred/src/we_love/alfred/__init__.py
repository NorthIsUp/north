from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from asyncio import TaskGroup, subprocess
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path as SyncPath
from typing import TYPE_CHECKING, Any, Callable, Self, TypedDict, Unpack
from urllib.parse import urlsplit, urlunsplit

import favicon
import httpx
from aiopath import AsyncPath

if TYPE_CHECKING:
    from collections.abc import Awaitable, Sequence
    from types import TracebackType

    from typing_extensions import Required

logger = logging.getLogger(__name__)

HOME = AsyncPath(SyncPath.home())


def _just_netloc(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


@dataclass
class BaseModel:
    """pydantic-like model with some additional methods."""

    @classmethod
    def model_validate_json(cls, v: str) -> Self:
        return cls.model_validate(json.loads(v))

    @classmethod
    def model_validate(cls, v: Any) -> Self:
        match v:
            case dict():
                return cls(**v)
            case object() if isinstance(v, cls):
                return cls(**v.__dict__)
            case _:
                raise ValueError(f"Invalid {cls.__name__}: {v}")

    def model_dump(self, exclude_none: bool = False) -> dict[str, Any]:
        data = {}
        for k, _v in self.__dataclass_fields__.items():
            match getattr(self, k):
                case BaseModel() as v:
                    data[k] = v.model_dump()
                case list() | tuple() as v:
                    data[k] = [_.model_dump() for _ in v]
                case dict() as v:
                    data[k] = v
                case None if exclude_none:
                    continue
                case v:
                    data[k] = v

        return data

    def model_dump_json(self, indent: int = 2, exclude_none: bool = False) -> str:
        return json.dumps(self.model_dump(exclude_none=exclude_none), indent=indent)


@dataclass
class AwsAccount(BaseModel):
    id: str
    name: str
    services: Sequence[str] = ()
    role_names: Sequence[str] = ("AdministratorAccess",)

    @classmethod
    def model_validate_list(cls, v: Any) -> list[Self]:
        match v:
            case "null" | None:
                return []
            case str() if v.startswith("{") and v.endswith("}"):
                return [cls.model_validate_json(v)]
            case str() if v.startswith("[") and v.endswith("]"):
                return [cls.model_validate(_) for _ in json.loads(v)]
            case list() | tuple():
                return [cls.model_validate(_) for _ in v]
            case _:
                raise ValueError(f"Invalid AWS accounts: {v}")


def _env[R](key: str, default: R, cast: Callable[[str | R], R]) -> Callable[[], R]:
    def _() -> R:
        return cast(os.environ.get(key, default))

    return _


@dataclass
class MenuItem(BaseModel):
    """Pydantic model for Alfred menu items."""

    title: str
    subtitle: str = ""
    alt: str | dict[str, str] | None = None
    cmd: str | dict[str, str] | None = None
    arg: str = ""
    uid: str = ""
    match: str = ""
    autocomplete: str = ""

    icon: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.alt, str):
            self.alt = {"subtitle": self.alt}
        if isinstance(self.cmd, str):
            self.cmd = {"subtitle": self.cmd}


@dataclass
class MenuCache(BaseModel):
    """Pydantic model for Alfred menu cache settings."""

    seconds: int
    loosereload: bool = True


@dataclass
class AlfredMenu(BaseModel):
    """Pydantic model for the complete Alfred menu structure."""

    cache: MenuCache
    items: list[MenuItem] = field(default_factory=list)


class AddItemArgs(TypedDict, total=False):
    item_type: str
    title: str
    subtitle: str
    arg: str
    url: str
    command: str
    path: str
    # Icon options
    icon: str
    glyph: str
    appicon: str
    clearbiticon: str
    urlicon: str
    favicon: str
    workflowicon: str
    filetype: str
    fileicon: str
    utiicon: str
    # Additional options
    uid: str
    match: str
    autocomplete: str


@dataclass
class AlfredWorkflow(BaseModel):
    """Alfred workflow generator for MaxCare."""

    cache_ttl: int = field(default=3600)
    home: AsyncPath = HOME
    xdg_cache_home: AsyncPath = HOME / ".cache"
    icon_cache: AsyncPath = HOME / ".cache" / "alfred-icons"
    menu_items: list[MenuItem] = field(default_factory=list)

    # SF Symbols glyphs mapping
    glyphs: dict[str, str] = field(
        # glyphs from apple's SF-Pro
        default_factory=lambda: {
            "terminal": "􀩼",
            "terminal-fill": "􀪏",
            "bookmark": "􀉞",
            "path": "􀈕",
            "file": "􀈷",
            "maxcare": "􀴿",
            "sparkles": "􀆿",
            "monitor-sparkles": "􁅋",
            "monitor-sparkles-fill": "􁅌",
            "bubbles-sparkles": "􁒉",
            "bubbles-sparkles-fill": "􁒊",
            "cloud": "􀇂",
        }
    )

    @cached_property
    def _item_queue(self) -> asyncio.Queue[AddItemArgs | None]:
        return asyncio.Queue()

    async def sfsymbol(self, symbol: str, _has_convert: dict[str, bool] = {}) -> str | None:
        """Generate SF Pro icon files for given symbol."""
        icon_stem = self.xdg_cache_home / f"font-icons/sf-pro-{symbol}"
        dark_path = icon_stem.with_suffix(".png").with_name(f"{icon_stem.stem}-dark.png")
        light_path = icon_stem.with_suffix(".png").with_name(f"{icon_stem.stem}-light.png")

        if not await dark_path.exists():
            if "convert" not in _has_convert:
                _has_convert["convert"] = (await subprocess.create_subprocess_exec("which", "convert")).returncode == 0

            if not _has_convert["convert"]:
                return None

            await dark_path.parent.mkdir(parents=True, exist_ok=True)

            async with TaskGroup() as tg:
                for mode, path in [("black", dark_path), ("white", light_path)]:
                    tg.create_task(
                        subprocess.create_subprocess_exec(
                            "convert",
                            "-background",
                            "none",
                            "-fill",
                            mode,
                            "-font",
                            str(self.home / "Library/Fonts/SF-Pro.ttf"),
                            "-pointsize",
                            "300",
                            f"label:{symbol}",
                            str(path),
                        )
                    )

        return str(dark_path) if (await dark_path.exists()) else None

    def generate_uid(self, title: str, subtitle: str, arg: str) -> str:
        """Generate unique ID for menu item."""
        content = f"{title} {subtitle} {arg}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def process_icon(self, icon_type: str, value: str, existing_icon: dict[str, str] | None = None) -> dict[str, str] | None:
        """Process different icon types and return icon dict."""
        if existing_icon and icon_type in {"appicon", "urlicon", "clearbiticon"}:
            return existing_icon

        match icon_type:
            case "icon" if "*" in value:
                if icon_path := await anext(AsyncPath().glob(value, case_sensitive=False), None):
                    return {"path": str(icon_path.absolute())}
                return None

            case "icon":
                return {"path": value}

            case "glyph":
                if value in self.glyphs:
                    icon_path = await self.sfsymbol(self.glyphs[value])
                    return {"path": icon_path} if icon_path else None
                elif await AsyncPath(value).exists():
                    return {"path": value}
                else:
                    print(
                        f"glyph: '{value}' does not exist",
                        file=__import__("sys").stderr,
                    )
                    return None

            case "filetype":
                return {"type": "filetype", "path": value}

            case "fileicon" | "utiicon":
                return {"type": "fileicon", "path": value}

            case "workflowicon":
                return {"path": f"./icons/{value}.png"}

            case "appicon":
                app_path = AsyncPath(f"/Applications/{value}.app/Contents/Resources/{value}.icns")
                icon_path = self.icon_cache / f"{value}.png"
                if await icon_path.exists():
                    return {"path": str(icon_path)}
                elif await app_path.exists():
                    icon_path.parent.mkdir(parents=True, exist_ok=True)
                    proc = await subprocess.create_subprocess_exec(
                        "sips",
                        "-s",
                        "format",
                        "png",
                        str(app_path),
                        "--out",
                        str(icon_path),
                    )
                    if proc.returncode == 0:
                        return {"path": str(icon_path)}
                    return None

            case "clearbiticon":
                domain = value.split("://")[-1].split("/")[0].split(":")[0]
                icon_url = f"https://logo.clearbit.com/{domain}"
                icon_path = self.icon_cache / f"{domain}.png"
                return await self._download_icon(icon_url, icon_path)

            case "urlicon":
                clean_url = value.replace("/", "_")
                icon_path = self.icon_cache / f"{clean_url}.png"
                return await self._download_icon(value, icon_path)

            case "favicon":
                value_url = urlsplit(value)

                async def _get_favicon() -> tuple[str, str]:
                    try:
                        icon = (await asyncio.to_thread(favicon.get, value))[0]
                    except Exception:
                        icon = (await asyncio.to_thread(favicon.get, urlunsplit(value_url._replace(path=""))))[0]

                    return (icon.url, f"favicon.{icon.format}")

                return await self._download_icon(
                    _get_favicon,
                    self.icon_cache / value_url.netloc / "favicon.*",
                )

        return None

    async def _download_icon(
        self,
        url: str | Callable[[], Awaitable[str]] | Callable[[], Awaitable[tuple[str, str]]],
        icon_path: AsyncPath,
    ) -> dict[str, str] | None:
        """Download icon from URL."""
        if icon_path.suffix == ".*" and (new_icon_path := await anext(icon_path.parent.glob(icon_path.name), None)):
            icon_path = new_icon_path

        if (await icon_path.exists()) and (await icon_path.stat()).st_size > 20:
            return {"path": str(icon_path)}

        if callable(url):
            match await url():
                case str(url):
                    pass
                case (str(url), str(filename)):
                    icon_path = icon_path.with_name(filename)

        try:
            icon_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Downloading icon from {url} to {icon_path}")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    timeout=2,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                    },
                )
                logger.debug(f"Response: {response.status_code}")
                response.raise_for_status()
                icon_path.write_bytes(response.content)

            return {"path": str(icon_path)}
        except httpx.HTTPError:
            return None

    def queue_item(self, item_type: str, /, **kwargs: Unpack[AddItemArgs]) -> None:
        self._item_queue.put_nowait({
            "item_type": item_type,
            **kwargs,
        })

    async def add_item(
        self,
        item_type: str,
        *,
        title: str,
        subtitle: str | None = None,
        arg: str | None = None,
        url: str | None = None,
        command: str | None = None,
        path: str | None = None,
        # Icon options
        icon: str | None = None,
        glyph: str | None = None,
        appicon: str | None = None,
        clearbiticon: str | None = None,
        urlicon: str | None = None,
        favicon: str | None = None,
        workflowicon: str | None = None,
        filetype: str | None = None,
        fileicon: str | None = None,
        utiicon: str | None = None,
        # Additional options
        uid: str | None = None,
        match: str | None = None,
        autocomplete: str | None = None,
        **kwargs: str | None,
    ) -> None:
        """Add a menu item based on type using keyword arguments."""
        item_args = {"title": title}
        icon_dict = None

        match item_type:
            case "easy":
                if not subtitle or not arg:
                    raise ValueError("easy items require 'title', 'subtitle', and 'arg'")
                item_args.update({"subtitle": subtitle, "arg": arg})

            case "url":
                if not url:
                    raise ValueError("url items require 'title' and 'url'")
                item_args.update({
                    "subtitle": subtitle or f"open {title} in browser ({url})",
                    "arg": f"open {url}",
                })
                # Default to favicon if no icon specified
                if not (icon or glyph or appicon or clearbiticon or urlicon or workflowicon or filetype or fileicon or utiicon):
                    favicon = url

            case "exec":
                if not command:
                    raise ValueError("exec items require 'title' and 'command'")
                item_args.update({"subtitle": subtitle or command, "arg": f"zsh://{command}"})
                # Default to terminal glyph if no glyph specified
                if not (icon or glyph or appicon or clearbiticon or urlicon or workflowicon or filetype or fileicon or utiicon):
                    glyph = "terminal"

            case _:
                raise ValueError(f"unknown item type: '{item_type}'")

        # Handle path argument
        if path:
            path_obj = AsyncPath(path).expanduser()
            item_args.setdefault("uid", path)
            item_args.setdefault("arg", str(path_obj.relative_to(self.home, walk_up=True)))
            item_args.setdefault("title", path_obj.name)

        # Process icon options (in priority order)
        for icon_type, icon_value in {
            "icon": icon,
            "glyph": glyph,
            "favicon": favicon,
            "appicon": appicon,
            "clearbiticon": clearbiticon,
            "urlicon": urlicon,
            "workflowicon": workflowicon,
            "filetype": filetype,
            "fileicon": fileicon,
            "utiicon": utiicon,
        }.items():
            if icon_value:
                icon_dict = await self.process_icon(icon_type, icon_value, icon_dict)
                break

        # Set additional overrides
        if uid:
            item_args["uid"] = uid
        if match:
            item_args["match"] = match
        if autocomplete:
            item_args["autocomplete"] = autocomplete

        # Add any additional kwargs
        item_args.update({k: v for k, v in kwargs.items() if v is not None})

        # Generate UID and set defaults
        generated_uid = self.generate_uid(
            item_args.get("title", ""),
            item_args.get("subtitle", ""),
            item_args.get("arg", ""),
        )
        item_args.setdefault("uid", generated_uid)
        item_args.setdefault(
            "match",
            f"{item_args.get('title', '')} {item_args.get('subtitle', '')} {item_args.get('arg', '')}",
        )
        item_args.setdefault("autocomplete", item_args.get("arg", ""))

        # Create menu item
        menu_item = MenuItem(icon=icon_dict, **item_args)

        self.menu_items.append(menu_item)

    def add_url(
        self,
        title: str,
        url: str,
        /,
        **kwargs: Unpack[AddItemArgs],
    ) -> None:
        """Add a URL menu item."""
        url = url.replace("http://", "https://")

        kwargs["title"] = title
        kwargs["url"] = url

        self.queue_item("url", **kwargs)

    def add_exec(
        self,
        title: str,
        command: str,
        /,
        **kwargs: Unpack[AddItemArgs],
    ) -> None:
        """Add an executable command menu item."""
        kwargs["title"] = title
        kwargs["command"] = command
        self.queue_item("exec", **kwargs)

    def add_easy(
        self,
        title: str,
        subtitle: str,
        arg: str,
        /,
        **kwargs: Unpack[AddItemArgs],
    ) -> None:
        """Add a simple menu item with title, subtitle, and arg."""
        kwargs["title"] = title
        kwargs["subtitle"] = subtitle
        kwargs["arg"] = arg
        self.queue_item("easy", **kwargs)

    def add_config_items(self) -> None:
        """Add configuration menu items."""
        cache_path = self.icon_cache / "*"
        self.add_exec(
            "clear cache",
            f'[[ -d "{self.icon_cache}/" ]] && rm "{cache_path}"',
        )

    async def process_items(self) -> None:
        """Process items in the queue."""
        self._item_queue.put_nowait(None)

        async def consumer() -> None:
            while True:
                item = await self._item_queue.get()
                if item is None:
                    break
                tg.create_task(self.add_item(**item))

        async with TaskGroup() as tg:
            tg.create_task(consumer())

    def format_menu(self) -> str:
        """Generate the complete Alfred menu JSON."""
        menu = AlfredMenu(cache=MenuCache(seconds=self.cache_ttl), items=self.menu_items)
        return menu.model_dump_json(indent=2, exclude_none=True)

    def print_menu(self) -> None:
        """Print the complete Alfred menu JSON."""
        print(self.format_menu())

    def __str__(self) -> str:
        return self.format_menu()
