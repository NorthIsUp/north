from __future__ import annotations

import logging
import sys
from datetime import timedelta
from typing import Annotated, Self, override

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .arguments import LOGGING_GROUP, BaseSettings, CliFlag, CliImplicitFlag, CliVerbosity, Group
from .debugging import DebugSettings

logger = logging.getLogger(__name__)


# Supports the inherited settings pattern that we are using in the coding agent
class _GlobalSettingsStore:
    """Store the active CLI settings"""

    _settings: GlobalSettings | None = None

    def set(self, settings: GlobalSettings) -> None:
        self._settings = settings

    def get(self) -> GlobalSettings:
        if self._settings is None:
            raise LookupError("Global settings not initialized. Call settings.set() first.")
        return self._settings

    def clear(self) -> None:
        self._settings = None


class LoggingSettings(BaseSettings):
    """global logging settings, access via coding_agent.appconfig.settings"""

    verbosity: Annotated[CliVerbosity, LOGGING_GROUP] = None

    litellm_debug: Annotated[CliFlag[bool], LOGGING_GROUP] = Field(
        default=False,
        description="Enable debug logging for litellm library",
    )
    conversation_debug: Annotated[CliFlag[bool], LOGGING_GROUP] = Field(
        default=False,
        description="Enable debug logging for conversation flows",
    )
    agent_streaming_debug: Annotated[CliFlag[bool], LOGGING_GROUP] = Field(
        default=False,
        description="Enable debug logging for agent streaming",
    )
    interactive_terminal: Annotated[CliImplicitFlag[bool], LOGGING_GROUP] = Field(
        default=sys.stdout.isatty(),
        description="Enable interactive terminal mode (default: True if stdout is a terminal)",
    )

    @field_validator("verbosity", mode="before")
    @classmethod
    def validate_verbosity(cls, v: object) -> int:
        """Handle -v, -vv, -vvv style flags"""
        match v:
            case None:
                verbosity = 2
            case str() as v if v.isdigit():
                verbosity = int(v)
            case int() as v:
                verbosity = v
            case _:
                raise ValueError(f"Verbosity must be an integer, got {v!r}")

        if verbosity > 5:
            raise ValueError("Verbosity cannot be greater than 5")

        if verbosity < 0:
            raise ValueError("Verbosity cannot be less than 0")

        return verbosity

    @model_validator(mode="after")
    def validate_logging(self) -> Self:
        """done as a validator to ensure the settings are changed any time the settings are changed"""

        assert self.verbosity is not None

        self.configure_logging()

        return self

    def configure_logging(self) -> None:
        assert self.verbosity is not None
        level = max(logging.DEBUG, logging.WARNING - 10 * (self.verbosity - 1))
        logging.basicConfig(level=level)
        logging.getLogger().setLevel(level)
        for name, enabled in (
            ("litellm", self.litellm_debug),
            ("coding_agent.conversation", self.conversation_debug),
            ("coding_agent.streaming", self.agent_streaming_debug),
        ):
            logging.getLogger(name).setLevel(logging.DEBUG if enabled else level)


_group = Group("cache")


class CacheSettings(BaseSettings):
    litellm_cache: Annotated[bool, _group] = Field(
        default=False,
        description="Use the litellm cache to store and retrieve responses from the cache before sending requests to the Model API.",
    )
    litellm_cache_ttl: Annotated[int, _group] = Field(
        default=int(timedelta(hours=6).total_seconds()),
        ge=0,
        description="The time to live for the litellm cache.",
    )
    litellm_cache_namespace: Annotated[str, _group] = Field(
        default="coding_agent",
        description="The namespace for the litellm cache.",
    )
    litellm_cache_s_maxage: Annotated[int, _group] | None = Field(
        default=None,
        ge=0,
        description="do not use cached items older than this age",
    )
    litellm_cache_no_cache: Annotated[bool, _group] | None = Field(
        default=None,
        description="Do not cache the litellm response.",
    )
    litellm_cache_no_store: Annotated[bool, _group] | None = Field(
        default=None,
        description="Do not store the litellm response.",
    )


class GlobalSettings(LoggingSettings, CacheSettings, DebugSettings):
    """global settings, access via coding_agent.appconfig.settings"""

    model_config = ConfigDict(
        frozen=True,
        validate_assignment=True,
        validate_default=True,
    )

    @override
    def model_post_init(self, context: object) -> None:
        """
        set the global settings in thread-safe storage
        """
        super().model_post_init(context)

        logger.info("setting the global settings to %s", self.__class__.__name__)
        settings.set(self)

    def cast_to[T: BaseModel](self, cls: type[T]) -> T:
        """
        cast the settings to a given settings class, will raise a ValueError if
        the settings are not of the given class
        """
        if isinstance(self, cls):
            return self
        raise ValueError(f"cannot cast '{self.__class__.__name__} ({id(self.__class__)})' to '{cls.__name__} ({id(cls)})'")


settings = _GlobalSettingsStore()
