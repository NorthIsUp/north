"""Converter boundaries used by command-line arguments."""

import pytest

from .converters import ConversionError, FloatConverter, IntConverter, ListConverter, StringConverter


@pytest.mark.parametrize("text", ["-42", "+42", " 42 "])
def test_signed_integer_inputs(text: str) -> None:
    """Valid signed integers should not be rejected by a digit-only precheck."""
    assert abs(IntConverter().decode(text)) == 42


def test_float_exponents_and_list_empty_roundtrip() -> None:
    """CLI values support scientific notation and an empty list round trip."""
    assert FloatConverter().decode("-1.5e2") == -150
    converter = ListConverter(StringConverter())
    assert converter.decode(converter.encode([])) == []


def test_conversion_error_has_human_message() -> None:
    """A rejected input retains its value and a readable exception message."""
    with pytest.raises(ConversionError, match="Invalid int") as caught:
        IntConverter().decode("not an int")
    assert caught.value.value == "not an int"
