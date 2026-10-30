from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import sys
from asyncio import TaskGroup, subprocess
from fnmatch import fnmatch
from functools import cached_property
from html.parser import HTMLParser
from shlex import quote
from typing import TYPE_CHECKING, Self, TypedDict, Unpack, override
from urllib.parse import urljoin, urlsplit, urlunsplit

import asyncstdlib as a
import httpx
from anyio import Path as AsyncPath
from pydantic import Field, RootModel, ValidationError
from we_love.alfred.editor import Editor, Editors
from we_love.alfred.fast import cache_path as fast_cache_path
from we_love.alfred.model import AlfredBaseModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Sequence
    from os import PathLike


__lazy_modules__ = ("httpx", "we_love.alfred.editor")

HOME = AsyncPath(os.environ["HOME"])


async def _glob(path: AsyncPath, pattern: str, case_sensitive: bool = False, recurse_symlinks: bool = False) -> AsyncIterator[AsyncPath]:
    if case_sensitive:
        async for entry in path.glob(pattern, recurse_symlinks=recurse_symlinks):
            yield entry
    else:
        async for entry in path.iterdir():
            if fnmatch(entry.name.casefold(), pattern.casefold()):
                yield entry


class FaviconLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        relation = attributes.get("rel") or ""
        href = attributes.get("href")
        if tag == "link" and "icon" in relation.lower() and href is not None and href:
            self.links.append(href)


def _just_netloc(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


class AwsAccount(AlfredBaseModel):
    id: str
    name: str
    services: list[str] | tuple[str, ...] = ()
    role_names: list[str] | tuple[str, ...] = ("AdministratorAccess",)

    @classmethod
    def model_validate_list(cls, v: object) -> list[Self]:
        adapter = RootModel[list[object]]
        match v:
            case "null" | None:
                return []
            case str() if v.startswith("{"):
                return [cls.model_validate_json(v)]
            case str():
                return [cls.model_validate(item) for item in adapter.model_validate_json(v).root]
            case _:
                return [cls.model_validate(item) for item in adapter.model_validate(v).root]


def env[R](key: str, default: R, converter: Callable[[str | R], R]) -> Callable[[], R]:
    def _() -> R:
        return converter(os.environ.get(key, default))

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

    @override
    def model_post_init(self, context: object) -> None:
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
    items: list[MenuItem] = Field(default_factory=list[MenuItem])


class AddItemArgs(TypedDict, total=False):
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


class QueuedItem(AddItemArgs):
    item_type: str


class MenuItemOverrides(TypedDict, total=False):
    alt: str | dict[str, str] | None
    cmd: str | dict[str, str] | None


class AlfredWorkflow(AlfredBaseModel, ignored_types=(AsyncPath,), arbitrary_types_allowed=True):
    """Alfred workflow generator for MaxCare."""

    cache_name: str | None = None
    cache_ttl: int = 3600
    home: AsyncPath = HOME
    xdg_cache_home: AsyncPath = HOME / ".cache"
    icon_cache: AsyncPath = HOME / ".cache" / "alfred-icons"
    menu_items: list[MenuItem] = Field(default_factory=list[MenuItem])

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
    def _item_queue(self) -> asyncio.Queue[QueuedItem]:
        return asyncio.Queue()

    @a.cached_property
    async def _has_magick_bin(self) -> bool:
        proc = await subprocess.create_subprocess_exec("which", "magick", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await proc.wait()
        return proc.returncode == 0

    async def sfsymbol(self, symbol: str) -> str | None:
        """Generate SF Pro icon files for given symbol."""
        icon_stem = self.xdg_cache_home / f"font-icons/sf-pro-{symbol}"
        dark_path = icon_stem.with_suffix(".png").with_name(f"{icon_stem.stem}-dark.png")
        light_path = icon_stem.with_suffix(".png").with_name(f"{icon_stem.stem}-light.png")

        if not await dark_path.exists():
            if not await self._has_magick_bin:
                return None

            await dark_path.parent.mkdir(parents=True, exist_ok=True)

            async def render_icon(mode: str, path: AsyncPath) -> None:
                process = await subprocess.create_subprocess_exec(
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
                await process.wait()

            async with TaskGroup() as tg:
                for mode, path in [("black", dark_path), ("white", light_path)]:
                    tg.create_task(render_icon(mode, path))

        return str(dark_path) if (await dark_path.exists()) else None

    def generate_uid(self, title: str, subtitle: str, arg: str) -> str:
        """Generate unique ID for menu item."""
        content = f"{title} {subtitle} {arg}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def process_icon(
        self,
        icon_type: str,
        value: str,
        existing_icon: dict[str, str] | None = None,
    ) -> dict[str, str] | None:
        """Process different icon types and return icon dict."""
        if (existing_icon is not None and existing_icon) and icon_type in {"appicon", "urlicon", "clearbiticon"}:
            return existing_icon

        match icon_type:
            case "icon" if "*" in value:
                async for icon_path in _glob(self.icon_cache, value, case_sensitive=False):
                    return {"path": str(await icon_path.absolute())}
                return None

            case "icon":
                return {"path": value}

            case "glyph":
                if value in self.glyphs:
                    icon_path = await self.sfsymbol(self.glyphs[value])
                    return {"path": icon_path} if (icon_path is not None and icon_path) else None
                if await AsyncPath(value).exists():
                    return {"path": value}
                print(
                    f"glyph: '{value}' does not exist",
                    file=sys.stderr,
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

                if await app_path.exists():
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
                    await proc.wait()
                    if proc.returncode == 0:
                        return {"path": str(icon_path)}
                    return None

            case "clearbiticon":
                domain = value.rsplit("://", maxsplit=1)[-1].split("/", maxsplit=1)[0].split(":", maxsplit=1)[0]
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
                    async with httpx.AsyncClient(follow_redirects=True, timeout=2) as client:
                        for page_url in (value, _just_netloc(value)):
                            response = await client.get(page_url)
                            response.raise_for_status()
                            links = FaviconLinks()
                            links.feed(response.text)
                            if links.links:
                                icon_url = urljoin(str(response.url), links.links[0])
                                suffix = AsyncPath(urlsplit(icon_url).path).suffix or ".ico"
                                return icon_url, f"favicon{suffix}"
                    return urljoin(value, "/favicon.ico"), "favicon.ico"

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

        if not isinstance(url, str):
            try:
                resolved = await url()
                match resolved:
                    case str() as resolved_url:
                        url = resolved_url
                    case (str(resolved_url), str(filename)):
                        url = resolved_url
                        icon_path = icon_path.with_name(filename)
            except Exception:
                self.logger.debug("Failed to resolve icon URL for '%s'", icon_path)
                return None

        try:
            await icon_path.parent.mkdir(parents=True, exist_ok=True)
            self.logger.debug("Downloading icon from %s to %s", url, icon_path)
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    timeout=2,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                    },
                )
                self.logger.debug("Response: %s", response.status_code)
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

    async def add_item(
        self,
        item_type: str,
        *,
        title: str = "",
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
        **kwargs: Unpack[MenuItemOverrides],
    ) -> None:
        """Add a menu item based on type using keyword arguments."""
        item_args = {"title": title}
        icon_dict = None

        match item_type:
            case "easy":
                if not (subtitle is not None and subtitle) or not (arg is not None and arg):
                    raise ValueError("easy items require 'title', 'subtitle', and 'arg'")
                item_args.update({"subtitle": subtitle, "arg": arg})

            case "url":
                if not (url is not None and url):
                    raise ValueError("url items require 'title' and 'url'")
                item_args.update({
                    "subtitle": subtitle or f"open {title} in browser ({url})",
                    "arg": f"open {url}",
                })
                # Default to favicon if no icon specified
                if not (
                    (icon is not None and icon)
                    or (glyph is not None and glyph)
                    or (appicon is not None and appicon)
                    or (clearbiticon is not None and clearbiticon)
                    or (urlicon is not None and urlicon)
                    or (workflowicon is not None and workflowicon)
                    or (filetype is not None and filetype)
                    or (fileicon is not None and fileicon)
                    or (utiicon is not None and utiicon)
                ):
                    favicon = url

            case "exec":
                if not (command is not None and command):
                    raise ValueError("exec items require 'title' and 'command'")
                item_args.update({"subtitle": subtitle or command, "arg": f"zsh://{command}"})
                # Default to terminal glyph if no glyph specified
                if not (
                    (icon is not None and icon)
                    or (glyph is not None and glyph)
                    or (appicon is not None and appicon)
                    or (clearbiticon is not None and clearbiticon)
                    or (urlicon is not None and urlicon)
                    or (workflowicon is not None and workflowicon)
                    or (filetype is not None and filetype)
                    or (fileicon is not None and fileicon)
                    or (utiicon is not None and utiicon)
                ):
                    glyph = "terminal"

            case _:
                raise ValueError(f"unknown item type: '{item_type}'")

        # Handle path argument
        if path is not None and path:
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
            if icon_value is not None and icon_value:
                icon_dict = await self.process_icon(icon_type, icon_value, icon_dict)
                break

        # Set additional overrides
        if uid is not None and uid:
            item_args["uid"] = uid
        if match is not None and match:
            item_args["match"] = match
        if autocomplete is not None and autocomplete:
            item_args["autocomplete"] = autocomplete

        # Add any additional kwargs

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
        menu_item = MenuItem.model_validate({**item_args, **kwargs, "icon": icon_dict})

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
        editors = [editor] if isinstance(editor, Editor) else editor
        for current_editor in editors:
            options: AddItemArgs = {"title": AsyncPath(src_file).name}
            if current_editor.appicon is not None:
                options["appicon"] = current_editor.appicon
            self.add_easy(
                AsyncPath(src_file).name,
                f"{current_editor.short_name} {src_file!s}",
                current_editor.open_cmd(src_file),
                **options,
            )

    async def add_source_file(self, *srcs: PathLike[str], editor: Editor | Sequence[Editor] | None = None) -> None:
        if not srcs:
            raise ValueError("no source files provided")
        editors = await Editors.editors() if editor is None else [editor] if isinstance(editor, Editor) else editor
        for src_file in srcs:
            await self._add_source_file(src_file, editors)

    def add_config_items(self) -> None:
        """Add configuration menu items."""
        menu_cache = fast_cache_path(self.cache_name)
        pidfile = quote(str(menu_cache) + ".refresh.pid")
        self.add_exec(
            "clear cache",
            f'if [[ -f {pidfile} ]]; then kill "$(cat {pidfile})" 2>/dev/null; fi; '
            f"rm -f {pidfile} {quote(str(menu_cache))}; "
            f"if [[ -d {quote(str(self.icon_cache))} ]]; then find {quote(str(self.icon_cache))} -type f -delete; fi",
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
                while True:
                    item = await self._item_queue.get()
                    tg.create_task(self.add_item(**item))
            except asyncio.QueueShutDown:
                pass

    async def builder(
        self,
        *handlers: Callable[[Self], Coroutine[object, object, None]],
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

    @classmethod
    async def cache_path(cls, name: str | None = None) -> AsyncPath:
        return AsyncPath(fast_cache_path(name))

    @classmethod
    async def read_cache(cls, name: str | None = None) -> Self | None:
        cache_path = await cls.cache_path(name)
        if await cache_path.exists() and (data := await cache_path.read_text()):
            try:
                menu = AlfredMenu.model_validate_json(data)
                return cls(cache_name=name, cache_ttl=menu.cache.seconds, menu_items=menu.items)

            except ValidationError:
                await cache_path.unlink()
        return None

    async def write_cache(self) -> None:
        path = AsyncPath(fast_cache_path(self.cache_name))
        await path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            await temporary.write_text(self.format_menu())
            await temporary.replace(path)
        finally:
            await temporary.unlink(missing_ok=True)

    @override
    def __str__(self) -> str:
        return self.format_menu()
