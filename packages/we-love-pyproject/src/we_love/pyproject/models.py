"""
Pydantic models for pyproject.toml file structure with TOML serialization support.
"""

from __future__ import annotations

from pathlib import Path
from typing import Self, TypedDict, Unpack, override

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, JsonValue, RootModel, ValidationError
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Table


class TomlDumpOptions(TypedDict, total=False):
    exclude_none: bool
    exclude_unset: bool
    exclude_defaults: bool
    by_alias: bool


class TomlSerializableModel(BaseModel):
    """Models with an explicit TOML serialization boundary."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    def model_dump_toml(
        self,
        target_document: tomlkit.TOMLDocument | None = None,
        drop_none: bool = True,
        **kwargs: Unpack[TomlDumpOptions],
    ) -> tomlkit.TOMLDocument:
        options: TomlDumpOptions = {"exclude_none": drop_none, "by_alias": True, **kwargs}
        data = RootModel[dict[str, JsonValue]].model_validate(self.model_dump(mode="json", **options)).root
        document = target_document if target_document is not None else tomlkit.document()
        for key, value in data.items():
            if value is not None:
                document[key] = value
        return document


class BuildSystem(TomlSerializableModel):
    """Build system configuration."""

    build_backend: str = Field(validation_alias="build-backend", serialization_alias="build-backend")
    requires: list[str]
    dependency_groups: DependencyGroup | None = None


class DependencyInclude(TomlSerializableModel):
    include_group: str = Field(alias="include-group")


class DependencyGroup(TomlSerializableModel):
    """Dependency group configuration."""

    dev: list[str | DependencyInclude] | None = None
    test: list[str | DependencyInclude] | None = None
    docs: list[str | DependencyInclude] | None = None
    lint: list[str | DependencyInclude] | None = None


class RuffConfig(TomlSerializableModel):
    """Ruff configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    target_version: str | None = Field(default=None, validation_alias="target-version", serialization_alias="target-version")


class RuffLintConfig(TomlSerializableModel):
    """Ruff lint configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    extend_select: list[str] | None = None
    ignore: list[str] | None = None


class RuffTool(TomlSerializableModel):
    """Ruff tool configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    target_version: str | None = Field(default=None, validation_alias="target-version", serialization_alias="target-version")
    lint: RuffLintConfig | None = None


class PytestMarker(TomlSerializableModel):
    """Pytest marker configuration."""

    name: str
    description: str


class PytestIniOptions(TomlSerializableModel):
    """Pytest ini options configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    minversion: str | None = None
    addopts: str | list[str] | None = None
    markers: list[str | PytestMarker] | None = None
    testpaths: list[str] | None = None
    python_files: list[str] | None = None
    python_classes: list[str] | None = None
    python_functions: list[str] | None = None


class PytestTool(TomlSerializableModel):
    """Pytest tool configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    ini_options: PytestIniOptions | None = None


class ToolPyright(TomlSerializableModel):
    """Pyright tool configuration (tool.pyright)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    include: list[str] | None = None
    exclude: list[str] | None = None
    ignore: list[str] | None = None
    strict: list[str] | None = None
    venv_path: str | None = Field(default=None, validation_alias="venvPath", serialization_alias="venvPath")
    venv: str | None = None
    python_version: str | None = Field(default=None, validation_alias="pythonVersion", serialization_alias="pythonVersion")
    python_platform: str | None = Field(default=None, validation_alias="pythonPlatform", serialization_alias="pythonPlatform")
    type_checking_mode: str | None = Field(default=None, validation_alias="typeCheckingMode", serialization_alias="typeCheckingMode")
    use_library_code_for_types: bool | None = Field(
        default=None, validation_alias="useLibraryCodeForTypes", serialization_alias="useLibraryCodeForTypes"
    )
    report_missing_imports: str | None = Field(
        default=None, validation_alias="reportMissingImports", serialization_alias="reportMissingImports"
    )
    report_missing_type_stubs: str | None = Field(
        default=None, validation_alias="reportMissingTypeStubs", serialization_alias="reportMissingTypeStubs"
    )
    report_unused_import: str | None = Field(default=None, validation_alias="reportUnusedImport", serialization_alias="reportUnusedImport")
    report_unused_variable: str | None = Field(
        default=None, validation_alias="reportUnusedVariable", serialization_alias="reportUnusedVariable"
    )
    report_duplicate_import: str | None = Field(
        default=None, validation_alias="reportDuplicateImport", serialization_alias="reportDuplicateImport"
    )


class UvBuildBackend(TomlSerializableModel):
    """UV build backend configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    namespace: bool | None = None
    module_name: str | None = Field(default=None, validation_alias="module-name", serialization_alias="module-name")
    module_root: str | None = Field(default=None, validation_alias="module-root", serialization_alias="module-root")


class UvWorkspace(TomlSerializableModel):
    """UV workspace configuration."""

    members: list[str]


class UvSource(TomlSerializableModel):
    """UV source configuration."""

    workspace: bool = True
    path: str | None = None
    url: str | None = None
    git: str | None = None
    tag: str | None = None
    branch: str | None = None
    rev: str | None = None


class Package(TomlSerializableModel):
    """Represents a workspace package."""

    name: str
    extra_name: str
    description: str = ""
    path: Path
    pyproject: UvWorkspacePyProjectToml

    @classmethod
    def from_dir(cls, pkg_dir: Path) -> Package:
        pyproject_path = pkg_dir / "pyproject.toml"
        py = UvWorkspacePyProjectToml.from_file(pyproject_path)
        if not py.project or not py.project.name:
            raise ValueError(f"missing 'project.name' in '{pyproject_path}'")
        name = py.project.name
        description = py.project.description or ""
        extra_name = name[8:].replace("-", "_") if name.startswith("we-love-") else name
        return cls(
            name=name,
            extra_name=extra_name,
            description=description,
            path=pkg_dir,
            pyproject=py,
        )

    @classmethod
    def create_namespaced(cls, packages_dir: Path, package_name: str, description: str = "") -> Package:
        if not package_name.startswith("we-love-"):
            package_name = f"we-love-{package_name}"

        subpackage_name = package_name[8:].replace("-", "_")  # Strip "we-love-" and replace hyphens
        package_dir = packages_dir / package_name
        if package_dir.exists():
            raise FileExistsError(f"Package directory '{package_dir}' already exists")

        # Create directories
        src_dir = package_dir / "src" / "we_love" / subpackage_name
        src_dir.mkdir(parents=True, exist_ok=True)

        # __init__.py
        init_file = src_dir / "__init__.py"
        init_file.write_text(f'"""We Love namespace package for {subpackage_name} functionality."""\n')

        # pyproject.toml content via models
        py = UvWorkspacePyProjectToml(
            build_system=BuildSystem(
                build_backend="uv_build",
                requires=["uv-build>=0.8,<0.9"],
            ),
            project=Project(
                name=package_name,
                version="0.1.0",
                description=description or f"{subpackage_name.title()} utilities for the we_love namespace",
                requires_python=">=3.13",
                dependencies=[],
            ),
            tool=Tool(
                uv=UvTool(
                    build_backend=UvBuildBackend(namespace=True, module_name="we_love"),
                ),
                pyright=ToolPyright(
                    venv=".venv",
                    venv_path=".",
                ),
            ),
        )

        pyproject_file = package_dir / "pyproject.toml"
        py.write(pyproject_file)

        return cls(
            name=package_name,
            extra_name=subpackage_name,
            description=description,
            path=package_dir,
            pyproject=py,
        )

    def write_pyproject(self) -> None:
        """Write this package's pyproject back to disk."""
        self.pyproject.write(self.path / "pyproject.toml")


class UvTool(TomlSerializableModel):
    """UV tool configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    build_backend: UvBuildBackend | None = Field(default=None, validation_alias="build-backend", serialization_alias="build-backend")
    workspace: UvWorkspace | None = None
    sources: dict[str, UvSource] | None = None

    @property
    def ensure_sources(self) -> dict[str, UvSource]:
        self.sources = self.sources or {}
        return self.sources

    @property
    def ensure_workspace(self) -> UvWorkspace:
        self.workspace = self.workspace or UvWorkspace(members=[])
        return self.workspace

    @override
    def model_dump_toml(
        self, target_document: tomlkit.TOMLDocument | None = None, drop_none: bool = True, **kwargs: Unpack[TomlDumpOptions]
    ) -> tomlkit.TOMLDocument:
        """Dump TOML ensuring [tool.uv.sources] uses inline tables per entry."""
        # Call super to get the base serialization
        result = super().model_dump_toml(target_document, drop_none, **kwargs)

        # Do our work: format sources as inline tables
        if self.sources is not None:
            sources_table = tomlkit.table()
            for pkg_name, source_cfg in sorted(self.sources.items()):
                inline = tomlkit.inline_table()
                for key, value in source_cfg.model_dump(exclude_none=True, by_alias=True).items():
                    inline[key] = value
                sources_table.add(pkg_name, inline)
            result["sources"] = sources_table

        return result


class Tool(TomlSerializableModel):
    """Tool configuration section."""

    ruff: RuffTool | None = None
    pytest: PytestTool | None = None
    pyright: ToolPyright | None = None
    uv: UvTool | None = None

    @property
    def ensure_uv(self) -> UvTool:
        self.uv = self.uv or UvTool()
        return self.uv


class Project(TomlSerializableModel):
    """Project configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str
    version: str
    description: str | None = None
    requires_python: str | None = Field(default=None, validation_alias="requires-python", serialization_alias="requires-python")
    dependencies: list[str] | None = None
    optional_dependencies: dict[str, list[str]] | None = Field(
        default=None, validation_alias="optional-dependencies", serialization_alias="optional-dependencies"
    )
    authors: list[dict[str, str]] | None = None
    maintainers: list[dict[str, str]] | None = None
    keywords: list[str] | None = None
    classifiers: list[str] | None = None
    urls: dict[str, str] | None = None
    scripts: dict[str, str] | None = None
    gui_scripts: dict[str, str] | None = Field(default=None, validation_alias="gui-scripts", serialization_alias="gui-scripts")
    entry_points: dict[str, dict[str, str]] | None = Field(
        default=None, validation_alias="entry-points", serialization_alias="entry-points"
    )


class PyProjectToml(TomlSerializableModel):
    """Complete pyproject.toml file structure."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    build_system: BuildSystem | None = Field(default=None, validation_alias="build-system", serialization_alias="build-system")
    project: Project | None = None
    dependency_groups: DependencyGroup | None = Field(
        default=None, validation_alias="dependency-groups", serialization_alias="dependency-groups"
    )
    tool: Tool | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> Self:
        """Load pyproject.toml from file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"pyproject.toml not found at {path}")

        content = path.read_text()
        data = tomlkit.loads(content)
        return cls.model_validate(data)

    @property
    def ensure_tool(self) -> Tool:
        self.tool = self.tool or Tool()
        return self.tool

    def write(self, path: str | Path) -> None:
        """Write pyproject.toml to file."""
        path = Path(path)
        toml_doc = self.model_dump_toml()
        path.write_text(tomlkit.dumps(toml_doc))


class UvWorkspacePyProjectToml(PyProjectToml):
    """PyProject.toml with UV workspace-specific functionality."""

    @override
    def model_dump_toml(
        self, target_document: tomlkit.TOMLDocument | None = None, drop_none: bool = True, **kwargs: Unpack[TomlDumpOptions]
    ) -> tomlkit.TOMLDocument:
        document = super().model_dump_toml(target_document, drop_none, **kwargs)
        if self.tool is not None and self.tool.uv is not None:
            uv_document = self.tool.uv.model_dump_toml(drop_none=drop_none, **kwargs)
            tool_value = document["tool"]
            if isinstance(tool_value, Table):
                tool_value["uv"] = uv_document
        return document

    def get_workspace_members(self) -> list[str]:
        """Get workspace members from uv.workspace.members."""
        if not self.tool or not self.tool.uv or not self.tool.uv.workspace:
            return []
        return self.tool.uv.workspace.members

    def get_workspace_sources(self) -> dict[str, UvSource]:
        """Get workspace sources from uv.sources."""
        if not self.tool or not self.tool.uv or self.tool.uv.sources is None:
            return {}
        return self.tool.uv.sources

    def add_workspace_member(self, member: str) -> None:
        """Add a workspace member."""
        workspace = self.ensure_tool.ensure_uv.ensure_workspace
        if member not in workspace.members:
            workspace.members.append(member)
            workspace.members.sort()

    def add_workspace_source(self, package_name: str, source: UvSource) -> None:
        """Add a workspace source."""
        self.ensure_tool.ensure_uv.ensure_sources[package_name] = source

    def remove_workspace_member(self, member: str) -> None:
        """Remove a workspace member."""
        if self.tool and self.tool.uv and self.tool.uv.workspace and member in self.tool.uv.workspace.members:
            self.tool.uv.workspace.members.remove(member)

    def remove_workspace_source(self, package_name: str) -> None:
        """Remove a workspace source."""
        if self.tool and self.tool.uv and self.tool.uv.sources is not None and package_name in self.tool.uv.sources:
            del self.tool.uv.sources[package_name]


# Example usage and testing
if __name__ == "__main__":
    # Test loading and dumping
    try:
        pyproject = UvWorkspacePyProjectToml.from_file("pyproject.toml")
        print("✅ Successfully loaded pyproject.toml")
        print(f"Workspace members: {pyproject.get_workspace_members()}")
        print(f"Workspace sources: {list(pyproject.get_workspace_sources().keys())}")

        # Test adding a new member
        pyproject.add_workspace_member("packages/we-love-test")
        pyproject.add_workspace_source("we-love-test", UvSource(workspace=True))

        print("\n✅ Added test member and source")
        print(f"Updated workspace members: {pyproject.get_workspace_members()}")
        print(f"Updated workspace sources: {list(pyproject.get_workspace_sources().keys())}")

        # Test TOML serialization
        toml_output = pyproject.model_dump_toml()
        print(f"\n✅ TOML serialization successful (length: {len(toml_output)} chars)")

    except FileNotFoundError:
        print("❌ pyproject.toml not found in current directory")
    except (ValidationError, TOMLKitError) as e:
        print(f"❌ Error: {e}")
