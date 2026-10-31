"""Typed TOML models with workspace editing.

>>> model = UvWorkspacePyProjectToml()
>>> model.add_workspace_member("packages/example")
>>> model.get_workspace_members()
['packages/example']
>>> Project(name="example", version="1.0.0").model_dump_toml()["name"]
'example'
"""

from .models import BuildSystem, DependencyGroup, DependencyInclude, Project, PyProjectToml, Tool, UvSource, UvWorkspacePyProjectToml

__all__ = [
    "BuildSystem",
    "DependencyGroup",
    "DependencyInclude",
    "Project",
    "PyProjectToml",
    "Tool",
    "UvSource",
    "UvWorkspacePyProjectToml",
]
