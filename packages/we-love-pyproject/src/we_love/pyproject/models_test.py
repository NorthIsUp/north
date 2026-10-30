"""Schema imports and TOML round trips exercise the Pydantic v2 migration."""

from __future__ import annotations

import importlib
import tomllib
from typing import TYPE_CHECKING

import pytest
from we_love.pyproject.models import PyProjectToml, UvSource, UvWorkspacePyProjectToml

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    "module", ["_hatch", "_partial-black", "_partial-mypy", "_partial-pytest", "_partial-setuptools", "_pdm", "_poetry", "_ruff"]
)
def test_generated_schema_imports(module: str) -> None:
    assert importlib.import_module(f"we_love.pyproject.{module}") is not None


def test_toml_roundtrip_preserves_unmodeled_tool_settings(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    original = {"project": {"name": "example", "version": "1.0"}, "tool": {"ty": {"rules": {"all": "error"}}}}
    path.write_text('[project]\nname = "example"\nversion = "1.0"\n[tool.ty.rules]\nall = "error"\n', encoding="utf-8")
    model = PyProjectToml.from_file(path)
    model.write(path)
    assert tomllib.loads(path.read_text(encoding="utf-8")) == original


def test_workspace_members_and_inline_sources(tmp_path: Path) -> None:
    model = UvWorkspacePyProjectToml()
    model.add_workspace_member("packages/example")
    model.add_workspace_source("example", UvSource(workspace=True))
    path = tmp_path / "pyproject.toml"
    model.write(path)
    loaded = UvWorkspacePyProjectToml.from_file(path)
    assert loaded.get_workspace_members() == ["packages/example"]
    assert loaded.get_workspace_sources()["example"].workspace
    assert "example = {workspace = true}" in path.read_text(encoding="utf-8")
