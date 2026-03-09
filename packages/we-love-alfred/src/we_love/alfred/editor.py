from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar

import asyncstdlib as a
from anyio import Path as AsyncPath
from pydantic import PrivateAttr
from we_love.alfred.model import AlfredBaseModel

if TYPE_CHECKING:
    from collections.abc import Sequence
    from os import PathLike


class Editor(AlfredBaseModel, arbitrary_types_allowed=True):
    name: str
    short_name: str
    path: AsyncPath
    appicon: str | None = None
    _exists_cache: bool | None = PrivateAttr(default=None)

    async def exists(self) -> bool:
        if self._exists_cache is None:
            self._exists_cache = await self.path.exists()
        return self._exists_cache  # type: ignore[return-value]

    def open_cmd(self, path: PathLike[str]) -> str:
        return f"open -a '{self.name}' {path!s}"


class Editors:
    _registry: ClassVar[dict[str, Editor]] = {}
    _discovery_has_run: ClassVar[bool] = False
    _discovery_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @classmethod
    async def editors(
        cls,
        priority: Sequence[str] = (
            "cursor",
            "code-insiders",
            "code",
            "xcode",
            "textedit",
        ),
        num: int | None = None,
    ) -> Sequence[Editor]:
        if not cls._discovery_has_run:
            await cls.discover_editors()

        return sorted(cls._registry.values(), key=lambda x: priority.index(x.short_name), reverse=True)[:num]

    @a.cache
    @classmethod
    async def discover_editors(cls) -> None:
        async with cls._discovery_lock:
            if cls._discovery_has_run:
                return

            cls._discovery_has_run = True

            async def _register_editor(editor: Editor) -> None:
                if await editor.exists():
                    cls._registry[editor.short_name] = editor

            async with asyncio.TaskGroup() as tg:
                for editor in [
                    Editor(
                        name="Cursor",
                        short_name="cursor",
                        path=AsyncPath("/Applications/Cursor.app"),
                        appicon="Cursor",
                    ),
                    Editor(
                        name="Visual Studio Code - Insiders",
                        short_name="code-insiders",
                        path=AsyncPath("/Applications/Visual Studio Code - Insiders.app"),
                        appicon="/Applications/Visual Studio Code - Insiders.app/Contents/Resources/Code - Insiders.icns",
                    ),
                    Editor(
                        name="Visual Studio Code",
                        short_name="code",
                        path=AsyncPath("/Applications/Visual Studio Code.app"),
                        appicon="/Applications/Visual Studio Code.app/Contents/Resources/Code.icns",
                    ),
                    Editor(
                        name="Xcode",
                        short_name="xcode",
                        path=AsyncPath("/Applications/Xcode.app"),
                        appicon="/Applications/Xcode.app/Contents/Resources/Xcode.icns",
                    ),
                    Editor(
                        name="TextEdit",
                        short_name="textedit",
                        path=AsyncPath("/Applications/TextEdit.app"),
                        appicon="/Applications/TextEdit.app/Contents/Resources/TextEdit.icns",
                    ),
                ]:
                    tg.create_task(_register_editor(editor))
