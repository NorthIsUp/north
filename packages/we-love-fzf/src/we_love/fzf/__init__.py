"""Select typed objects using fzf with a pzp fallback.

>>> fzf_select([]) is None
True
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Literal, overload

from pzp import pzp

if TYPE_CHECKING:
    from collections.abc import Callable


@overload
def fzf_select[T](
    items: list[T],
    prompt: str = ...,
    format_fn: Callable[[T], str] = ...,
    height: int = ...,
    width: int = ...,
    many: Literal[False] = False,
    header: str | None = None,
) -> T | None: ...


@overload
def fzf_select[T](
    items: list[T],
    prompt: str = ...,
    format_fn: Callable[[T], str] = ...,
    height: int = ...,
    width: int = ...,
    *,
    many: Literal[True],
    header: str | None = None,
) -> list[T] | None: ...


@overload
def fzf_select[T](
    items: list[T],
    prompt: str = ...,
    format_fn: Callable[[T], str] = ...,
    height: int = ...,
    width: int = ...,
    *,
    many: bool,
    header: str | None = None,
) -> T | list[T] | None: ...


def fzf_select[T](
    items: list[T],
    prompt: str = "Select an item: ",
    format_fn: Callable[[T], str] = str,
    height: int = 40,
    width: int = 100,
    many: bool = False,
    header: str | None = None,
) -> T | list[T] | None:
    if not items:
        return None
    command = ["fzf", "--prompt", prompt, "--height", str(height), "--ansi", "--with-nth", "2..", "--delimiter", "\t"]
    if many:
        command.append("--multi")
    if header is not None:
        command.extend(("--header", header))
    labels = [
        f"{index}\t{format_fn(item).translate(str.maketrans({chr(10): ' ', chr(13): ' ', chr(9): ' '}))}"
        for index, item in enumerate(items)
    ]
    try:
        result = subprocess.run(command, input="\n".join(labels), text=True, stdout=subprocess.PIPE, check=False)
    except FileNotFoundError:
        selected = pzp(labels, format_fn=str, height=height, prompt_str=prompt, header_str=header or "")
        if selected is None:
            return None
        item = items[int(selected.split("\t", 1)[0])]
        return [item] if many else item
    if result.returncode in {1, 130}:
        return None
    result.check_returncode()
    if not result.stdout.strip():
        return None
    selected = [items[int(line.split("\t", 1)[0])] for line in result.stdout.splitlines()]
    return selected if many else selected[0]


__all__ = ["fzf_select"]
