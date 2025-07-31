from typing import Literal

from .typeid import TypeId


def test_ids():
    assert TypeId("hi") == TypeId("hi")
    assert TypeId("hi") != TypeId("hi2")
    assert TypeId("hi") != TypeId("hi_1234")
    assert TypeId("hi") != TypeId("hi_1234")


def test_type_safety() -> None:
    """Test that TypeId with different prefixes are type-safe and distinct."""

    # works as subclass
    class EncId(TypeId[Literal["enc"]]): ...

    assert EncId.__name__ == "EncId"
    assert EncId.__typeid_prefix__ == Literal["enc"]
    assert EncId.__typeid_prefix_str__ == "enc"

    # works as assignment
    user_id = TypeId[Literal["user"]]

    assert user_id.__name__ == "UserId"
    assert user_id.__typeid_prefix__ == Literal["user"]
    assert user_id.__typeid_prefix_str__ == "user"

    enc = EncId("1234")
    user = user_id("abcd")

    # Test that instances have correct prefixes
    assert enc.prefix == Literal["enc"]
    assert user.prefix == Literal["user"]

    assert enc.prefix_str == "enc"
    assert user.prefix_str == "user"

    # Test that string representation includes prefix
    assert str(enc) == "enc_1234"
    assert str(user) == "user_abcd"

    # Test that different types are not equal even with same suffix
    enc_duplicate = EncId("abcd")
    assert user != enc_duplicate

    # Test type safety function
    def take_enc_id(x: TypeId[Literal["enc"]]) -> str:
        return f"Processing {x}"

    # This should work fine
    result = take_enc_id(enc)
    assert result == "Processing enc_1234"

    # Note: take_enc_id(user) would fail static type checking
    # but we can't test that at runtime without a type checker


def test_values():
    typeid = "enc_01jp36hnz4fvmvm4bge859pb5r"
    expected_uuid = "01958668-d7e4-7ee9-ba11-70720a9b2cb8"
    assert TypeId._convert_b32_to_uuid(typeid) == expected_uuid
    assert TypeId._convert_uuid_to_b32(expected_uuid) == typeid
