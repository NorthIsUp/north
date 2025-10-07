"""
Pydantic models for pyproject.toml file structure with TOML serialization support.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Self, overload

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_serializer
from tomlkit.container import Container
from tomlkit.items import Null

if TYPE_CHECKING:
    from pydantic_core.core_schema import SerializerFunctionWrapHandler


class TomlSerializableModel(BaseModel):
    """Base model with TOML serialization capabilities."""

    # Accept population by field name and alias across all models
    model_config = ConfigDict(populate_by_name=True)

    @model_serializer(mode="wrap", when_used="always")
    def _serialize(self, serializer: SerializerFunctionWrapHandler, info) -> Any:
        """
        Custom serializer that supports TOML output via context.

        Note: Return type is Any to avoid Pydantic schema generation errors.
        Actual return types:
            - Container if context={'format': 'toml'}
            - dict[str, Any] otherwise
        """
        # Get the default serialized data (with aliases)
        data = serializer(self)

        # Check if we should return TOML structures
        if info.context and info.context.get("format") == "toml":
            return self._convert_to_toml(data)

        return data

    # Overloaded model_dump for better type hints
    @overload
    def model_dump(
        self,
        *,
        context: dict[Literal["format"], Literal["toml"]],
        by_alias: bool = True,
        **kwargs: Any,
    ) -> Container: ...

    @overload
    def model_dump(
        self,
        *,
        context: None = None,
        by_alias: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    def model_dump(
        self,
        *,
        context: dict[str, str] | None = None,
        by_alias: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any] | Container:
        """
        Dump model to dict or tomlkit Container based on context.

        Args:
            context: If {'format': 'toml'}, returns Container, otherwise dict
            by_alias: Use field aliases in output
            **kwargs: Additional arguments passed to BaseModel.model_dump

        Returns:
            Container if context={'format': 'toml'}, otherwise dict[str, Any]
        """
        return super().model_dump(context=context, by_alias=by_alias, **kwargs)

    def _convert_to_toml(self, data: dict[str, Any]) -> Container:
        """Convert a dict to tomlkit Container recursively."""
        table = tomlkit.table()
        for key, value in data.items():
            table[key] = self._value_to_toml(value)
        return table

    def _value_to_toml(self, value: Any) -> Any:
        """Convert a value to appropriate tomlkit type."""
        match value:
            case dict():
                table = tomlkit.table()
                for k, v in value.items():
                    table[k] = self._value_to_toml(v)
                return table
            case list() | tuple() | set() | frozenset():
                array = tomlkit.array()
                array.extend([self._value_to_toml(v) for v in value])
                return array
            case None:
                return Null()
            case _:
                return value

    def model_dump_toml(
        self,
        target_document: tomlkit.TOMLDocument | None = None,
        drop_none: bool = True,
        **kwargs: Any,
    ) -> tomlkit.TOMLDocument:
        """Dump the model to TOML document using tomlkit."""
        # Use model_dump with context to trigger TOML serialization
        data = self.model_dump(
            by_alias=True,
            exclude_none=drop_none,
            mode="python",
            context={"format": "toml"},
            **kwargs,
        )

        # Create or update target document
        target_document = target_document or tomlkit.document()
        if isinstance(data, Container):
            target_document.update(data)
        else:
            # Fallback if serializer didn't return Container
            for key, value in data.items():
                target_document[key] = value

        return target_document


class BuildSystem(TomlSerializableModel):
    """Build system configuration."""

    build_backend: str = Field(alias="build-backend")
    requires: list[str]


class DependencyGroup(TomlSerializableModel):
    """Dependency group configuration."""

    dev: list[str] | None = None
    test: list[str] | None = None
    docs: list[str] | None = None
    lint: list[str] | None = None


class RuffConfig(TomlSerializableModel):
    """Ruff configuration."""

    model_config = ConfigDict(populate_by_name=True)

    target_version: str = Field(alias="target-version")


class RuffLintConfig(TomlSerializableModel):
    """Ruff lint configuration."""

    model_config = ConfigDict(populate_by_name=True)

    extend_select: list[str] | None = None
    ignore: list[str] | None = None


class RuffTool(TomlSerializableModel):
    """Ruff tool configuration."""

    model_config = ConfigDict(populate_by_name=True)

    target_version: str = Field(alias="target-version")
    lint: RuffLintConfig | None = None


class PytestMarker(TomlSerializableModel):
    """Pytest marker configuration."""

    name: str
    description: str


class PytestIniOptions(TomlSerializableModel):
    """Pytest ini options configuration."""

    model_config = ConfigDict(populate_by_name=True)

    minversion: str | None = None
    addopts: list[str] | None = None
    markers: list[PytestMarker] | None = None
    testpaths: list[str] | None = None
    python_files: list[str] | None = None
    python_classes: list[str] | None = None
    python_functions: list[str] | None = None


class PytestTool(TomlSerializableModel):
    """Pytest tool configuration."""

    model_config = ConfigDict(populate_by_name=True)

    ini_options: PytestIniOptions | None = None


class ToolPyright(TomlSerializableModel):
    """Pyright tool configuration (tool.pyright)."""

    model_config = ConfigDict(populate_by_name=True)

    include: list[str] | None = None
    exclude: list[str] | None = None
    ignore: list[str] | None = None
    strict: list[str] | None = None
    venv_path: str | None = Field(None, alias="venvPath")
    venv: str | None = None
    python_version: str | None = Field(None, alias="pythonVersion")
    python_platform: str | None = Field(None, alias="pythonPlatform")
    type_checking_mode: str | None = Field(None, alias="typeCheckingMode")
    use_library_code_for_types: bool | None = Field(None, alias="useLibraryCodeForTypes")
    report_missing_imports: str | None = Field(None, alias="reportMissingImports")
    report_missing_type_stubs: str | None = Field(None, alias="reportMissingTypeStubs")
    report_unused_import: str | None = Field(None, alias="reportUnusedImport")
    report_unused_variable: str | None = Field(None, alias="reportUnusedVariable")
    report_duplicate_import: str | None = Field(None, alias="reportDuplicateImport")


class UvBuildBackend(TomlSerializableModel):
    """UV build backend configuration."""

    model_config = ConfigDict(populate_by_name=True)

    namespace: bool | None = None
    module_root: str | None = Field(None, alias="module-root")


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
                    build_backend=UvBuildBackend(namespace=True),
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

    model_config = ConfigDict(populate_by_name=True)

    build_backend: UvBuildBackend | None = Field(None, alias="build-backend")
    workspace: UvWorkspace | None = None
    sources: dict[str, UvSource] | None = None

    @property
    def _sources(self) -> dict[str, UvSource]:
        self.sources = self.sources or {}
        return self.sources

    @property
    def _workspace(self) -> UvWorkspace:
        self.workspace = self.workspace or UvWorkspace(members=[])
        return self.workspace

    def model_dump_toml(self, target_document: tomlkit.TOMLDocument | None = None, **kwargs: Any) -> tomlkit.TOMLDocument:
        """Dump TOML ensuring [tool.uv.sources] uses inline tables per entry."""
        # Call super to get the base serialization
        result = super().model_dump_toml(target_document, **kwargs)

        # Do our work: format sources as inline tables
        if self.sources:
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
    def _uv(self) -> UvTool:
        self.uv = self.uv or UvTool()
        return self.uv


class Project(TomlSerializableModel):
    """Project configuration."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    version: str
    description: str | None = None
    requires_python: str | None = Field(None, alias="requires-python")
    dependencies: list[str] | None = None
    optional_dependencies: dict[str, list[str]] | None = Field(None, alias="optional-dependencies")
    authors: list[dict[str, str]] | None = None
    maintainers: list[dict[str, str]] | None = None
    keywords: list[str] | None = None
    classifiers: list[str] | None = None
    urls: dict[str, str] | None = None
    scripts: dict[str, str] | None = None
    gui_scripts: dict[str, str] | None = Field(None, alias="gui-scripts")
    entry_points: dict[str, dict[str, str]] | None = Field(None, alias="entry-points")


class PyProjectToml(TomlSerializableModel):
    """Complete pyproject.toml file structure."""

    model_config = ConfigDict(populate_by_name=True)

    build_system: BuildSystem | None = Field(None, alias="build-system")
    project: Project | None = None
    dependency_groups: DependencyGroup | None = Field(None, alias="dependency-groups")
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
    def _tool(self) -> Tool:
        self.tool = self.tool or Tool()
        return self.tool

    def write(self, path: str | Path) -> None:
        """Write pyproject.toml to file."""
        path = Path(path)
        toml_doc = self.model_dump_toml()
        path.write_text(tomlkit.dumps(toml_doc))


class UvWorkspacePyProjectToml(PyProjectToml):
    """PyProject.toml with UV workspace-specific functionality."""

    def get_workspace_members(self) -> list[str]:
        """Get workspace members from uv.workspace.members."""
        if not self.tool or not self.tool.uv or not self.tool.uv.workspace:
            return []
        return self.tool.uv.workspace.members

    def get_workspace_sources(self) -> dict[str, UvSource]:
        """Get workspace sources from uv.sources."""
        if not self.tool or not self.tool.uv or not self.tool.uv.sources:
            return {}
        return self.tool.uv.sources

    def add_workspace_member(self, member: str) -> None:
        """Add a workspace member."""
        if member not in self._tool._uv._workspace.members:
            self.tool.uv.workspace.members.append(member)
            self.tool.uv.workspace.members.sort()

    def add_workspace_source(self, package_name: str, source: UvSource) -> None:
        """Add a workspace source."""
        self._tool._uv._sources[package_name] = source

    def remove_workspace_member(self, member: str) -> None:
        """Remove a workspace member."""
        if self.tool and self.tool.uv and self.tool.uv.workspace and member in self.tool.uv.workspace.members:
            self.tool.uv.workspace.members.remove(member)

    def remove_workspace_source(self, package_name: str) -> None:
        """Remove a workspace source."""
        if self.tool and self.tool.uv and self.tool.uv.sources and package_name in self.tool.uv.sources:
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
    except (ValidationError, tomlkit.exceptions.TOMLKitError) as e:
        print(f"❌ Error: {e}")
