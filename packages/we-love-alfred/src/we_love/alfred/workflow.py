from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from asyncio import TaskGroup, subprocess
from functools import cached_property
from typing import TYPE_CHECKING, Any, Self, TypedDict, Unpack, cast
from urllib.parse import urlsplit, urlunsplit

import asyncstdlib as a
import favicon
import httpx
from anyio import Path as AsyncPath
from pydantic import Field, ValidationError
from we_love.alfred.editor import Editor, Editors
from we_love.alfred.model import AlfredBaseModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Sequence
    from os import PathLike


HOME = AsyncPath(os.path.expanduser("~"))


def _glob(path: AsyncPath, pattern: str, case_sensitive: bool = False, recurse_symlinks: bool = False) -> AsyncIterator[AsyncPath]:
    from anyio._core._fileio import _PathIterator

    iters = path._path.glob(
        pattern,
        case_sensitive=case_sensitive,
        recurse_symlinks=recurse_symlinks,
    )
    return _PathIterator(iters)


def _just_netloc(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


class AwsAccount(AlfredBaseModel):
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


class MenuItem(AlfredBaseModel):
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


class MenuCache(AlfredBaseModel):
    """Pydantic model for Alfred menu cache settings."""

    seconds: int = 3600  # 1 hour
    loosereload: bool = True


class AlfredMenu(AlfredBaseModel):
    """Pydantic model for the complete Alfred menu structure."""

    cache: MenuCache
    items: list[MenuItem] = Field(default_factory=list)


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


class AlfredWorkflow(AlfredBaseModel, ignored_types=(AsyncPath,), arbitrary_types_allowed=True):
    """Alfred workflow generator for MaxCare."""

    cache_ttl: int = 3600
    home: AsyncPath = HOME
    xdg_cache_home: AsyncPath = HOME / ".cache"
    icon_cache: AsyncPath = HOME / ".cache" / "alfred-icons"
    menu_items: list[MenuItem] = Field(default_factory=list)

    # SF Symbols glyphs mapping
    glyphs: dict[str, str] = Field(
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
    def logger(self) -> logging.Logger:
        return logging.getLogger(__name__)

    @cached_property
    def _item_queue(self) -> asyncio.Queue[AddItemArgs]:
        return asyncio.Queue()

    @cached_property
    async def _has_magick_bin(self) -> bool:
        async def _() -> bool:
            proc = await subprocess.create_subprocess_exec("which", "magick", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await proc.wait()
            return proc.returncode == 0

        return await asyncio.create_task(_())

    async def sfsymbol(self, symbol: str) -> str | None:
        """Generate SF Pro icon files for given symbol."""
        icon_stem = self.xdg_cache_home / f"font-icons/sf-pro-{symbol}"
        dark_path = icon_stem.with_suffix(".png").with_name(f"{icon_stem.stem}-dark.png")
        light_path = icon_stem.with_suffix(".png").with_name(f"{icon_stem.stem}-light.png")

        if not await dark_path.exists():
            if not await self._has_magick_bin:
                return None

            await dark_path.parent.mkdir(parents=True, exist_ok=True)

            async with TaskGroup() as tg:
                for mode, path in [("black", dark_path), ("white", light_path)]:
                    tg.create_task(
                        subprocess.create_subprocess_exec(
                            "magick",
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

    async def process_icon(  # noqa: PLR0912
        self,
        icon_type: str,
        value: str,
        existing_icon: dict[str, str] | None = None,
    ) -> dict[str, str] | None:
        """Process different icon types and return icon dict."""
        if existing_icon and icon_type in {"appicon", "urlicon", "clearbiticon"}:
            return existing_icon

        match icon_type:
            case "icon" if "*" in value:
                async for icon_path in _glob(self.icon_cache, value, case_sensitive=False):
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
                if value.endswith(".icns"):
                    app_path = AsyncPath(value)
                    icon_path = self.icon_cache / f"{app_path.stem}.png"
                else:
                    app_path = AsyncPath(f"/Applications/{value}.app/Contents/Resources/{value}.icns")
                    icon_path = self.icon_cache / f"{value}.png"

                if await icon_path.exists():
                    return {"path": str(icon_path)}

                elif await app_path.exists():
                    await icon_path.parent.mkdir(parents=True, exist_ok=True)
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
                    icons = await asyncio.to_thread(favicon.get, value)
                    if not icons:
                        # Try root URL if the specific path returned no favicons
                        icons = await asyncio.to_thread(favicon.get, urlunsplit(value_url._replace(path="")))
                    if not icons:
                        raise ValueError(f"no favicon found for '{value}'")
                    icon = icons[0]
                    return (icon.url, f"favicon.{icon.format}")

                return await self._download_icon(
                    _get_favicon,
                    self.icon_cache / value_url.netloc / "favicon.*",
                )
            case _:
                raise ValueError(f"unknown icon type: '{icon_type}'")

        return None

    async def _download_icon(
        self,
        url: str | Callable[[], Awaitable[str]] | Callable[[], Awaitable[tuple[str, str]]],
        icon_path: AsyncPath,
    ) -> dict[str, str] | None:
        """Download icon from URL."""
        if icon_path.suffix == ".*":
            async for new_icon_path in icon_path.parent.glob(icon_path.name):
                icon_path = new_icon_path
                break

        if (await icon_path.exists()) and (await icon_path.stat()).st_size > 20:
            return {"path": str(icon_path)}

        if callable(url):
            try:
                match await url():
                    case str(url):
                        pass
                    case (str(url), str(filename)):
                        icon_path = icon_path.with_name(filename)
            except Exception:  # noqa: BLE001
                self.logger.debug(f"Failed to resolve icon URL for '{icon_path}'")
                return None

        try:
            await icon_path.parent.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Downloading icon from {url} to {icon_path}")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    timeout=2,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                    },
                )
                self.logger.debug(f"Response: {response.status_code}")
                response.raise_for_status()
                await icon_path.write_bytes(response.content)

            return {"path": str(icon_path)}
        except httpx.HTTPError:
            return None

    def queue_item(self, item_type: str, /, **kwargs: Unpack[AddItemArgs]) -> None:
        self._item_queue.put_nowait({
            "item_type": item_type,
            **kwargs,
        })

    async def add_item(  # noqa: PLR0912
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
            path_obj = await AsyncPath(path).expanduser()
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

    async def _add_source_file(self, src_file: PathLike[str], editor: Editor | Sequence[Editor]) -> None:
        match editor:
            case Editor() as editor:
                editors = [editor]
            case [*editors]:
                pass

        async with TaskGroup() as tg:
            for editor in editors:
                tg.create_task(
                    self.add_easy(
                        AsyncPath(src_file).name,
                        f"{editor.short_name} {src_file!s}",
                        editor.open_cmd(src_file),
                        **{k: v for k, v in {"appicon": editor.appicon}.items() if v is not None},
                    )
                )

    async def add_source_file(self, *srcs: PathLike[str], editor: Editor | Sequence[Editor] | None = None) -> None:
        if not srcs:
            raise ValueError("no source files provided")

        match editor:
            case None:
                editors = await Editors.editors()
            case [*editors]:
                pass
            case Editor() as editor:
                editors = [editor]

        for src_file in srcs:
            self._add_source_file(src_file, editors)

    def add_config_items(self) -> None:
        """Add configuration menu items."""
        cache_path = self.icon_cache / "*"
        self.add_exec(
            "clear cache",
            f'[[ -d "{self.icon_cache}/" ]] && rm "{cache_path}"',
        )

    def add_dev_workflow(self, editors: Sequence[str] = ("cursor", "vscode", "vscode-insiders", "xcode")) -> None:
        for editor in editors:
            self.add_exec(
                editor,
                f"open -a {editor}",
            )

    async def process_items(self) -> None:
        """Process items in the queue."""
        self._item_queue.shutdown()

        async with TaskGroup() as tg:
            try:
                while item := await self._item_queue.get():
                    tg.create_task(self.add_item(**cast(dict, item)))
            except asyncio.QueueShutDown:
                pass

    async def builder(
        self,
        *handlers: Callable[[Self], Coroutine[Any, Any, None]],
        add_config: bool = True,
        cache: bool = True,
    ) -> Self:
        if add_config:
            self.add_config_items()

        async with asyncio.TaskGroup() as tg:
            for handler in handlers:
                tg.create_task(handler(self))

        await self.process_items()

        if cache:
            await self.write_cache()

        return self

    def format_menu(self) -> str:
        """Generate the complete Alfred menu JSON."""
        menu = AlfredMenu(cache=MenuCache(seconds=self.cache_ttl), items=self.menu_items)
        return menu.model_dump_json(indent=2, exclude_none=True)

    def print_menu(self) -> None:
        """Print the complete Alfred menu JSON."""
        print(self.format_menu())

    @a.cache
    @classmethod
    async def cache_path(cls) -> AsyncPath:
        cache_tail = AsyncPath("alfred/maxcare-menu.json")
        if xdg_cache_home := os.environ.get("XDG_CACHE_HOME"):
            return AsyncPath(xdg_cache_home) / cache_tail
        elif await (cache_dir := HOME / ".cache").exists():
            return cache_dir / cache_tail
        else:
            return AsyncPath("/tmp/") / cache_tail

    @classmethod
    async def read_cache(cls) -> Self | None:
        cache_path = await cls.cache_path()
        if await cache_path.exists() and (data := await cache_path.read_text()):
            try:
                return cls.model_validate_json(data)

            except (json.JSONDecodeError, ValidationError):
                await cache_path.unlink()
        return None

    async def write_cache(self) -> None:
        path = await self.cache_path()
        await path.parent.mkdir(parents=True, exist_ok=True)
        await path.write_text(self.format_menu())

    def __str__(self) -> str:
        return self.format_menu()
