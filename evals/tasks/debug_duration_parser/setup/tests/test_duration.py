from duration import format_duration, parse_duration


def test_basic():
    assert parse_duration("1h30m") == 5400
    assert parse_duration("2d 3h") == 2 * 86400 + 3 * 3600


def test_decimal():
    assert parse_duration("1.5h") == 5400


def test_format():
    assert format_duration(5400) == "1h30m"
