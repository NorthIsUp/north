"""
Test suite to verify that all north packages can be installed and imported correctly using uv run.
This is the recommended way to test package installation and imports.
"""

import subprocess
import tomllib
from dataclasses import dataclass
from inspect import cleandoc
from pathlib import Path

import pytest


@dataclass
class Package:
    package_name: str
    module_name: str
    description: str

    @property
    def is_main(self) -> bool:
        return self.package_name == "north"


def discover_packages() -> list[Package]:
    """Discover all north packages by reading pyproject.toml files."""
    packages_dir = Path(__file__).parent.parent
    packages = []

    # Find all pyproject.toml files in the packages directory
    for pyproject_file in packages_dir.glob("*/pyproject.toml"):
        try:
            with open(pyproject_file, "rb") as f:
                config = tomllib.load(f)

            # Extract package information
            project_name = config.get("project", {}).get("name", "")
            description = config.get("project", {}).get("description", "No description")

            # Skip if not a north package
            if not project_name.startswith("north"):
                continue

            # Determine the module name
            if project_name == "north":
                # Main north package
                module_name = "north"
                package_name = "north"
            else:
                # Namespace packages (e.g., north-string -> north.string)
                package_name = project_name
                module_name = project_name.replace("-", ".")

            packages.append(
                Package(
                    package_name=package_name,
                    module_name=module_name,
                    description=description,
                )
            )

        except Exception as e:
            print(f"Warning: Could not parse {pyproject_file}: {e}")
            continue

    # Sort packages: main north package first, then others alphabetically
    packages.sort(key=lambda p: (not p.is_main, p.package_name))
    return packages


def get_namespace_packages() -> list[Package]:
    """Get only the namespace packages (excluding main north package)."""
    all_packages = discover_packages()
    return [pkg for pkg in all_packages if not pkg.is_main]


def get_all_package_names() -> list[str]:
    """Get all package names for uv run commands."""
    return [pkg.package_name for pkg in discover_packages()]


def get_all_module_imports() -> list[str]:
    """Get all module import statements for testing."""
    all_packages = discover_packages()
    imports = []
    for pkg in all_packages:
        if pkg.is_main:
            imports.append(f"import {pkg.module_name}")
        else:
            imports.append(f"import {pkg.module_name}")
    return imports


def run_uv_test(
    packages: list[str], import_statement: str, description: str
) -> tuple[bool, str]:
    """Test importing packages using uv run."""
    # Build the uv run command
    cmd = ["uv", "run", "--no-project"]
    for package in packages:
        cmd.extend(["--with", package])
    cmd.extend(["--", "python", "-c", import_statement])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr


class TestNorthPackageImports:
    """Test class for north package imports using uv run."""

    @pytest.fixture(scope="class")
    def discovered_packages(self) -> list[Package]:
        """Discover all packages at test class initialization."""
        return discover_packages()

    @pytest.fixture(scope="class")
    def namespace_packages(self) -> list[Package]:
        """Get namespace packages at test class initialization."""
        return get_namespace_packages()

    def test_main_north_package_import(
        self, discovered_packages: list[Package]
    ) -> None:
        """Test that the main north package can be imported."""
        main_package = next((pkg for pkg in discovered_packages if pkg.is_main), None)
        assert main_package is not None, "Main north package not found"

        success, output = run_uv_test(
            [main_package.package_name],
            f"import {main_package.module_name}; print('{main_package.module_name} imported successfully')",
            "Main north package import",
        )
        assert success, f"Failed to import main north package: {output}"
        assert f"{main_package.module_name} imported successfully" in output

    @pytest.mark.parametrize(
        "package_info",
        [pytest.param(pkg, id=pkg.package_name) for pkg in get_namespace_packages()],
    )
    def test_namespace_package_imports(self, package_info: Package) -> None:
        """Test that individual namespace packages can be imported."""
        success, output = run_uv_test(
            ["north", package_info.package_name],
            f"import {package_info.module_name}; print('{package_info.module_name} imported successfully')",
            f"{package_info.description} ({package_info.module_name})",
        )
        assert success, f"Failed to import {package_info.module_name}: {output}"
        assert f"{package_info.module_name} imported successfully" in output

    def test_multiple_packages_together(
        self, discovered_packages: list[Package]
    ) -> None:
        """Test that multiple namespace packages can be imported together."""
        # Get first few namespace packages for testing
        namespace_packages = [pkg for pkg in discovered_packages if not pkg.is_main][:3]
        if not namespace_packages:
            pytest.skip("No namespace packages found")

        package_names = ["north"] + [pkg.package_name for pkg in namespace_packages]

        # Create import statements for the selected packages
        import_statements = []
        for pkg in namespace_packages:
            if pkg.module_name == "north.string":
                import_statements.append("import north.string.case")
            elif pkg.module_name == "north.typeid":
                import_statements.append("import north.typeid.typeid")
            elif pkg.module_name == "north.matchbox":
                import_statements.append("import north.matchbox.guards")
            else:
                import_statements.append(f"import {pkg.module_name}")

        import_code = (
            "\n".join(import_statements)
            + "\nprint('Multiple namespace packages imported successfully')"
        )

        success, output = run_uv_test(
            package_names,
            import_code,
            "Multiple namespace packages together",
        )
        assert success, f"Failed to import multiple packages: {output}"
        assert "Multiple namespace packages imported successfully" in output

    def test_functionality_test(self, discovered_packages: list[Package]) -> None:
        """Test that package functionality works correctly."""
        # Find north-string package for functionality testing
        string_package = next(
            (pkg for pkg in discovered_packages if pkg.package_name == "north-string"),
            None,
        )
        if not string_package:
            pytest.skip("north-string package not found")

        success, output = run_uv_test(
            ["north", string_package.package_name],
            cleandoc("""
            import north.string.case
            result = north.string.case.snakecase('HelloWorld')
            print(f'Function test: snakecase result: {result}')
            """),
            "Functionality test (north.string.case)",
        )
        assert success, f"Failed functionality test: {output}"
        assert "Function test: snakecase result: _hello_world" in output

    def test_all_packages_together(self, discovered_packages: list[Package]) -> None:
        """Test that all packages can be imported together."""
        all_package_names = [pkg.package_name for pkg in discovered_packages]

        # Create import statements for all packages
        import_statements = []
        for pkg in discovered_packages:
            import_statements.append(f"import {pkg.module_name}")

        import_code = (
            "\n".join(import_statements)
            + "\nprint('All packages imported successfully')"
        )

        success, output = run_uv_test(
            all_package_names,
            import_code,
            "All packages together",
        )
        assert success, f"Failed to import all packages: {output}"
        assert "All packages imported successfully" in output

    def test_package_discovery(self) -> None:
        """Test that package discovery works correctly."""
        packages = discover_packages()

        # Should have at least the main north package
        assert len(packages) > 0, "No packages discovered"

        # Should have exactly one main package
        main_packages = [pkg for pkg in packages if pkg.is_main]
        assert len(main_packages) == 1, (
            f"Expected 1 main package, found {len(main_packages)}"
        )
        assert main_packages[0].package_name == "north", (
            "Main package should be 'north'"
        )

        # Should have namespace packages
        namespace_packages = [pkg for pkg in packages if not pkg.is_main]
        assert len(namespace_packages) > 0, "No namespace packages discovered"

        # All packages should have required fields
        for pkg in packages:
            assert pkg.package_name is not None, f"Package missing package_name: {pkg}"
            assert pkg.module_name is not None, f"Package missing module_name: {pkg}"
            assert pkg.description is not None, f"Package missing description: {pkg}"
            assert pkg.is_main is not None, f"Package missing is_main: {pkg}"

            # Package names should start with 'north'
            assert pkg.package_name.startswith("north"), (
                f"Package name should start with 'north': {pkg['package_name']}"
            )

            # Module names should be valid Python identifiers
            assert pkg.module_name.replace(".", "_").replace("-", "_").isidentifier(), (
                f"Invalid module name: {pkg['module_name']}"
            )

        print(
            f"✅ Discovered {len(packages)} packages: {[pkg.package_name for pkg in packages]}"
        )
