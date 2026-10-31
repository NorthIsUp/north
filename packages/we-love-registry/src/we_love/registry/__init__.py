"""Typed model and class registration with explicit discovery.

>>> class Example(RegisterableModel):
...     pass
>>> registry = Registry()
>>> entry = Example(name="demo")
>>> registry.register(entry)
>>> registry["demo"] is entry
True
>>> [item.name for item in registry.enabled() if isinstance(item, RegisterableModel)]
['demo']
"""

from .autodiscover import autodiscover, autodiscover_iter
from .registerable import RegisterableBase, RegisterableModel, RegisterableType, Registry

__all__ = [
    "RegisterableBase",
    "RegisterableModel",
    "RegisterableType",
    "Registry",
    "autodiscover",
    "autodiscover_iter",
]
