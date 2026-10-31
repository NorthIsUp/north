"""Identifier casing and colored differences.

>>> to_snake("HTTPServer42")
'http_server42'
>>> camelcase("http-server42")
'httpServer42'
>>> colordiff("same", "same")
'same'
"""

from .case import (
    alphanumcase,
    backslashcase,
    camelcase,
    capitalcase,
    constcase,
    dotcase,
    lowercase,
    pascalcase,
    pathcase,
    sentencecase,
    snakecase,
    spinalcase,
    titlecase,
    to_camel,
    to_delimited,
    to_kebab,
    to_lower_camel,
    to_screaming_delimited,
    to_screaming_kebab,
    to_screaming_snake,
    to_snake,
    trimcase,
    uppercase,
)
from .diff import colordiff

__all__ = [
    "alphanumcase",
    "backslashcase",
    "camelcase",
    "capitalcase",
    "colordiff",
    "constcase",
    "dotcase",
    "lowercase",
    "pascalcase",
    "pathcase",
    "sentencecase",
    "snakecase",
    "spinalcase",
    "titlecase",
    "to_camel",
    "to_delimited",
    "to_kebab",
    "to_lower_camel",
    "to_screaming_delimited",
    "to_screaming_kebab",
    "to_screaming_snake",
    "to_snake",
    "trimcase",
    "uppercase",
]
