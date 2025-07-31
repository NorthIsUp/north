# North Configuration Scripts

## update_north_config.py

Automatically updates `packages/north/pyproject.toml` and the root `pyproject.toml` with all packages found in the `packages/` directory.

### What it does:

1. **Scans `packages/` directory** for all subdirectories (except `north`)
2. **Reads each package's `pyproject.toml`** to get package name and description
3. **Updates `packages/north/pyproject.toml`** with:
   - Individual extras: `north[string]`, `north[typeid]`, etc.
   - `all` extra containing all packages
   - Workspace source configurations
4. **Updates root `pyproject.toml`** with workspace member list

### Usage:

```bash
# Run the script directly
uv run python scripts/update_north_config.py

# Or use the wrapper script
./scripts/update-config.sh

# After running, sync to apply changes
uv sync
```

### Example Output:

```
🔍 Scanning packages directory...

📝 Updating configuration files...
✅ Updated packages/north/pyproject.toml
📦 Found 5 packages:
   - funcy: north-funcy
   - matchbox: north-matchbox
   - registry: north-registry
   - string: north-string
   - typeid: north-typeid
✅ Updated pyproject.toml workspace members

🎉 Configuration updated! Found 5 packages:
   Available extras:
     north[funcy]      # Functional utilities for the north namespace
     north[matchbox]   # Pattern matching and guards for the north namespace
     north[registry]   # Registry and autodiscovery utilities for the north namespace
     north[string]     # String utilities for the north namespace
     north[typeid]     # TypeId implementation for the north namespace
     north[all]        # All packages
```

### When to run:

- After adding a new package to `packages/`
- After changing package names or descriptions
- After modifying the workspace structure

### Requirements:

- `tomli-w` (already included in dev dependencies)

## Generated Configuration

The script generates configuration like this:

### packages/north/pyproject.toml
```toml
[project.optional-dependencies]
string = ["north-string"]
typeid = ["north-typeid"]
matchbox = ["north-matchbox"]
funcy = ["north-funcy"]
registry = ["north-registry"]
all = ["north-string", "north-typeid", "north-matchbox", "north-funcy", "north-registry"]

[tool.uv.sources]
north-string = { workspace = true }
north-typeid = { workspace = true }
# ... etc
```

### pyproject.toml (root)
```toml
[tool.uv.workspace]
members = [
    "packages/north",
    "packages/north-funcy",
    "packages/north-matchbox",
    "packages/north-registry",
    "packages/north-string",
    "packages/north-typeid",
]
```

This enables usage like:
```bash
uv add "north[string,typeid]"
uv add "north[all]"
```
