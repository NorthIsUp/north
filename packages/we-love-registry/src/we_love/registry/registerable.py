from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, cast

from pydantic import BaseModel, Field, PrivateAttr
from we_love.string import to_snake

from .autodiscover import autodiscover

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

RegisterableTypes = TypeVar(
    "RegisterableTypes", "RegisterableModel", type["RegisterableType"]
)
RegisterableTypesList = list[RegisterableTypes]
RegisterableTypesDict = dict[str, RegisterableTypes]


class Registry(BaseModel):
    """Registry for experiment configurations."""

    autodiscovery_module: str | list[str] | tuple[str, ...] = ()
    autodiscovery_run: bool = False

    # name transformers
    to_snake_case: bool = False
    to_lower: bool = False
    to_upper: bool = False

    registry: RegisterableTypesDict = Field(default_factory=dict)

    @cached_property
    def discovered(self) -> RegisterableTypesDict:
        self.autodiscover()
        return cast(RegisterableTypesDict, self.registry)

    def __getitem__(self, name: str) -> RegisterableTypes:
        return cast(RegisterableTypes, self.discovered[name])

    def __iter__(self) -> Iterator[RegisterableTypes]:
        return iter(self.all())

    def autodiscover(
        self,
        *extra_packages: str,
        submodules: bool = True,
        force: bool = False,
    ) -> list[RegisterableModel]:
        """
        Automatically discover and import all modules for registration.
        """
        if not self.autodiscovery_run or force:
            self.autodiscovery_run = True

            autodiscovery_module = self.autodiscovery_module
            if isinstance(autodiscovery_module, str):
                autodiscovery_module = [autodiscovery_module]
            assert [
                *autodiscovery_module,
                *extra_packages,
            ], "no autodiscovery modules provided"
            autodiscover([*autodiscovery_module, *extra_packages], recursive=submodules)

        return self.all_raw()

    def register(self, obj: RegisterableTypes) -> None:
        """Register an experiment instance."""
        match obj:
            case type(__name__=name):
                ...
            case RegisterableModel(name=name):
                ...
            case _:
                raise ValueError(f"Invalid object: {obj}")

        if self.to_snake_case:
            name = to_snake(name)
        if self.to_lower:
            name = name.lower()
        if self.to_upper:
            name = name.upper()

        self.registry[name] = obj

    def get(self, name: str) -> RegisterableTypes | None:
        """Get an experiment by name."""
        return self.discovered.get(name)

    def items(self) -> RegisterableTypesDict:
        """Get all registered experiments."""
        return self.discovered.copy()

    def all_raw(self) -> RegisterableTypesList:
        """Get all registered experiments."""
        values = cast(list[RegisterableModel], list(self.registry.values()))
        values.sort(key=lambda exp: exp.name)
        return values

    def all(self) -> RegisterableTypesList:
        """Get all registered experiments."""
        return self.autodiscover()

    def enabled(self) -> RegisterableTypesList:
        """Get all enabled experiments."""
        enabled = [exp for exp in self.all() if exp.enabled]
        return cast(RegisterableTypesList, enabled)


class RegisterableBase(BaseModel):
    _registry: ClassVar[Registry] = PrivateAttr()
    _autodiscovery_module: ClassVar[str | tuple[str, ...]] = PrivateAttr(default=())

    @classmethod
    def registry(cls) -> Registry:
        if not hasattr(cls, "_registry"):
            extra_discovery_modules = getattr(cls, "_autodiscovery_module", ())
            logger.debug(
                f"  -->creating registry for '{cls.__name__}' with extra_discovery_modules: '{extra_discovery_modules}'"
            )
            cls._registry = Registry(autodiscovery_module=extra_discovery_modules)

        return cls._registry


class RegisterableType(RegisterableBase):
    enabled: ClassVar[bool] = True

    def __init_subclass__(cls, **kwargs: Any) -> None:
        logger.debug(f"====>initializing subclass {cls.__name__}")
        cls.registry().register(cls)
        super().__init_subclass__(**kwargs)


class RegisterableModel(RegisterableBase):
    name: str
    enabled: bool = True

    def __init_subclass__(cls, **kwargs: Any) -> None:
        logger.debug(f"====>initializing subclass {cls.__name__}")
        cls.registry()  # create the registry if it doesn't exist

        super().__init_subclass__(**kwargs)

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)

        if self.name:
            logger.debug(f"Registering {self.__class__.__name__} {self.name}")
            self.registry().register(self)
        else:
            # this is a mystery, `CodingSteps`s are creating a phantom
            # `BaseModelConfig` instance when no default is provided even tho
            # the default is `None`
            logger.debug(
                f"Skipping registration of {self.__class__.__name__} since it has no name."
            )
