#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "click",
#   "rich",
#   "tomlkit",
#   "we-love-pyproject@file:///${PROJECT_ROOT}/packages/we-love-pyproject"
# ]
# ///
"""
Helper script to update packages/we_love/pyproject.toml with all packages found in packages/
and create new namespaced packages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from textwrap import dedent

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.traceback import install as install_traceback
from we_love.pyproject.models import Package, PyProjectToml, ToolPyright, UvSource

console = Console()
install_traceback(show_locals=True)


@dataclass
class WeLoveWorkspaceManager:
    """Manage we_love workspace packages and pyproject configuration."""

    root: Path = field(default_factory=Path.cwd)
    packages: list[Package] = field(default_factory=list)

    @cached_property
    def packages_dir(self) -> Path:
        return self.root / "packages"

    @cached_property
    def workspace_config_path(self) -> Path:
        return self.root / "pyproject.toml"

    @cached_property
    def workspace_pyproject(self) -> PyProjectToml:
        """Loaded root pyproject.toml for the workspace."""
        return PyProjectToml.from_file(self.workspace_config_path)

    @cached_property
    def workspace_file_path(self) -> Path:
        """Path to the we_love.code-workspace file."""
        return self.root / "we-love.code-workspace"

    def __post_init__(self) -> None:
        self.scan_packages()

    def scan_packages(self) -> list[Package]:
        """Scan packages/ directory and return list of package info."""
        packages: list[Package] = []

        if not self.packages_dir.exists():
            console.print("[red]❌ packages/ directory not found[/red]")
            self.packages = []
            return self.packages

        package_dirs = [d for d in self.packages_dir.iterdir() if d.is_dir() and d.name != "we_love" and d.suffix != ".bak"]

        if not package_dirs:
            console.print("[yellow]⚠️  No packages found in packages/ directory[/yellow]")
            return self.packages

        for pkg_dir in package_dirs:
            pyproject_path = pkg_dir / "pyproject.toml"
            if not pyproject_path.exists():
                console.print(f"[yellow]⚠️  {pkg_dir.name} has no pyproject.toml, skipping[/yellow]")
                continue

            try:
                packages.append(Package.from_dir(pkg_dir))
            except Exception as e:  # noqa: BLE001
                console.print(f"[red]❌ Error reading {pyproject_path}: {e}[/red]")

        self.packages = sorted(packages, key=lambda x: x.extra_name)
        return self.packages

    def check_missing_packages(self) -> None:
        """Check for packages in TOML files that no longer exist in filesystem."""
        missing_packages: list[tuple[str, str]] = []

        # Check workspace config via models
        if self.workspace_config_path.exists():
            py = self.workspace_pyproject

            # Members listed but not present in scanned packages
            for member in py.get_workspace_members():
                if member.startswith("packages/") and not member.endswith(".bak"):
                    pkg_name = Path(member).name
                    if not any(pkg.path.name == pkg_name for pkg in self.packages):
                        missing_packages.append((pkg_name, "workspace members"))

            # Sources declared but not present in scanned packages
            for pkg_name, source in py.get_workspace_sources().items():
                if getattr(source, "workspace", False):
                    if not any(pkg.name == pkg_name for pkg in self.packages):
                        missing_packages.append((pkg_name, "uv.sources"))

        if missing_packages:
            console.print("\n[yellow]⚠️  Found packages in configuration that no longer exist:[/yellow]")
            for pkg_name, config_type in missing_packages:
                console.print(f"  [red]•[/red] {pkg_name} (in {config_type})")

    def update_workspace_config(self) -> None:
        """Update root pyproject.toml workspace members and sources using Pydantic models."""
        if not self.workspace_config_path.exists():
            console.print(f"[yellow]⚠️  Warning: {self.workspace_config_path} does not exist[/yellow]")
            return

        pyproject = self.workspace_pyproject

        member_paths = {f"packages/{pkg.path.name}" for pkg in self.packages}
        uv_workspace = pyproject._tool._uv._workspace
        uv_workspace.members = sorted(member_paths)

        uv_tool = pyproject._tool._uv
        uv_tool.sources = {}
        for pkg in self.packages:
            uv_tool._sources[pkg.name] = UvSource(workspace=True)

        pyproject.write(self.workspace_config_path)

        console.print(f"[green]✅ Updated {self.workspace_config_path} workspace members and sources[/green]")

    def update_workspace_file(self) -> None:
        """Update we_love.code-workspace file with folders for each package and exclude them from root."""
        if not self.workspace_file_path.exists():
            console.print(f"[yellow]⚠️  Warning: {self.workspace_file_path} does not exist[/yellow]")
            return

        # Load existing workspace file
        try:
            with open(self.workspace_file_path) as f:
                workspace_data = json.load(f)
        except Exception as e:
            console.print(f"[red]❌ Error reading {self.workspace_file_path}: {e}[/red]")
            return

        # Create folders list
        folders = [{"name": "we_love", "path": "."}]

        # Add folder for each package
        for pkg in self.packages:
            folder_name = pkg.name.replace("-", "-")
            folders.append({
                "name": "  — " + folder_name.removeprefix("we-love-"),
                "path": f"packages/{pkg.path.name}",
            })

        # Update the workspace data
        workspace_data["folders"] = folders

        # Add files.exclude settings to exclude package directories from root
        if "settings" not in workspace_data:
            workspace_data["settings"] = {}

        # Create files.exclude pattern for all package directories
        exclude_patterns = {
            "packages/*/": True,
            "packages/*/.*": True,
            "packages/*/__pycache__/": True,
            "packages/*/.*.pyc": True,
            "packages/*/.*.pyo": True,
            "packages/*/.*.pyd": True,
            "packages/*/.pytest_cache/": True,
            "packages/*/dist/": True,
            "packages/*/build/": True,
            "packages/*/*.egg-info/": True,
        }

        workspace_data["settings"]["files.exclude"] = exclude_patterns

        # Write the updated workspace file
        try:
            with open(self.workspace_file_path, "w") as f:
                json.dump(workspace_data, f, indent="\t")

            console.print(f"[green]✅ Updated {self.workspace_file_path} with {len(folders)} folders and exclusion patterns[/green]")
        except Exception as e:
            console.print(f"[red]❌ Error writing {self.workspace_file_path}: {e}[/red]")

    def update_package_configs(self) -> None:
        """Update individual package pyproject.toml files to ensure they have required configurations."""
        updated_count = 0

        for pkg in self.packages:
            updated = False

            # Check if pyright configuration is missing
            if pkg.pyproject.tool is None or pkg.pyproject.tool.pyright is None:
                # Ensure tool section exists
                if pkg.pyproject.tool is None:
                    from we_love.pyproject.models import Tool

                    pkg.pyproject.tool = Tool()

                # Add pyright configuration
                pkg.pyproject.tool.pyright = ToolPyright(
                    venv=".venv",
                    venv_path=".",
                )
                updated = True

            if updated:
                pkg.write_pyproject()
                updated_count += 1
                console.print(f"[green]✅ Updated {pkg.name} with pyright configuration[/green]")

        if updated_count > 0:
            console.print(f"[green]✅ Updated {updated_count} package(s) with missing configurations[/green]")
        else:
            console.print("[blue]ℹ️  All packages already have required configurations[/blue]")


def update_workspace_config(packages: list[Package]) -> None:
    """Update root pyproject.toml workspace members and sources using Pydantic models."""
    workspace_config_path = Path("pyproject.toml")

    if not workspace_config_path.exists():
        console.print(f"[yellow]⚠️  Warning: {workspace_config_path} does not exist[/yellow]")
        return

    # Load with models
    pyproject = PyProjectToml.from_file(workspace_config_path)

    # Build members list
    member_paths = {f"packages/{pkg.path.name}" for pkg in packages}

    # Ensure tool/uv/workspace exists and set members
    uv_workspace = pyproject._tool._uv._workspace
    uv_workspace.members = sorted(member_paths)

    # Rebuild sources as inline tables (workspace = true)
    uv_tool = pyproject._tool._uv
    uv_tool.sources = {}
    for pkg in packages:
        uv_tool.sources[pkg.name] = UvSource(workspace=True)

    # Write back to file
    pyproject.to_file(workspace_config_path)

    console.print(f"[green]✅ Updated {workspace_config_path} workspace members and sources[/green]")


def create_namespaced_package(package_name: str, description: str = "") -> None:
    """Create a new namespaced package via Project helper, then print a summary."""
    # Validate package name characters
    if not package_name.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"Invalid package name '{package_name}'. Use alphanumeric characters, hyphens, and underscores only.")

    packages_dir = Path("packages")
    created = Package.create_namespaced(packages_dir, package_name, description)

    subpackage_name = (package_name if package_name.startswith("we-love-") else f"we-love-{package_name}")[8:].replace(
        "-", "_"
    )  # Strip "we-love-" and replace hyphens
    summary_text = dedent(f"""
        [bold green]✅ Package Created Successfully![/bold green]

        [bold cyan]Package Name:[/bold cyan] {package_name if package_name.startswith("we-love-") else f"we-love-{package_name}"}
        [bold cyan]Namespace:[/bold cyan] we_love.{subpackage_name}
        [bold cyan]Directory:[/bold cyan] {created.path}
        [bold cyan]Description:[/bold cyan] {description or f"{subpackage_name.title()} utilities for the we_love namespace"}

        [bold yellow]Files Created:[/bold yellow]
            📄 {created.path / "pyproject.toml"}
            📄 {created.path / "src" / "we_love" / subpackage_name / "__init__.py"}

        [bold blue]Next Steps:[/bold blue]
            1. Add your code to src/we_love/{subpackage_name}/
            2. Run this script without --create to update configurations
            3. Start developing your package!
    """).strip()

    console.print(Panel(summary_text, title="🎉 Package Creation Complete", border_style="green"))


def print_extras_summary(packages: list[Package]) -> None:
    """Print a summary of the packages."""
    # Create a table for extras
    table = Table(title="Available Extras", show_header=True, header_style="bold yellow")
    table.add_column("Extra", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")

    for pkg in packages:
        extra_name = f"we_love[{pkg.extra_name}]"
        description = pkg.description or "No description"
        # Use Text objects to avoid Rich markup interpretation
        extra_text = Text(extra_name, style="cyan")
        desc_text = Text(description)
        table.add_row(extra_text, desc_text)

    table.add_row(Text("we_love[all]", style="bold cyan"), Text("All packages", style="bold"))

    summary_text = dedent(f"""
        [bold green]✅ Configuration updated! Found {len(packages)} packages:[/bold green]
    """).strip()

    console.print(summary_text)
    console.print(table)


@click.command()
@click.option("--create", "-c", "package_name", help="Create a new namespaced package")
@click.option("--description", "-d", help="Description for the new package")
@click.option("--workspace-only", "-w", is_flag=True, help="Update only the workspace file")
def main(package_name: str | None, description: str | None, workspace_only: bool) -> None:
    """Main function."""
    # Show welcome banner
    console.print(
        Panel.fit(
            "[bold blue]WeLove Package Manager[/bold blue]\nManage your namespaced packages with style! 🚀",
            border_style="blue",
        )
    )

    if package_name:
        # Create new package
        try:
            create_namespaced_package(package_name, description or "")
            console.print(
                Panel.fit(
                    f"[green]✅ Package '{package_name}' created successfully![/green]\nRun without --create to update configurations.",
                    title="🎉 Success",
                    border_style="green",
                )
            )
        except Exception as e:
            console.print(
                Panel.fit(
                    f"[red]❌ Error creating package: {e}[/red]",
                    title="Error",
                    border_style="red",
                )
            )
            return

    # Update existing packages (class-based)
    console.print("\n[bold blue]🔍 Scanning packages directory...[/bold blue]")
    manager = WeLoveWorkspaceManager()
    packages = manager.scan_packages()

    if not packages:
        console.print(
            Panel.fit(
                "[yellow]⚠️  No packages found in packages/ directory[/yellow]\nUse [cyan]--create[/cyan] to create a new package!",
                title="No Packages Found",
                border_style="yellow",
            )
        )
        return

    if workspace_only:
        console.print("\n[bold blue]📝 Updating workspace file only...[/bold blue]")
        manager.update_workspace_file()
        return

    # Check for missing packages before updating
    manager.check_missing_packages()

    console.print("\n[bold blue]📝 Updating configuration files...[/bold blue]")
    manager.update_package_configs()
    manager.update_workspace_config()
    manager.update_workspace_file()
    print_extras_summary(packages)


if __name__ == "__main__":
    main()
