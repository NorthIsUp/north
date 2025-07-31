#!/usr/bin/env python3
"""
Helper script to update packages/north/pyproject.toml with all packages found in packages/
"""

import tomllib
from pathlib import Path
from typing import Dict, List

import tomli_w


def scan_packages() -> List[Dict[str, str]]:
    """Scan packages/ directory and return list of package info."""
    packages_dir = Path("packages")
    packages = []

    for pkg_dir in packages_dir.iterdir():
        if not pkg_dir.is_dir() or pkg_dir.name == "north":
            continue

        pyproject_path = pkg_dir / "pyproject.toml"
        if not pyproject_path.exists():
            print(f"Warning: {pkg_dir.name} has no pyproject.toml, skipping")
            continue

        try:
            with open(pyproject_path, "rb") as f:
                config = tomllib.load(f)

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
            print(f"Error reading {pyproject_path}: {e}")
            continue

    return sorted(packages, key=lambda x: x["extra_name"])


def update_north_config(packages: List[Dict[str, str]]) -> None:
    """Update packages/north/pyproject.toml with discovered packages."""
    north_config_path = Path("packages/north/pyproject.toml")

    if not north_config_path.exists():
        print(f"Error: {north_config_path} does not exist")
        return

    # Read current config
    with open(north_config_path, "rb") as f:
        config = tomllib.load(f)

    # Update optional-dependencies
    if "project" not in config:
        config["project"] = {}

    if "optional-dependencies" not in config["project"]:
        config["project"]["optional-dependencies"] = {}

    optional_deps = config["project"]["optional-dependencies"]

    # Add individual extras
    for pkg in packages:
        optional_deps[pkg["extra_name"]] = [pkg["name"]]

    # Update "all" extra
    all_packages = [pkg["name"] for pkg in packages]
    optional_deps["all"] = all_packages

    # Update tool.uv.sources
    if "tool" not in config:
        config["tool"] = {}
    if "uv" not in config["tool"]:
        config["tool"]["uv"] = {}
    if "sources" not in config["tool"]["uv"]:
        config["tool"]["uv"]["sources"] = {}

    sources = config["tool"]["uv"]["sources"]

    # Add workspace sources for all packages
    for pkg in packages:
        sources[pkg["name"]] = {"workspace": True}

    # Write updated config
    with open(north_config_path, "wb") as f:
        tomli_w.dump(config, f)

    print(f"✅ Updated {north_config_path}")
    print(f"📦 Found {len(packages)} packages:")
    for pkg in packages:
        print(f"   - {pkg['extra_name']}: {pkg['name']}")


def update_workspace_config(packages: List[Dict[str, str]]) -> None:
    """Update root pyproject.toml workspace members."""
    workspace_config_path = Path("pyproject.toml")

    if not workspace_config_path.exists():
        print(f"Warning: {workspace_config_path} does not exist")
        return

    # Read current config
    with open(workspace_config_path, "rb") as f:
        config = tomllib.load(f)

    # Update workspace members
    if "tool" not in config:
        config["tool"] = {}
    if "uv" not in config["tool"]:
        config["tool"]["uv"] = {}
    if "workspace" not in config["tool"]["uv"]:
        config["tool"]["uv"]["workspace"] = {}

    # Build members list
    members = ["packages/north"]  # Always include main north package
    for pkg in packages:
        members.append(f"packages/{Path(pkg['path']).name}")

    config["tool"]["uv"]["workspace"]["members"] = sorted(members)

    # Write updated config
    with open(workspace_config_path, "wb") as f:
        tomli_w.dump(config, f)

    print(f"✅ Updated {workspace_config_path} workspace members")


def main():
    """Main function."""
    print("🔍 Scanning packages directory...")
    packages = scan_packages()

    if not packages:
        print("❌ No packages found in packages/ directory")
        return

    print("\n📝 Updating configuration files...")
    update_north_config(packages)
    update_workspace_config(packages)

    print(f"\n🎉 Configuration updated! Found {len(packages)} packages:")
    print("   Available extras:")
    for pkg in packages:
        print(f"     north[{pkg['extra_name']}]  # {pkg['description']}")
    print("     north[all]                    # All packages")


if __name__ == "__main__":
    main()
