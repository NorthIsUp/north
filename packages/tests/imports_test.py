"""Import every local package in a fresh process."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from pydantic import BaseModel


class Project(BaseModel):
    name: str


class PackageConfig(BaseModel):
    project: Project


def discover_packages() -> list[str]:
    packages_dir = Path(__file__).parent.parent
    return sorted(
        PackageConfig.model_validate(tomllib.loads(path.read_text())).project.name for path in packages_dir.glob("we-love-*/pyproject.toml")
    )


@pytest.mark.parametrize("package", discover_packages())
def test_package_imports(package: str) -> None:
    module = "we_love." + package.removeprefix("we-love-").replace("-", "_")
    result = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_package_discovery() -> None:
    assert "we-love-alfred" in discover_packages()
    assert "we-love-pyproject" in discover_packages()
