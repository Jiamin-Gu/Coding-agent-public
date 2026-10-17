import pytest

from duration import format_duration, parse_duration


@pytest.mark.parametrize("text, expected", [
    ("1h30m", 5400), ("2d 3h", 183600), ("1H 5M 10S", 3910), ("45s", 45),
    ("  1h   30m  ", 5400), ("1.5h", 5400), ("0.5s", 1), ("1.25m", 75), ("2.5", 3),
    ("90", 90), ("0", 0), ("1d1h1m1s", 90061), ("10M", 600), ("0.4s", 0),
])
def test_parse_valid(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", [
    "", "   ", "-5m", "30m1h", "1h1h", "5x", "1h 30", "abc", "1.h", ".5h", "1h30mx", "h", "1hh",
])
def test_parse_invalid(text):
    with pytest.raises(ValueError):
        parse_duration(text)


@pytest.mark.parametrize("seconds, expected", [
    (5400, "1h30m"), (90061, "1d1h1m1s"), (45, "45s"), (86400, "1d"), (0, "0s"), (3600 + 1, "1h1s"),
])
def test_format(seconds, expected):
    assert format_duration(seconds) == expected


@pytest.mark.parametrize("bad", [-1, 1.5])
def test_format_invalid(bad):
    with pytest.raises(ValueError):
        format_duration(bad)


def test_round_trip():
    for n in list(range(0, 4000, 7)) + [86399, 86400, 172801, 999999]:
        assert parse_duration(format_duration(n)) == n
