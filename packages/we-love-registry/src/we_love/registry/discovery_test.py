"""Discovery imports exactly the requested subtree and remains retryable."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from . import Registry, autodiscover

if TYPE_CHECKING:
    from pathlib import Path
import importlib
import sys


@pytest.mark.parametrize("recursive", [False, True])
def test_discovery_respects_recursion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recursive: bool) -> None:
    """Nonrecursive discovery avoids nested modules; recursive discovery imports each once."""
    name = f"audit_discovery_{recursive}"
    package = tmp_path / name
    nested = package / "nested"
    nested.mkdir(parents=True)
    for path in (package / "__init__.py", package / "entry.py", nested / "__init__.py", nested / "child.py"):
        path.write_text("")
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    importlib.invalidate_caches()
    names = [module.__name__ for module in autodiscover(name, recursive=recursive)]
    expected = {f"{name}.entry", f"{name}.nested"}
    if recursive:
        expected.add(f"{name}.nested.child")
    assert set(names) == expected
    assert len(names) == len(expected)


def test_failed_discovery_is_retryable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An import failure must not mark a registry as successfully discovered."""
    package = tmp_path / "audit_broken_discovery"
    package.mkdir()
    (package / "__init__.py").write_text("")
    broken = package / "entry.py"
    broken.write_text("raise RuntimeError('broken import')")
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    importlib.invalidate_caches()
    registry = Registry(autodiscovery_module=package.name)
    with pytest.raises(RuntimeError, match="broken import"):
        registry.all()
    assert not registry.autodiscovery_run
    broken.write_text("")
    assert registry.all() == []
    assert registry.autodiscovery_run
