#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "requests>=2.32.5", "rich>=14.1.0"
# ]
# ///
"""
Check if a package in dist directory already exists on PyPI by comparing checksums.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import requests


def calculate_sha256(filepath: Path) -> str:
    """Calculate the SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def normalize_package_name(name: str) -> str:
    """
    Normalize package name according to PEP 503.
    PyPI normalizes names by lowercasing and converting runs of separators to single hyphens.
    """
    import re

    return re.sub(r"[-_.]+", "-", name).lower()


def get_pypi_checksums(package_name: str) -> dict[str, dict[str, str]]:
    """
    Retrieve checksums for all versions of a package from PyPI.
    Returns dict mapping version -> {filename: checksum}
    """
    normalized_name = normalize_package_name(package_name)
    url = f"https://pypi.org/pypi/{normalized_name}/json"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Failed to fetch data for '{package_name}' from PyPI: {e}")
        return {}

    try:
        data = response.json()
        checksums = {}

        for version, files in data["releases"].items():
            version_checksums = {}
            for file_info in files:
                filename = file_info["filename"]
                sha256_hash = file_info["digests"]["sha256"]
                version_checksums[filename] = sha256_hash

            if version_checksums:  # Only include versions with files
                checksums[version] = version_checksums

        return checksums

    except (KeyError, json.JSONDecodeError) as e:
        print(f"Unexpected data format for '{package_name}': {e}")
        return {}


def find_package_files(package_name: str, dist_dir: Path) -> list[Path]:
    """Find all package files for the given package in dist directory."""
    # Convert package name to the format used in filenames (replace - with _)
    file_package_name = package_name.replace("-", "_")

    patterns = [f"{file_package_name}-*.whl", f"{file_package_name}-*.tar.gz"]

    files = []
    for pattern in patterns:
        files.extend(dist_dir.glob(pattern))

    return sorted(files)


def check_package_exists_on_pypi(package_name: str, dist_dir: Path) -> bool:
    """
    Check if any package files in dist directory already exist on PyPI.
    Returns True if any file already exists, False otherwise.
    """
    print(
        f"Checking if '{package_name}' files in dist are already published on PyPI..."
    )

    # Find local package files
    local_files = find_package_files(package_name, dist_dir)
    if not local_files:
        print(f"No package files found for '{package_name}' in '{dist_dir}'")
        return False

    print(f"Found {len(local_files)} local files:")
    for file_path in local_files:
        print(f"  - {file_path.name}")

    # Get PyPI checksums
    pypi_checksums = get_pypi_checksums(package_name)
    if not pypi_checksums:
        print(f"No PyPI data found for '{package_name}' - assuming it's a new package")
        return False

    print(f"Found {len(pypi_checksums)} versions on PyPI")

    # Check each local file against PyPI
    files_exist_on_pypi = []

    for local_file in local_files:
        local_checksum = calculate_sha256(local_file)
        filename = local_file.name

        # Check all PyPI versions for this filename
        found_on_pypi = False
        for version, version_files in pypi_checksums.items():
            if filename in version_files:
                pypi_checksum = version_files[filename]
                if local_checksum == pypi_checksum:
                    print(f"  ✓ {filename} already exists on PyPI (version {version})")
                    found_on_pypi = True
                    files_exist_on_pypi.append(filename)
                    break

        if not found_on_pypi:
            print(f"  - {filename} is new (not found on PyPI)")

    if files_exist_on_pypi:
        print(f"\n⚠️  {len(files_exist_on_pypi)} file(s) already exist on PyPI:")
        for filename in files_exist_on_pypi:
            print(f"     {filename}")
        return True
    else:
        print("\n✅ All files are new - safe to publish")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Check if package files in dist directory already exist on PyPI"
    )
    parser.add_argument(
        "package_name", help="Name of the package to check (e.g., 'we-love-string')"
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=Path("dist"),
        help="Path to dist directory (default: ./dist)",
    )
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit with code 1 if package already exists on PyPI",
    )

    args = parser.parse_args()

    if not args.dist_dir.exists():
        print(f"Dist directory '{args.dist_dir}' does not exist")
        sys.exit(1)

    exists = check_package_exists_on_pypi(args.package_name, args.dist_dir)

    if args.exit_code and exists:
        sys.exit(1)


if __name__ == "__main__":
    main()
