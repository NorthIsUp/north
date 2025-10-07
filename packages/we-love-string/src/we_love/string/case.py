"""
String convert functions
"""

import re

# Pre-compiled regex patterns for speed
_SNAKE_CASE_DELIMITER_TRANSLATION = str.maketrans("-. ", "___")
_SNAKE_CASE_CAPITAL_RE = re.compile(r"[A-Z]")
_CAMEL_CASE_UNDERSCORE_RE = re.compile(r"_+([a-zA-Z])")
_CAMEL_CASE_HYPHEN_RE = re.compile(r"-+([a-zA-Z])")
_PATH_CASE_RE = re.compile(r"_")
_BACKSLASH_CASE_RE = re.compile(r"_")
_SENTENCE_CASE_DELIMITER_RE = re.compile(r"[\\-_\\.\\s]")
_SENTENCE_CASE_CAPITAL_RE = re.compile(r"[A-Z]")
_SPINAL_CASE_RE = re.compile(r"_")
_DOT_CASE_RE = re.compile(r"_")
_ALPHANUM_FILTER_RE = re.compile(r"[^a-zA-Z0-9]")


def camelcase(string: str) -> str:
    """Convert string into camel case. Optimized for speed.

    Args:
        string: String to convert.

    Returns:
        string: Camel case string.

    """

    if not string:
        return ""

    # Handle underscores first, then hyphens
    string = _CAMEL_CASE_UNDERSCORE_RE.sub(lambda m: m.group(1).upper(), string)
    string = _CAMEL_CASE_HYPHEN_RE.sub(lambda m: m.group(1).upper(), string)
    return string


def capitalcase(string: str) -> str:
    """Convert string into capital case.
    First letters will be uppercase.

    Args:
        string: String to convert.

    Returns:
        string: Capital case string.

    """

    if not string:
        return ""
    # Use slicing and upper() for potential micro-optimization over calling uppercase()
    s = str(string)
    return s[0].upper() + s[1:]


def constcase(string: str) -> str:
    """Convert string into upper snake case. Optimized for speed.

    Args:
        string: String to convert.

    Returns:
        string: Const cased string.

    """

    if not string:
        return ""
    s = str(string).translate(_SNAKE_CASE_DELIMITER_TRANSLATION)
    result = _SNAKE_CASE_CAPITAL_RE.sub(lambda m: "_" + m.group(0), s)
    return result.upper()


def lowercase(string: str) -> str:
    """Convert string into lower case.

    Args:
        string: String to convert.

    Returns:
        string: Lowercase case string.

    """

    return str(string).lower()


def pascalcase(string: str) -> str:
    """Convert string into pascal case. Optimized for speed.

    Args:
        string: String to convert.

    Returns:
        string: Pascal case string.

    """

    if not string:
        return ""
    # Handle underscores first, then hyphens
    s = _CAMEL_CASE_UNDERSCORE_RE.sub(lambda m: m.group(1).upper(), string)
    s = _CAMEL_CASE_HYPHEN_RE.sub(lambda m: m.group(1).upper(), s)
    return s[0].upper() + s[1:]


def pathcase(string: str) -> str:
    """Convert string into path case. Optimized for speed.

    Args:
        string: String to convert.

    Returns:
        string: Path cased string.

    """

    return _PATH_CASE_RE.sub("/", snakecase(string))


def backslashcase(string: str) -> str:
    """Convert string into spinal case.
    Join punctuation with backslash.

    Args:
        string: String to convert.

    Returns:
        string: Spinal cased string.

    """
    return _BACKSLASH_CASE_RE.sub(r"\\\\", snakecase(string))


def sentencecase(string: str) -> str:
    """Convert string into sentence case. Optimized for speed.

    Args:
        string: String to convert.

    Returns:
        string: Sentence cased string.

    """
    joiner = " "
    s = _SENTENCE_CASE_DELIMITER_RE.sub(joiner, str(string))
    if not s:
        return ""
    # Apply capitalcase logic directly after handling uppercase letters
    transformed = _SENTENCE_CASE_CAPITAL_RE.sub(
        lambda m: joiner + m.group(0).lower(), s
    ).strip()
    return transformed[0].upper() + transformed[1:] if transformed else ""


def snakecase(string: str) -> str:
    """Convert string into snake case. Optimized for speed.

    Args:
        string: String to convert.

    Returns:
        string: Snake cased string.

    """

    if not string:
        return ""
    # Use translate for faster delimiter replacement
    s = str(string).translate(_SNAKE_CASE_DELIMITER_TRANSLATION)
    # Apply lowercase transformation during substitution
    result = _SNAKE_CASE_CAPITAL_RE.sub(lambda m: "_" + m.group(0).lower(), s)
    return result[0].lower() + result[1:]


def spinalcase(string: str) -> str:
    """Convert string into spinal case. Optimized for speed.

    Args:
        string: String to convert.

    Returns:
        string: Spinal cased string.

    """

    return _SPINAL_CASE_RE.sub("-", snakecase(string))


def dotcase(string: str) -> str:
    """Convert string into dot case. Optimized for speed.

    Args:
        string: String to convert.

    Returns:
        string: Dot cased string.

    """

    return _DOT_CASE_RE.sub(".", snakecase(string))


def titlecase(string: str) -> str:
    """Convert string into sentence case.
    First letter capped while each punctuations is capitalsed
    and joined with space.

    Args:
        string: String to convert.

    Returns:
        string: Title cased string.

    """

    # Avoid list comprehension for potential speedup
    words = snakecase(string).split("_")
    if not words:
        return ""

    # Build the string directly
    result = words[0][0].upper() + words[0][1:] if words[0] else ""
    for word in words[1:]:
        if word:
            result += " " + word[0].upper() + word[1:]
        else:
            result += " "  # Handle potential empty strings from multiple underscores
    return result


def trimcase(string: str) -> str:
    """Convert string into trimmed string.

    Args:
        string: String to convert.

    Returns:
        string: Trimmed case string
    """

    return str(string).strip()


def uppercase(string: str) -> str:
    """Convert string into upper case.

    Args:
        string: String to convert.

    Returns:
        string: Uppercase case string.

    """

    return str(string).upper()


def alphanumcase(string: str) -> str:
    """Cuts all non-alphanumeric symbols. Optimized for speed.

    Args:
        string: String to convert.

    Returns:
        string: String with cutted non-alphanumeric symbols.

    """
    # Using regex sub is often faster than filter/join for this
    return _ALPHANUM_FILTER_RE.sub("", str(string))
