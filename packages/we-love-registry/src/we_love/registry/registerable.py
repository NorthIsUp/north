from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, ClassVar, override

from pydantic import BaseModel, Field
from we_love.string import to_snake

from .autodiscover import autodiscover

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

type RegisterableTypes = RegisterableModel | type[RegisterableType]
type RegisterableTypesList = list[RegisterableTypes]
type RegisterableTypesDict = dict[str, RegisterableTypes]


class RegistryConfig(BaseModel):
    """Registry for experiment configurations."""

    autodiscovery_module: str | list[str] | tuple[str, ...] = ()
    autodiscovery_run: bool = False

    # name transformers
    to_snake_case: bool = False
    to_lower: bool = False
    to_upper: bool = False

    registry: RegisterableTypesDict = Field(default_factory=dict[str, RegisterableTypes])


class Registry:
    """A typed collection with validated configuration."""

    def __init__(
        self,
        autodiscovery_module: str | list[str] | tuple[str, ...] = (),
        autodiscovery_run: bool = False,
        to_snake_case: bool = False,
        to_lower: bool = False,
        to_upper: bool = False,
        registry: RegisterableTypesDict | None = None,
    ) -> None:
        self.config = RegistryConfig(
            autodiscovery_module=autodiscovery_module,
            autodiscovery_run=autodiscovery_run,
            to_snake_case=to_snake_case,
            to_lower=to_lower,
            to_upper=to_upper,
            registry={} if registry is None else registry,
        )

    @property
    def autodiscovery_module(self) -> str | list[str] | tuple[str, ...]:
        return self.config.autodiscovery_module

    @autodiscovery_module.setter
    def autodiscovery_module(self, value: str | list[str] | tuple[str, ...]) -> None:
        self.config.autodiscovery_module = value

    @property
    def autodiscovery_run(self) -> bool:
        return self.config.autodiscovery_run

    @autodiscovery_run.setter
    def autodiscovery_run(self, value: bool) -> None:
        self.config.autodiscovery_run = value

    @property
    def to_snake_case(self) -> bool:
        return self.config.to_snake_case

    @to_snake_case.setter
    def to_snake_case(self, value: bool) -> None:
        self.config.to_snake_case = value

    @property
    def to_lower(self) -> bool:
        return self.config.to_lower

    @to_lower.setter
    def to_lower(self, value: bool) -> None:
        self.config.to_lower = value

    @property
    def to_upper(self) -> bool:
        return self.config.to_upper

    @to_upper.setter
    def to_upper(self, value: bool) -> None:
        self.config.to_upper = value

    @property
    def registry(self) -> RegisterableTypesDict:
        return self.config.registry

    @registry.setter
    def registry(self, value: RegisterableTypesDict) -> None:
        self.config.registry = value

    @cached_property
    def discovered(self) -> RegisterableTypesDict:
        self.autodiscover()
        return self.registry

    def __getitem__(self, name: str) -> RegisterableTypes:
        return self.discovered[name]

    def __iter__(self) -> Iterator[RegisterableTypes]:
        return iter(self.all())

    def autodiscover(
        self,
        *extra_packages: str,
        submodules: bool = True,
        force: bool = False,
    ) -> RegisterableTypesList:
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
            case type() as model_type:
                name = model_type.__name__
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
        values = list(self.registry.values())
        values.sort(key=lambda exp: exp.__name__ if isinstance(exp, type) else exp.name)
        return values

    def all(self) -> RegisterableTypesList:
        """Get all registered experiments."""
        return self.autodiscover()

    def enabled(self) -> RegisterableTypesList:
        """Get all enabled experiments."""
        return [exp for exp in self.all() if exp.enabled]


class RegisterableBase(BaseModel):
    _registry: ClassVar[Registry]
    _autodiscovery_module: ClassVar[str | tuple[str, ...]] = ()

    @classmethod
    def registry(cls) -> Registry:
        if not hasattr(cls, "_registry"):
            extra_discovery_modules = getattr(cls, "_autodiscovery_module", ())
            logger.debug("  -->creating registry for '%s' with extra_discovery_modules: '%s'", cls.__name__, extra_discovery_modules)
            cls._registry = Registry(autodiscovery_module=extra_discovery_modules)

        return cls._registry


class RegisterableType(RegisterableBase):
    enabled: ClassVar[bool] = True

    def __init_subclass__(cls, **kwargs: object) -> None:
        logger.debug("====>initializing subclass %s", cls.__name__)
        cls.registry().register(cls)
        super().__init_subclass__()


class RegisterableModel(RegisterableBase):
    name: str
    enabled: bool = True

    def __init_subclass__(cls, **kwargs: object) -> None:
        logger.debug("====>initializing subclass %s", cls.__name__)
        cls.registry()  # create the registry if it doesn't exist

        super().__init_subclass__()

    @override
    def model_post_init(self, __context: object) -> None:
        super().model_post_init(__context)

        if self.name:
            logger.debug("Registering %s %s", self.__class__.__name__, self.name)
            self.registry().register(self)
        else:
            # this is a mystery, `CodingSteps`s are creating a phantom
            # `BaseModelConfig` instance when no default is provided even tho
            # the default is `None`
            logger.debug("Skipping registration of %s since it has no name.", self.__class__.__name__)
