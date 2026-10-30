from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from anyio import Path as AsyncPath
from we_love.alfred import workflow as workflow_module
from we_love.alfred.editor import Editor
from we_love.alfred.fast import cache_path, filter_menu, read_cache, refresh, write_cache
from we_love.alfred.workflow import AlfredWorkflow, MenuItem

if TYPE_CHECKING:
    from pathlib import Path


def test_fast_import_is_stdlib_only() -> None:
    source = "import sys; import we_love.alfred.fast; assert not {'pydantic', 'httpx', 'favicon', 'requests', 'bs4'} & sys.modules.keys()"
    result = subprocess.run([sys.executable, "-c", source], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_cache_names_are_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("alfred_workflow_bundleid", "com.example.first")
    assert cache_path() == tmp_path / "alfred/com.example.first.json"
    assert cache_path("second") == tmp_path / "alfred/second.json"
    with pytest.raises(ValueError, match="Cache name"):
        cache_path("../escape")


def test_cache_roundtrip_filters_match_and_title(tmp_path: Path) -> None:
    path = tmp_path / "menu.json"
    write_cache(
        path,
        {"cache": {"seconds": 3600}, "items": [{"title": "Production deploy", "match": "production deploy"}, {"title": "Open dashboard"}]},
    )
    menu = read_cache(path)
    assert menu is not None
    assert filter_menu(menu, "prd dpl") == {"items": [{"title": "Production deploy", "match": "production deploy"}]}
    assert filter_menu(menu, "dsbrd") == {"items": [{"title": "Open dashboard"}]}
    path.write_text('{"items": [')
    assert read_cache(path) is None


def test_refresh_preserves_argv_and_throttles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, str], bool]] = []

    class Child:
        pid: int = 12345

    def spawn(command: list[str], *, stdin: int, stdout: int, stderr: int, start_new_session: bool, env: dict[str, str]) -> Child:
        calls.append((command, env, start_new_session))
        return Child()

    monkeypatch.setattr(subprocess, "Popen", spawn)
    script = tmp_path / "full builder.py"
    path = tmp_path / "cache.json"
    assert refresh(script, path)
    assert not refresh(script, path)
    assert calls[0][0] == [sys.executable, str(script), "--no-cache"]
    assert calls[0][1]["PYDANTIC_DISABLE_PLUGINS"] == "__all__"
    assert calls[0][2]
    assert path.with_suffix(".json.refresh.pid").read_text() == "12345"
    os.utime(path.with_suffix(".json.refresh.pid"), (0, 0))
    assert refresh(script, path, interval=timedelta(seconds=60))
    assert len(calls) == 2


def test_failed_refresh_is_throttled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def spawn(*args: object, **kwargs: object) -> None:
        raise OSError("unavailable")

    monkeypatch.setattr(subprocess, "Popen", spawn)
    path = tmp_path / "cache.json"
    assert not refresh(tmp_path / "full.py", path)
    assert not refresh(tmp_path / "full.py", path)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_builder_cache_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    workflow = AlfredWorkflow(cache_name="example", menu_items=[MenuItem(title="Ready")])
    await workflow.write_cache()
    loaded = await AlfredWorkflow.read_cache("example")
    assert loaded is not None
    assert loaded.menu_items == workflow.menu_items
    assert json.loads(cache_path("example").read_text())["items"][0]["title"] == "Ready"


@pytest.mark.anyio
async def test_source_files_queue_editor_actions(tmp_path: Path) -> None:

    editor = Editor(name="Example", short_name="example", path=AsyncPath(tmp_path))
    workflow = AlfredWorkflow()
    await workflow.add_source_file(tmp_path / "config.toml", editor=editor)
    await workflow.process_items()
    assert workflow.menu_items[0].title == "config.toml"


@pytest.mark.anyio
@pytest.mark.parametrize("with_home_cache", [False, True])
async def test_fast_and_full_cache_fallbacks_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_home_cache: bool) -> None:
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(workflow_module, "HOME", AsyncPath(tmp_path))
    if with_home_cache:
        await (AsyncPath(tmp_path) / ".cache").mkdir()
    assert str(await AlfredWorkflow.cache_path("example")) == str(cache_path("example"))
