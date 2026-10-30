"""Stdlib-only cached Script Filter entry point."""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, TypeIs

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type Menu = dict[str, JsonValue]


def is_list(value: object) -> TypeIs[list[object]]:
    return isinstance(value, list)


def is_dict(value: object) -> TypeIs[dict[object, object]]:
    return isinstance(value, dict)


def is_json(value: object) -> TypeIs[JsonValue]:
    if is_list(value):
        return all(is_json(item) for item in value)
    if is_dict(value):
        return all(isinstance(key, str) and is_json(item) for key, item in value.items())
    return value is None or isinstance(value, (bool, int, float, str))


def cache_path(name: str | None = None) -> Path:
    """Resolve a cache shared with the full builder, isolated by bundle ID."""
    workflow_name = name or os.environ.get("alfred_workflow_bundleid") or "maxcare-menu"
    if workflow_name in {".", ".."} or re.fullmatch(r"[\w.-]+", workflow_name) is None:
        raise ValueError("Cache name must be a filename without directory separators")
    home = Path.home()
    xdg = os.environ.get("XDG_CACHE_HOME")
    root = Path(xdg) if (xdg is not None and xdg) else home / ".cache" if (home / ".cache").exists() else Path(tempfile.gettempdir())
    return root / "alfred" / f"{workflow_name}.json"


def read_cache(path: Path) -> Menu | None:
    """Reject malformed or incomplete menus so the caller can rebuild."""
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not is_json(value) or not isinstance(value, dict):
        return None
    items = value.get("items")
    if not isinstance(items, list):
        return None
    if not all(isinstance(item, dict) and isinstance(item.get("title"), str) for item in items):
        return None
    return value


def filter_menu(menu: Menu, query: str) -> Menu:
    """Match query tokens as case-insensitive subsequences of match or title."""
    items = menu.get("items")
    if not isinstance(items, list):
        raise TypeError("Menu items must be a list")
    tokens = query.casefold().split()
    filtered: list[JsonValue] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = item.get("match") or item.get("title")
        if not isinstance(text, str):
            continue
        if all(_subsequence(token, text.casefold()) for token in tokens):
            filtered.append(item)
    # Alfred's own cache must not reuse a query-filtered response for the next query.
    return {key: value for key, value in {**menu, "items": filtered}.items() if key != "cache"}


def _subsequence(needle: str, haystack: str) -> bool:
    characters = iter(haystack)
    return all(character in characters for character in needle)


def write_cache(path: Path, menu: Menu) -> None:
    """Replace a complete, valid menu atomically."""
    payload = json.dumps(menu, allow_nan=False)
    items = menu.get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) and isinstance(item.get("title"), str) for item in items):
        raise ValueError("Menu items must be objects with string titles")
    atomic_write(path, payload)


def atomic_write(path: Path, payload: str) -> None:
    """Replace a UTF-8 payload atomically without sharing temporary filenames."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(payload)
            stream.close()
            Path(temporary).replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def refresh(
    script: Path,
    path: Path,
    *,
    args: Sequence[str] = ("--no-cache",),
    interval: timedelta = timedelta(minutes=1),
    env: Mapping[str, str] | None = None,
) -> bool:
    """Launch at most one detached builder per interval, including failed attempts."""
    return spawn_refresh([sys.executable, str(script), *args], path.with_suffix(path.suffix + ".refresh.pid"), interval=interval, env=env)


def spawn_refresh(
    command: Sequence[str],
    marker: Path,
    *,
    interval: timedelta = timedelta(minutes=1),
    env: Mapping[str, str] | None = None,
) -> bool:
    """Throttle detached processes using a locked marker, even after a failed spawn."""
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        with marker.open("a+", encoding="utf-8") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            stat = os.fstat(stream.fileno())
            age = datetime.now(UTC) - datetime.fromtimestamp(stat.st_mtime, UTC)
            if stat.st_size > 0 and age < interval:
                return False
            stream.seek(0)
            stream.truncate()
            stream.write(str(os.getpid()))
            stream.flush()
            try:
                child = subprocess.Popen(
                    list(command),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env={**os.environ, **(env or {}), "PYDANTIC_DISABLE_PLUGINS": "__all__"},
                )
            except OSError:
                return False
            stream.seek(0)
            stream.truncate()
            stream.write(str(child.pid))
    except OSError:
        return False
    return True


def serve(query: str = "", *, name: str | None = None, script: Path | None = None) -> bool:
    """Print a cached menu; return False when the full builder must run."""
    path = cache_path(name)
    menu = read_cache(path)
    if menu is None:
        return False
    if script is not None:
        refresh(script, path)
    print(json.dumps(filter_menu(menu, query)))
    return True
