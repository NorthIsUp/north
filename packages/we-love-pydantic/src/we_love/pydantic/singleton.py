from __future__ import annotations

import logging
from typing import Any, ClassVar, cast

from pydantic._internal._model_construction import ModelMetaclass

logger = logging.getLogger(__name__)


class Singleton[T: Singleton](ModelMetaclass, type):
    _instances: ClassVar[dict[type[Singleton[T]], Singleton[T]]] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> T:
        """
        "usual" way of creating a new class instance.

        We override this to make sure we always return the same instance, if you
        truly need a new instance use the new_instance() method
        """
        cls = cast(type[Singleton[T]], cls)
        if cls not in cls._instances:
            cls._instances[cls] = cls.new_instance(*args, **kwargs)
        return cast(T, cls._instances[cls])

    def new_instance(cls, *args: Any, **kwargs: Any) -> T:
        """
        Create a new instance of the singleton.

        This is useful for testing.
        """
        return super().__call__(*args, **kwargs)
