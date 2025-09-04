from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal, TypeVar, overload

logger = logging.getLogger(__name__)

T = TypeVar("T")


_FmtT = Callable[[T], str]


@overload
def fzf_select[T](
    items: list[T],
    prompt: str = ...,
    format_fn: _FmtT = ...,
    height: int = ...,
    width: int = ...,
    many: Literal[False] = False,
    header: str | None = None,
) -> T | None: ...


@overload
def fzf_select[T](
    items: list[T],
    prompt: str = ...,
    format_fn: _FmtT = ...,
    height: int = ...,
    width: int = ...,
    *,
    many: bool = ...,
    header: str | None = None,
) -> list[T] | None: ...


def fzf_select[T](
    items: list[T],
    prompt: str = "Select an item: ",
    format_fn: _FmtT = str,
    height: int = 40,
    width: int = 100,
    many: bool = False,
    header: str | None = None,
) -> T | list[T] | None:
    """Select an item from a list using fzf.

    Args:
        items: List of items to select from
        format_fn: Function to format items for display. Defaults to str.
        height: Height of the fzf window. Defaults to 40.
        width: Width of the fzf window. Defaults to 100.
        many: Whether to allow multiple selections. Defaults to False.

    Returns:
        The selected item(s) or None if no selection was made
    """
    try:
        import fzf

        kwargs = {}
        if header:
            kwargs["header"] = header

        return fzf.fzf_prompt(
            items,
            prompt_string=prompt,
            multi=many,
            processor=format_fn,
            ansi=True,
            escape_output=False,
            **kwargs,
        )

    except RuntimeError:  # could not find fzf
        from pzp import pzp

        return pzp(
            items,
            format_fn=format_fn,
            height=height,
            prompt_str=prompt,
        )
