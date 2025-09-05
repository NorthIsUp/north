#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "tomli-w", "rich", "click",
# ]
# ///
"""
Helper script to update packages/north/pyproject.toml with all packages found in packages/
and create new namespaced packages.
"""

import tomllib
from inspect import cleandoc
from pathlib import Path
from textwrap import dedent
from typing import Dict, List

import click
import tomli_w
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.traceback import install as install_traceback

console = Console()
install_traceback(show_locals=True)


def scan_packages() -> List[Dict[str, str]]:
    """Scan packages/ directory and return list of package info."""
    packages_dir = Path("packages")
    packages = []

    if not packages_dir.exists():
        console.print("[red]❌ packages/ directory not found[/red]")
        return packages

    # Get all package directories
    package_dirs = [
        d
        for d in packages_dir.iterdir()
        if d.is_dir() and d.name != "north" and d.suffix != ".bak"
    ]

    if not package_dirs:
        console.print("[yellow]⚠️  No packages found in packages/ directory[/yellow]")
        return packages

    for pkg_dir in package_dirs:
        pyproject_path = pkg_dir / "pyproject.toml"
        if not pyproject_path.exists():
            console.print(
                f"[yellow]⚠️  {pkg_dir.name} has no pyproject.toml, skipping[/yellow]"
            )
            continue

        try:
            config = tomllib.loads(pyproject_path.read_text())

            package_name = config["project"]["name"]
            description = config["project"].get("description", "")

            # Extract the subpackage name (e.g., "north-string" -> "string")
            if package_name.startswith("north-"):
                extra_name = package_name[6:]  # Remove "north-" prefix
            else:
                extra_name = package_name

            packages.append(
                {
                    "name": package_name,
                    "extra_name": extra_name,
                    "description": description,
                    "path": str(pkg_dir),
                }
            )

        except Exception as e:
            console.print(f"[red]❌ Error reading {pyproject_path}: {e}[/red]")

    return sorted(packages, key=lambda x: x["extra_name"])


def check_missing_packages(packages: List[Dict[str, str]]) -> None:
    """Check for packages in TOML files that no longer exist in filesystem."""
    north_config_path = Path("packages/north/pyproject.toml")
    workspace_config_path = Path("pyproject.toml")

    missing_packages = []

    # Check north config
    if north_config_path.exists():
        config = tomllib.loads(north_config_path.read_text())

        optional_deps = config.get("project", {}).get("optional-dependencies", {})
        for extra_name, pkg_list in optional_deps.items():
            if extra_name == "all":
                continue
            for pkg_name in pkg_list:
                if not any(pkg["name"] == pkg_name for pkg in packages):
                    missing_packages.append((pkg_name, "north config"))

    # Check workspace config
    if workspace_config_path.exists():
        config = tomllib.loads(workspace_config_path.read_text())

        members = (
            config.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
        )
        for member in members:
            if member.startswith("packages/") and not member.endswith(".bak"):
                pkg_dir = Path(member)
                if not pkg_dir.exists():
                    pkg_name = pkg_dir.name
                    if not any(pkg["name"] == pkg_name for pkg in packages):
                        missing_packages.append((pkg_name, "workspace config"))

    # Report missing packages
    if missing_packages:
        console.print(
            "\n[yellow]⚠️  Found packages in configuration that no longer exist:[/yellow]"
        )
        for pkg_name, config_type in missing_packages:
            console.print(f"  [red]•[/red] {pkg_name} (in {config_type})")


def update_north_config(packages: List[Dict[str, str]]) -> None:
    """Update packages/north/pyproject.toml with discovered packages."""
    north_config_path = Path("packages/north/pyproject.toml")

    if not north_config_path.exists():
        console.print(f"[red]❌ Error: {north_config_path} does not exist[/red]")
        return

    # Read current config
    config = tomllib.loads(north_config_path.read_text())

    # Update optional-dependencies
    optional_deps = config.setdefault("project", {}).setdefault(
        "optional-dependencies", {}
    )

    # Clear existing optional dependencies and add only current packages
    optional_deps.clear()

    # Add individual extras
    for pkg in packages:
        optional_deps[pkg["extra_name"]] = [pkg["name"]]

    # Update "all" extra
    all_packages = [pkg["name"] for pkg in packages]
    optional_deps["all"] = all_packages

    # Update tool.uv.sources
    sources = (
        config.setdefault("tool", {}).setdefault("uv", {}).setdefault("sources", {})
    )

    # Clear existing sources and add only current packages
    sources.clear()

    # Add workspace sources for all packages
    for pkg in packages:
        sources[pkg["name"]] = {"workspace": True}

    # Write updated config
    north_config_path.write_text(tomli_w.dumps(config, indent=2))
    console.print(f"[green]✅ Updated {north_config_path}[/green]")

    # Create a nice table for packages
    table = Table(
        title="📦 Discovered Packages", show_header=True, header_style="bold magenta"
    )
    table.add_column("Extra Name", style="cyan", no_wrap=True)
    table.add_column("Package Name", style="green")
    table.add_column("Description", style="white")

    for pkg in packages:
        table.add_row(
            pkg["extra_name"],
            pkg["name"],
            pkg["description"] or "[dim]No description[/dim]",
        )

    console.print(table)


def update_workspace_config(packages: List[Dict[str, str]]) -> None:
    """Update root pyproject.toml workspace members."""
    workspace_config_path = Path("pyproject.toml")

    if not workspace_config_path.exists():
        console.print(
            f"[yellow]⚠️  Warning: {workspace_config_path} does not exist[/yellow]"
        )
        return

    # Read current config
    config = tomllib.loads(workspace_config_path.read_text())

    members = (
        config.setdefault("tool", {})
        .setdefault("uv", {})
        .setdefault("workspace", {})
        .setdefault("members", [])
    )

    # Clear existing members and rebuild
    members.clear()

    # Build members list
    members.append("packages/north")  # Always include main north package
    for pkg in packages:
        members.append(f"packages/{Path(pkg['path']).name}")

    members[:] = sorted(set(members))

    # Write updated config
    workspace_config_path.write_text(tomli_w.dumps(config, indent=2))

    console.print(
        f"[green]✅ Updated {workspace_config_path} workspace members[/green]"
    )


def create_namespaced_package(package_name: str, description: str = "") -> None:
    """Create a new namespaced package with pyproject.toml, src structure, and __init__.py."""
    # Validate package name
    if not package_name.replace("-", "").replace("_", "").isalnum():
        raise ValueError(
            f"Invalid package name '{package_name}'. Use alphanumeric characters, hyphens, and underscores only."
        )

    # Ensure package name starts with 'north-'
    if not package_name.startswith("north-"):
        package_name = f"north-{package_name}"

    # Extract the subpackage name for the namespace
    subpackage_name = package_name[6:]  # Remove "north-" prefix

    # Create package directory
    package_dir = Path("packages") / package_name
    if package_dir.exists():
        raise FileExistsError(f"Package directory '{package_dir}' already exists")

    # Create directories
    package_dir.mkdir(parents=True, exist_ok=True)
    src_dir = package_dir / "src" / "north" / subpackage_name
    src_dir.mkdir(parents=True, exist_ok=True)

    # Create __init__.py
    init_file = src_dir / "__init__.py"
    init_file.write_text(
        '"""North namespace package for {subpackage_name} functionality."""\n'.format(
            subpackage_name=subpackage_name
        )
    )

    # Create pyproject.toml
    pyproject_content = cleandoc(f"""[project]
        name            = "{package_name}"
        version         = "0.1.0"
        description     = "{description or f"{subpackage_name.title()} utilities for the north namespace"}"
        requires-python = ">=3.13"
        dependencies    = []

        [build-system]
        requires      = ["uv_build>=0.8,<0.9"]
        build-backend = "uv_build"

        [tool.uv.build-backend]
        namespace = true
        """)

    pyproject_file = package_dir / "pyproject.toml"
    pyproject_file.write_text(pyproject_content)

    # Create a beautiful summary panel
    summary_text = dedent(f"""
        [bold green]✅ Package Created Successfully![/bold green]

        [bold cyan]Package Name:[/bold cyan] {package_name}
        [bold cyan]Namespace:[/bold cyan] north.{subpackage_name}
        [bold cyan]Directory:[/bold cyan] {package_dir}
        [bold cyan]Description:[/bold cyan] {description or f"{subpackage_name.title()} utilities for the north namespace"}

        [bold yellow]Files Created:[/bold yellow]
            📄 {pyproject_file}
            📄 {init_file}

        [bold blue]Next Steps:[/bold blue]
            1. Add your code to src/north/{subpackage_name}/
            2. Run this script without --create to update configurations
            3. Start developing your package!
    """).strip()

    console.print(
        Panel(summary_text, title="🎉 Package Creation Complete", border_style="green")
    )


def print_extras_summary(packages: List[Dict[str, str]]) -> None:
    """Print a summary of the packages."""
    # Create a table for extras
    table = Table(
        title="Available Extras", show_header=True, header_style="bold yellow"
    )
    table.add_column("Extra", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")

    for pkg in packages:
        extra_name = f"north[{pkg['extra_name']}]"
        description = pkg["description"] or "No description"
        # Use Text objects to avoid Rich markup interpretation
        extra_text = Text(extra_name, style="cyan")
        desc_text = Text(description)
        table.add_row(extra_text, desc_text)

    table.add_row(
        Text("north[all]", style="bold cyan"), Text("All packages", style="bold")
    )

    summary_text = dedent(f"""
        [bold green]✅ Configuration updated! Found {len(packages)} packages:[/bold green]
    """).strip()

    console.print(summary_text)
    console.print(table)


@click.command()
@click.option("--create", "-c", "package_name", help="Create a new namespaced package")
@click.option("--description", "-d", help="Description for the new package")
def main(package_name: str | None, description: str | None) -> None:
    """Main function."""
    # Show welcome banner
    console.print(
        Panel.fit(
            "[bold blue]North Package Manager[/bold blue]\n"
            "Manage your namespaced packages with style! 🚀",
            border_style="blue",
        )
    )

    if package_name:
        # Create new package
        try:
            create_namespaced_package(package_name, description or "")
            console.print(
                Panel.fit(
                    f"[green]✅ Package '{package_name}' created successfully![/green]\n"
                    f"Run without --create to update configurations.",
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

    # Update existing packages
    console.print("\n[bold blue]🔍 Scanning packages directory...[/bold blue]")
    packages = scan_packages()

    if not packages:
        console.print(
            Panel.fit(
                "[yellow]⚠️  No packages found in packages/ directory[/yellow]\n"
                "Use [cyan]--create[/cyan] to create a new package!",
                title="No Packages Found",
                border_style="yellow",
            )
        )
        return

    # Check for missing packages before updating
    check_missing_packages(packages)

    console.print("\n[bold blue]📝 Updating configuration files...[/bold blue]")
    update_north_config(packages)
    update_workspace_config(packages)
    print_extras_summary(packages)


if __name__ == "__main__":
    main()
