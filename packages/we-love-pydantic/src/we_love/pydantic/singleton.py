from __future__ import annotations

from typing import ClassVar, override

from pydantic._internal._model_construction import ModelMetaclass


class Singleton(ModelMetaclass):
    """Cache model instances while exposing fresh construction for tests."""

    _instances: ClassVar[dict[Singleton, object]] = {}

    @override
    def __call__(self, *args: object, **kwargs: object) -> object:
        if self not in self._instances:
            self._instances[self] = self.new_instance(*args, **kwargs)
        return self._instances[self]

    def new_instance(self, *args: object, **kwargs: object) -> object:
        value: object = super().__call__(*args, **kwargs)
        return value
