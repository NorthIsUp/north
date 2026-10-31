"""ASCII identifier case conversion with shared word boundaries."""

import re


def _words(value: str) -> list[str]:
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return [match.group(0) for match in re.finditer(r"[A-Za-z0-9]+", value)]


def to_delimited(value: str, delimiter: str) -> str:
    return delimiter.join(word.lower() for word in _words(value))


def to_camel(value: str) -> str:
    return "".join(word.capitalize() for word in _words(value))


def to_lower_camel(value: str) -> str:
    words = _words(value)
    return words[0].lower() + "".join(word.capitalize() for word in words[1:]) if words else ""


def to_snake(value: str) -> str:
    return to_delimited(value, "_")


def to_kebab(value: str) -> str:
    return to_delimited(value, "-")


def to_screaming_delimited(value: str, delimiter: str) -> str:
    return to_delimited(value, delimiter).upper()


def to_screaming_snake(value: str) -> str:
    return to_screaming_delimited(value, "_")


def to_screaming_kebab(value: str) -> str:
    return to_screaming_delimited(value, "-")


def capitalcase(value: str) -> str:
    return value[:1].upper() + value[1:]


def lowercase(value: str) -> str:
    return value.lower()


def uppercase(value: str) -> str:
    return value.upper()


def trimcase(value: str) -> str:
    return value.strip()


def pathcase(value: str) -> str:
    return to_delimited(value, "/")


def backslashcase(value: str) -> str:
    return to_delimited(value, "\\")


def sentencecase(value: str) -> str:
    return capitalcase(to_delimited(value, " "))


def titlecase(value: str) -> str:
    return " ".join(word.capitalize() for word in _words(value))


def dotcase(value: str) -> str:
    return to_delimited(value, ".")


def alphanumcase(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value)


camelcase = to_lower_camel
pascalcase = to_camel
snakecase = to_snake
constcase = to_screaming_snake
spinalcase = to_kebab
