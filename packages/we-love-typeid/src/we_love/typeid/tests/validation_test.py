"""Reject malformed encodings without losing UUID bits."""

from typing import Literal

import pytest
import uuid6
from we_love.typeid import TypeId
from we_love.typeid.base32 import decode, encode


@pytest.mark.parametrize("suffix", ["", "0" * 25, "0" * 27, "0" * 25 + "!", "z" + "0" * 25, "0" * 25 + "A", "é" * 26])
def test_invalid_suffixes_are_rejected(suffix: str) -> None:
    """Malformed suffixes fail consistently before byte indexing or UUID construction."""
    with pytest.raises(ValueError, match=r"Expected|exceeds"):
        decode(suffix)
    with pytest.raises(ValueError, match=r"Expected|exceeds"):
        TypeId[Literal["user"]](suffix)


def test_base_type_and_empty_prefix_roundtrip() -> None:
    """Unspecialized identifiers expose their suffix and embedded prefix correctly."""
    suffix = "0" * 26
    raw: TypeId[str] = TypeId(f"user_account_{suffix}")
    assert raw.prefix_str == "user_account"
    assert raw.suffix == suffix
    assert TypeId[Literal[""]](suffix) == suffix


def test_all_uuid_bits_survive_conversion() -> None:
    """Decoding must not rewrite version or variant bits from the original UUID."""
    original = uuid6.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
    suffix = TypeId.convert_uuid_to_b32(original)
    assert TypeId.convert_b32_to_uuid(suffix) == original
    assert encode(decode(suffix)) == suffix


@pytest.mark.parametrize("prefix", ["Bad", "_bad", "bad_", "a" * 64])
def test_invalid_prefixes_are_rejected(prefix: str) -> None:
    """Only canonical lowercase prefixes can define specialized identifier classes."""
    with pytest.raises(ValueError, match="prefixes"):
        TypeId.__class_getitem__(prefix)


def test_identifier_string_operations_return_plain_strings() -> None:
    """String slicing and casing must not try to construct malformed identifiers."""
    item = TypeId[Literal["user"]]("0" * 26)
    assert item[:4] == "user"
    assert item.upper().startswith("USER_")
    assert isinstance(item, str)
