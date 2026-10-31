"""Pydantic model helpers and legacy CLI compatibility.

>>> from pydantic import BaseModel
>>> class Options(BaseModel, metaclass=Singleton):
...     count: int = 1
>>> Options() is Options()
True
>>> Options.new_instance(count=2).count
2
"""

from .singleton import Singleton

__all__ = ["Singleton"]
