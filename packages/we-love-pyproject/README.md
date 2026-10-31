# we-love-pyproject

Typed TOML models with workspace editing.

Install with `uv add we-love-pyproject`. Requires Python 3.13+.

## Executable example

```pycon
>>> model = UvWorkspacePyProjectToml()
>>> model.add_workspace_member("packages/example")
>>> model.get_workspace_members()
['packages/example']
>>> Project(name="example", version="1.0.0").model_dump_toml()["name"]
'example'
```

`PyProjectToml.from_file` loads a file and `write` serializes it. Unknown tool sections and fields survive model validation; formatting/comments are not preserved by a model round trip. UvWorkspacePyProjectToml edits members and sources. Standard string pytest options, marker strings, dependency include-group entries, and Ruff sections without target-version are supported. Generated upstream schemas remain importable submodules.

Examples run in ordinary pytest discovery through `examples_test.py`. The distribution ships a `py.typed` marker.
