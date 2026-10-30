import pytest
from we_love.matchbox.regex import ReFullmatch, RegexMatch, ReMatch, ReSearch


@pytest.mark.parametrize("matcher", [RegexMatch, ReSearch, ReMatch, ReFullmatch])
def test_matchers_preserve_optional_groups(matcher: type[RegexMatch]) -> None:
    regex = matcher(r"(?P<optional>a)?b")
    assert regex == "b"
    assert regex["optional"] is None
    assert regex.groups() == (None,)
    assert regex.groupdict() == {"optional": None}
    assert regex == "ab"
    assert regex.groups() == ("a",)
    assert regex.groupdict() == {"optional": "a"}


def test_matching_modes_remain_distinct() -> None:
    assert ReSearch("b") == "abc"
    assert ReMatch("b") != "abc"
    assert ReMatch("b") == "bc"
    assert ReFullmatch("b") != "bc"
    assert ReFullmatch("b") == "b"


def test_matchers_reject_non_strings_and_clear_failed_matches() -> None:
    regex = ReSearch("(b)")
    assert regex != 1
    assert regex == "b"
    assert regex != "a"
    with pytest.raises(ValueError, match="No match found"):
        regex.groups()
