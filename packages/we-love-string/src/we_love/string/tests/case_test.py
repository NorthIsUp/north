"""One word-boundary contract across both public casing vocabularies."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from we_love import string

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize("text", ["HTTPServer42", "http-server42", "http_server42", " http...server42 ", "HTTP Server42"])
@pytest.mark.parametrize(
    ("convert", "expected"),
    [
        (string.to_snake, "http_server42"),
        (string.snakecase, "http_server42"),
        (string.camelcase, "httpServer42"),
        (string.to_camel, "HttpServer42"),
        (string.constcase, "HTTP_SERVER42"),
        (string.pathcase, "http/server42"),
        (string.backslashcase, "http\\server42"),
        (string.dotcase, "http.server42"),
        (string.sentencecase, "Http server42"),
        (string.titlecase, "Http Server42"),
    ],
)
def test_identifier_word_boundaries(text: str, convert: Callable[[str], str], expected: str) -> None:
    """Acronyms, punctuation, and mixed separators produce the same identifier words."""
    assert convert(text) == expected


@pytest.mark.parametrize("convert", [string.to_snake, string.camelcase, string.to_camel, string.titlecase, string.sentencecase])
def test_empty_and_punctuation_only_inputs(convert: Callable[[str], str]) -> None:
    """An absent identifier stays empty instead of producing separators or crashing."""
    assert not convert("")
    assert not convert(" --- ")


def test_plain_text_operations_do_not_tokenize() -> None:
    """Simple text casing and trimming preserve punctuation and spacing."""
    assert string.uppercase(" a.b ") == " A.B "
    assert string.lowercase(" A.B ") == " a.b "
    assert string.capitalcase("hello WORLD") == "Hello WORLD"
    assert string.trimcase(" a.b ") == "a.b"
    assert string.alphanumcase("a-b_2!") == "ab2"
    assert string.to_screaming_delimited("httpServer", "::") == "HTTP::SERVER"
    assert string.colordiff("same", "same") == "same"
