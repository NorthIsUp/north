from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from we_love.alfred.cleanup import CacheCleanup

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("explicit_paths", [False, True])
def test_cleanup_preserves_workflow_data_and_sibling_caches(tmp_path: Path, explicit_paths: bool) -> None:
    environment = {"alfred_workflow_bundleid": "com.example.workflow"}
    if explicit_paths:
        environment.update(
            alfred_workflow_cache=str(tmp_path / "workflow's cache"),
            alfred_workflow_data=str(tmp_path / "workflow's data"),
        )
    cleanup = CacheCleanup.from_environment(tmp_path / "menu.json", tmp_path / "icons", tmp_path, environment)
    assert cleanup.workflow_cache is not None
    assert cleanup.workflow_data is not None
    cleanup.workflow_cache.mkdir(parents=True)
    cleanup.workflow_data.mkdir(parents=True)
    cleanup.icon_cache.mkdir()
    cached = cleanup.workflow_cache / "old.json"
    cached.write_text("cache", encoding="utf-8")
    disposable = cleanup.workflow_data / "state.cache"
    disposable.write_text("cache", encoding="utf-8")
    retained = cleanup.workflow_data / "settings.json"
    retained.write_text("user data", encoding="utf-8")
    sibling = cleanup.workflow_cache.parent / "another-workflow" / "cache.json"
    sibling.parent.mkdir()
    sibling.write_text("other workflow", encoding="utf-8")
    cleanup.menu_cache.write_text("menu", encoding="utf-8")
    marker = cleanup.menu_cache.with_suffix(".json.refresh.pid")
    marker.write_text("pending", encoding="utf-8")
    icon = cleanup.icon_cache / "icon.png"
    icon.write_bytes(b"icon")

    script = 'kill() { printf "KILLED:%s\\n" "$1"; }; ' + cleanup.command()
    result = subprocess.run(["/bin/sh", "-c", script], env={}, capture_output=True, text=True, check=True)
    assert not result.stdout
    assert not cached.exists()
    assert not disposable.exists()
    assert not cleanup.menu_cache.exists()
    assert not marker.exists()
    assert not icon.exists()
    assert retained.read_text(encoding="utf-8") == "user data"
    assert sibling.read_text(encoding="utf-8") == "other workflow"


def test_missing_bundle_does_not_select_all_workflows(tmp_path: Path) -> None:
    cleanup = CacheCleanup.from_environment(tmp_path / "menu.json", tmp_path / "icons", tmp_path, {})
    assert cleanup.workflow_cache is None
    assert cleanup.workflow_data is None


@pytest.mark.parametrize("relative", [".", "..", "Library/Caches"])
def test_relative_workflow_paths_are_ignored(tmp_path: Path, relative: str) -> None:
    cleanup = CacheCleanup.from_environment(
        tmp_path / "menu.json",
        tmp_path / "icons",
        tmp_path,
        {"alfred_workflow_cache": relative, "alfred_workflow_data": relative},
    )
    assert cleanup.workflow_cache is None
    assert cleanup.workflow_data is None


def test_workflow_roots_are_never_selected_for_cleanup(tmp_path: Path) -> None:
    cleanup = CacheCleanup.from_environment(
        tmp_path / "menu.json",
        tmp_path / "icons",
        tmp_path,
        {
            "alfred_workflow_cache": str(tmp_path / "Library/Caches/com.runningwithcrayons.Alfred/Workflow Data"),
            "alfred_workflow_data": str(tmp_path / "Library/Application Support/Alfred/Workflow Data"),
        },
    )
    assert cleanup.workflow_cache is None
    assert cleanup.workflow_data is None
