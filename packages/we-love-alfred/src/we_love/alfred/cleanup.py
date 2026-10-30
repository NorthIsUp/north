"""Resolve workflow-owned cache paths before dispatching commands through zsh."""

from __future__ import annotations

from pathlib import Path
from shlex import quote
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel

from .fast import cache_filename

if TYPE_CHECKING:
    from collections.abc import Mapping


class CacheCleanup(BaseModel):
    menu_cache: Path
    icon_cache: Path
    workflow_cache: Path | None = None
    workflow_data: Path | None = None

    @classmethod
    def from_environment(cls, menu_cache: Path, icon_cache: Path, home: Path, environment: Mapping[str, str]) -> Self:
        cache_root = home / "Library/Caches/com.runningwithcrayons.Alfred/Workflow Data"
        data_root = home / "Library/Application Support/Alfred/Workflow Data"
        bundle = environment.get("alfred_workflow_bundleid")
        bundle = cache_filename(bundle).removesuffix(".json") if bundle is not None and bundle else None
        blocked = {home, *home.parents, cache_root, data_root}

        def workflow_path(key: str, root: Path) -> Path | None:
            raw = environment.get(key)
            path = Path(raw) if raw is not None and raw else root / bundle if bundle is not None else None
            if path is None or not path.is_absolute() or path in blocked or ".." in path.parts:
                return None
            return path

        return cls(
            menu_cache=menu_cache,
            icon_cache=icon_cache,
            workflow_cache=workflow_path("alfred_workflow_cache", cache_root),
            workflow_data=workflow_path("alfred_workflow_data", data_root),
        )

    def command(self) -> str:
        marker = quote(str(self.menu_cache) + ".refresh.pid")
        commands = [
            (
                f"if [ -f {marker} ]; then refresh_pid=$(cat {marker}); "
                'case "$refresh_pid" in ""|*[!0-9]*) ;; *) '
                'if [ "$refresh_pid" -gt 1 ]; then kill "$refresh_pid" 2>/dev/null; fi ;; esac; fi'
            ),
            f"rm -f {marker} {quote(str(self.menu_cache))}",
            self._delete_files(self.icon_cache),
        ]
        if self.workflow_cache is not None:
            path = quote(str(self.workflow_cache))
            commands.append(f"if [ -d {path} ]; then find {path} -mindepth 1 -delete; fi")
        if self.workflow_data is not None:
            commands.append(self._delete_files(self.workflow_data, "*.cache"))
        return "; ".join(commands)

    @staticmethod
    def _delete_files(path: Path, pattern: str | None = None) -> str:
        directory = quote(str(path))
        selection = f" -name {quote(pattern)}" if pattern is not None else ""
        return f"if [ -d {directory} ]; then find {directory} -type f{selection} -delete; fi"
