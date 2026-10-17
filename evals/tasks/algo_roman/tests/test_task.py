import pytest

from roman import from_roman, to_roman


def test_known_values():
    assert to_roman(1994) == "MCMXCIV"
    assert to_roman(3999) == "MMMCMXCIX"
    assert to_roman(4) == "IV"
    assert from_roman("MCMXCIV") == 1994
    assert from_roman("LVIII") == 58


def test_round_trip():
    for n in range(1, 4000):
        assert from_roman(to_roman(n)) == n


@pytest.mark.parametrize("n", [0, 4000, -1])
def test_out_of_range(n):
    with pytest.raises(ValueError):
        to_roman(n)


@pytest.mark.parametrize("s", ["IIII", "VX", "IC", "", "mcm", "ABC", "MMMM"])
def test_invalid_numerals(s):
    with pytest.raises(ValueError):
        from_roman(s)
