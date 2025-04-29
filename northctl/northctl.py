#!/usr/bin/env python3

import argparse
import difflib
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import indent
from typing import Any, Mapping

import tomlkit
from structlog import get_logger

logger = get_logger(__name__)


project_root = Path(__file__).parent
while not (project_root / ".git").is_dir():
    project_root = project_root.parent

packages_root = project_root / "src"


class Config:
    PYTHON_VERSION = "3.13"
    UV_MIN_VERSION = "0.6"
    UV_MAX_VERSION = "1"
    BUILD_SYSTEM_BACKEND = "hatchling.build"
    BUILD_SYSTEM_REQUIRES = ("hatchling",)
    VERSION = "0.1.0"

    @classmethod
    def base_config(cls, name: str) -> dict[str, Any]:
        return {
            "project": {
                "name": f"north-{name}",
                "version": cls.VERSION,
                "description": "",
                "readme": "README.md",
                "requires-python": f">={cls.PYTHON_VERSION}",
            },
            "build-system": {
                "requires": ["hatchling>=1.11,<2"],
                "build-backend": "hatchling.build",
            },
            "tool": {
                "setuptools": {
                    "packages": {
                        "find": {
                            "where": [f"src/north-{name}"],
                            "include": [f"north.{name}"],
                        },
                    },
                },
                "hatch": {
                    "build": {
                        "targets": {
                            "sdist": {"include": [f"src/north-{name}/{name}"]},
                            "wheel": {"packages": [f"src/north-{name}/{name}"]},
                        },
                    },
                },
            },
        }


def parse_args():
    package_choices = {p.name[6:] for p in packages_root.glob("north-*")}
    package_choices_opt = sorted(package_choices)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "packages",
        nargs="*",
        action="extend",
        help="The package to update",
        choices=package_choices_opt.copy(),
    )
    parser.add_argument(
        "--all",
        dest="packages",
        action="store_const",
        const=package_choices_opt.copy(),
        help="Update all packages",
    )
    parser.add_argument(
        "--create",
        type=str,
        help="Create a new package",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update packages",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run, don't write to files",
    )
    args = parser.parse_args()
    if args.create:
        args.packages = [args.create]

    logger.debug(f"args: {args}")
    if not args.packages:
        parser.error("No packages specified, use --all to update all packages")

    logger.debug(f"args: {args}")
    return args


@dataclass
class Project:
    name: str
    pyproject_toml: Path = field(init=False)
    dry_run: bool = False
    config: Config = Config()

    def __post_init__(self) -> None:
        self.pyproject_toml = packages_root / f"north-{self.name}" / "pyproject.toml"

    @property
    def pyproject_toml_text(self) -> str:
        return self.pyproject_toml.read_text()

    @property
    def pyproject_toml_dict(self) -> tomlkit.TOMLDocument:
        return tomlkit.parse(self.pyproject_toml_text)

    @property
    def pyproject_toml_relpath(self) -> Path:
        return self.pyproject_toml.relative_to(Path.home())

    def dump(self, dict: Mapping[str, Any]) -> str:
        return tomlkit.dumps(dict, sort_keys=True)

    def write_pyproject_toml(self, dict: dict[str, Any]):
        self.pyproject_toml.write_text(self.dump(dict))

    def create(self) -> None:
        self.create_package()
        self.write_pyproject_toml(self.config.base_config(self.name))
        self.update()

    def create_package(self) -> None:
        proj = packages_root / f"north-{self.name}"
        pkg = proj / "north" / self.name
        pkg.mkdir(parents=True, exist_ok=True)

        for file in ("__init__.py",):
            (pkg / file).touch()

        for file in ("README.md", "pyproject.toml"):
            (proj / file).touch()

    def update(self) -> None:
        (self.pyproject_toml.parent / "README.md").touch()
        if not self.pyproject_toml.exists():
            logger.error(f"Package '{self.name}' does not exist, creating...")
            self.create()

        pyproject = tomlkit.parse(self.pyproject_toml.read_text())
        project = pyproject.setdefault("project", {})

        project["requires-python"] = f">={self.config.PYTHON_VERSION}"
        # pyproject["build-system"]["build-backend"] = self.config.BUILD_SYSTEM_BACKEND
        # pyproject["build-system"]["requires"] = self.config.BUILD_SYSTEM_REQUIRES

        # output = self.dump(pyproject).splitlines()
        # diff = difflib.unified_diff(
        #     self.pyproject_toml_text.strip().splitlines(),
        #     output,
        #     fromfile=f"~/{self.pyproject_toml_relpath}",
        #     tofile=f"~/{self.pyproject_toml_relpath}",
        # )
        if diff := colordiff(self.pyproject_toml_text, self.dump(pyproject)):
            logger.info(f"Diff:\n{diff}")

        if self.dry_run:
            logger.info("Dry run, not writing to file")
            logger.info(
                f"~/{self.pyproject_toml_relpath}:\n"
                + indent(self.dump(pyproject), "    ")
            )
        else:
            logger.info("Writing to file")
            self.write_pyproject_toml(pyproject)


def colordiff(string_a: str, string_b: str) -> str:
    """
    Print or return a colour-coded diff of two items in a list of strings.
    Default: Compare first and last strings; print the output; return None.
    """
    green = "\x1b[38;5;16;48;5;2m"
    red = "\x1b[38;5;16;48;5;1m"
    end = "\x1b[0m"
    output: list[str] = []
    matcher = difflib.SequenceMatcher(None, string_a, string_b)
    for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
        if opcode == "equal":
            output += [string_a[a0:a1]]
        elif opcode == "insert":
            output += [green + string_b[b0:b1] + end]
        elif opcode == "delete":
            output += [red + string_a[a0:a1] + end]
        elif opcode == "replace":
            output += [green + string_b[b0:b1] + end]
            output += [red + string_a[a0:a1] + end]
    return "".join(output)


def main():
    args = parse_args()
    for package in args.packages:
        logger.info(f"Processing package: '{package}'")
        project = Project(name=package, dry_run=args.dry_run)
        if args.create:
            logger.info(f"Creating package: '{package}'")
            project.create()
        else:
            logger.info(f"Updating package: '{package}'")
            project.update()


if __name__ == "__main__":
    main()
