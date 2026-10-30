from __future__ import annotations

import logging
import sys
import types
from collections.abc import Callable
from pdb import post_mortem
from types import TracebackType
from typing import Annotated, override

from pydantic import Field, PrivateAttr, ValidationError
from rich import console
from rich.panel import Panel
from rich.pretty import pretty_repr

from .arguments import BaseSettings, CliImplicitFlag, Group

try:
    import debugpy
except ImportError:
    debugpy = None

logger = logging.getLogger(__name__)
DEBUG_GROUP = Group("debug")


class DebugSettings(BaseSettings):
    pdb: Annotated[CliImplicitFlag[bool], DEBUG_GROUP] = Field(
        default=False,
        description="Enable Python debugger post-mortem on exceptions",
    )
    pydantic_detailed_output: Annotated[CliImplicitFlag[bool], DEBUG_GROUP] = Field(
        default=True,
        description="Enable detailed output for pydantic validation errors",
    )

    debugpy: Annotated[CliImplicitFlag[bool], DEBUG_GROUP] = Field(
        default=False,
        description="Enable vscode debugger on exceptions",
    )
    debugpy_port: Annotated[int, DEBUG_GROUP] = Field(
        default=5678,
        description="The port to listen for remote debugger connections",
    )

    _excepthooks: list[Callable[[type[BaseException], BaseException, types.TracebackType | None], None]] = PrivateAttr(
        default_factory=list[Callable[[type[BaseException], BaseException, types.TracebackType | None], None]]
    )

    @override
    def model_post_init(self, context: object) -> None:
        super().model_post_init(context)
        if self.pydantic_detailed_output:
            self.enable_pydantic_detailed_output_excepthook()
        if self.pdb:
            self.enable_postmortem()
        if self.debugpy:
            self.enable_debugpy()

    def add_excepthook(
        self,
        hook: Callable[[type[BaseException], BaseException, types.TracebackType | None], None],
        exec_type: type[BaseException] | tuple[type[BaseException], ...] | None = None,
    ) -> None:
        """add an excepthook for pydantic validation errors"""

        self._excepthooks.append(hook)
        sys.excepthook = self._excepthook

    def _excepthook(self, exc_type: type[BaseException], exc: BaseException, tb: types.TracebackType | None) -> None:
        for hook in self._excepthooks:
            hook(exc_type, exc, tb)

    def enable_pydantic_detailed_output_excepthook(self) -> None:
        """Enable pydantic detailed output on exceptions"""

        def _pydantic_detailed_output_excepthook(exc_type: type[BaseException], exc: BaseException, tb: types.TracebackType | None) -> None:
            if isinstance(exc, ValidationError):
                payload = exc.errors(include_url=True)
                sys.stderr.write(pretty_repr(payload))
                sys.stderr.write("\n")
                sys.stderr.flush()

        self.add_excepthook(_pydantic_detailed_output_excepthook)

    def enable_postmortem(self) -> None:
        """Enable post-mortem debugging on exceptions"""

        def _enter_post_mortem(exc_type: type[BaseException], value: BaseException, traceback: TracebackType | None) -> None:

            post_mortem(traceback)

        self.add_excepthook(_enter_post_mortem)

        sys.excepthook = _enter_post_mortem

    def enable_debugpy(self) -> None:
        """Enable vscode debugger on exceptions"""

        if debugpy is None:
            raise RuntimeError("Install we-love-cli[debug] to enable debugpy")
        debugpy.listen(("127.0.0.1", self.debugpy_port))

        console.Console().print(Panel(f"Waiting for vscode debugger to attach on port {self.debugpy_port}"))

        logger.info("Waiting for vscode debugger to attach")
        debugpy.wait_for_client()
        logger.info("vscode debugger attached")
