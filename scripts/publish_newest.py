#!/usr/bin/env python3
"""
Publish only the newest version of a package from the dist directory.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

from packaging.version import Version


def find_newest_package_files(package_name: str, dist_dir: Path) -> list[Path]:
    """
    Find the newest version files for a given package in the dist directory.
    Returns paths to both .whl and .tar.gz files for the newest version.
    """
    # Convert package name to the format used in filenames (replace - with _)
    file_package_name = package_name.replace("-", "_")

    # Find all files for this package
    patterns = [f"{file_package_name}-*.whl", f"{file_package_name}-*.tar.gz"]

    all_files = []
    for pattern in patterns:
        all_files.extend(dist_dir.glob(pattern))

    if not all_files:
        print(f"No package files found for '{package_name}' in '{dist_dir}'")
        return []

    # Group files by version
    version_files = {}
    # Pattern to match both wheel and tar.gz files
    wheel_pattern = re.compile(rf"{re.escape(file_package_name)}-([^-]+)-.*\.whl$")
    tarball_pattern = re.compile(rf"{re.escape(file_package_name)}-([^-]+)\.tar\.gz$")

    for file_path in all_files:
        # Try both patterns
        match = wheel_pattern.match(file_path.name) or tarball_pattern.match(
            file_path.name
        )
        if match:
            version_str = match.group(1)
            try:
                version = Version(version_str)
                if version not in version_files:
                    version_files[version] = []
                version_files[version].append(file_path)
            except Exception as e:
                print(
                    f"Warning: Could not parse version '{version_str}' from {file_path.name}: {e}"
                )

    if not version_files:
        print(f"No valid version files found for '{package_name}'")
        return []

    # Find the newest version
    newest_version = max(version_files.keys())
    newest_files = version_files[newest_version]

    print(f"Found {len(version_files)} version(s) for '{package_name}'")
    print(f"Newest version: {newest_version}")
    print("Files to publish:")
    for file_path in sorted(newest_files):
        print(f"  - {file_path.name}")

    return sorted(newest_files)


def publish_files(file_paths: list[Path], dry_run: bool = False) -> bool:
    """
    Publish the given files using uv publish.
    Returns True if successful, False otherwise.
    """
    if not file_paths:
        print("No files to publish")
        return False

    cmd = ["uv", "publish"] + [str(path) for path in file_paths]

    if dry_run:
        print(f"Dry run - would execute: {' '.join(cmd)}")
        return True

    try:
        print(f"Publishing {len(file_paths)} file(s)...")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Successfully published!")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Publishing failed with exit code {e.returncode}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Publish only the newest version of a package from dist directory"
    )
    parser.add_argument(
        "package_name", help="Name of the package to publish (e.g., 'we-love-string')"
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=Path("dist"),
        help="Path to dist directory (default: ./dist)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be published without actually publishing",
    )

    args = parser.parse_args()

    if not args.dist_dir.exists():
        print(f"Dist directory '{args.dist_dir}' does not exist")
        sys.exit(1)

    newest_files = find_newest_package_files(args.package_name, args.dist_dir)

    if not newest_files:
        sys.exit(1)

    success = publish_files(newest_files, dry_run=args.dry_run)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
