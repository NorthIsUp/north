#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
# "rich",
#     "tomlkit>=0.13.2",
# ]
# ///


import difflib
from pathlib import Path
from typing import Sequence

import tomlkit


class Config:
    PYTHON_VERSION = "3.13"
    BUILD_SYSTEM_BACKEND = "uv"
    BUILD_SYSTEM_REQUIRES = ("uv>=0.7,<1",)


def new_package(name: str):
    """_summary_

    Args:
        name (str): _description_
    """
    config = {
        "package": {
            "name": f"north-{name}",
            "version": "0.1.0",
            "description": "",
            "readme": "README.md",
            "requires-python": ">={python_version}",
        },
        "build-system": {
            "requires": ["uv>=0.5.15,<0.6"],
            "build-backend": "uv",
        },
        "tool.setuptools.packages.find": {
            "where": ["src/"],
            "include": ["north.{name}"],
        },
    }

    print(tomlkit.dumps(config))


def update_project(
    pyproject_file: Path,
    dry_run: bool = True,
    python_version: str = f">={Config.PYTHON_VERSION}",
    build_system_backend: str = Config.BUILD_SYSTEM_BACKEND,
    build_system_requires: Sequence[str] = Config.BUILD_SYSTEM_REQUIRES,
):
    pyproject = tomlkit.parse(pyproject_file.read_text())

    pyproject["project"]["requires-python"] = python_version
    pyproject["build-system"]["build-backend"] = build_system_backend
    pyproject["build-system"]["requires"] = build_system_requires

    output = tomlkit.dumps(pyproject).splitlines()
    diff = difflib.unified_diff(
        pyproject_file.read_text().splitlines(),
        output,
    )
    print("\n".join(diff))
    if not dry_run:
        pyproject_file.write_text(output)


def update_projects(dry_run: bool = True):
    project_files = (Path(__file__).parent / "src").glob("*/pyproject.toml")
    for pyproject_file in project_files:
        update_project(pyproject_file, dry_run=dry_run)


def main():
    print("Hello from north!")
    new_package("mypkg")


if __name__ == "__main__":
    main()
