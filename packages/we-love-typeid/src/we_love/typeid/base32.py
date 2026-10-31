"""Canonical lowercase Crockford encoding of 128-bit values."""

SUFFIX_LEN = 26
ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def encode(src: list[int]) -> str:
    if len(src) != 16 or any(not 0 <= value <= 255 for value in src):
        raise ValueError("Expected exactly 16 bytes")
    value = int.from_bytes(src, "big")
    return "".join(ALPHABET[(value >> shift) & 31] for shift in range(125, -1, -5))


def decode(s: str) -> list[int]:
    if len(s) != SUFFIX_LEN or any(character not in ALPHABET for character in s):
        raise ValueError("Expected 26 lowercase Crockford base32 characters")
    if s[0] > "7":
        raise ValueError("Base32 value exceeds 128 bits")
    value = 0
    for character in s:
        value = (value << 5) | ALPHABET.index(character)
    return list(value.to_bytes(16, "big"))
