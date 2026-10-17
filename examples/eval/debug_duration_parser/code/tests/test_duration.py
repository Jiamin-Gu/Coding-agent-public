import pytest

from duration import format_duration, parse_duration


def test_basic():
    assert parse_duration("1h30m") == 5400
    assert parse_duration("2d 3h") == 2 * 86400 + 3 * 3600


def test_decimal():
    assert parse_duration("1.5h") == 5400


def test_format():
    assert format_duration(5400) == "1h30m"


# ---------------------------------------------------------------------------
# parse_duration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1h30m", 5400),
        ("2d 3h", 2 * 86400 + 3 * 3600),
        ("1H 5M 10S", 3600 + 5 * 60 + 10),
        ("1d1h1m1s", 86400 + 3600 + 60 + 1),
        ("1d2h3m4s", 86400 + 2 * 3600 + 3 * 60 + 4),
        ("2d3h", 2 * 86400 + 3 * 3600),  # 各部分之间可以没有空白
        ("  1h30m  ", 5400),  # 首尾空白忽略
        ("1h\t30m", 5400),  # 制表符也是空白
        ("1h\n30m", 5400),
        ("90", 90),  # 没有单位表示秒
        ("2.5", 3),  # 没有单位，0.5 进位
        ("0.5", 1),
        ("0", 0),
        ("0.4", 0),
        ("1.5h", 5400),
        ("0.25h", 900),
        ("0.5h30m", 3600),  # 0.5h=1800 秒，30m=1800 秒
        ("1.5m", 90),
        ("0s", 0),
    ],
)
def test_parse_valid(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",  # 空
        "   ",  # 只有空白
        "30m1h",  # 顺序错误
        "1h1h",  # 单位重复
        "1s1m",  # 顺序错误
        "1d1d",
        "-1h",  # 负数
        "-5",
        "1x",  # 未知单位
        "5 hours",
        ".5h",  # 小数点前缺数字
        "1.h",  # 小数点后缺数字
        "1..5h",
        "1 2",  # 没有单位的数字只能单独出现
        "1h 30",  # 尾部多出没有单位的数字
        "1h!",  # 多余字符
        "h",  # 只有单位
        "1h30",  # 缺少单位
        "abc",
        "1h30m2s3h",  # 顺序错误
    ],
)
def test_parse_invalid(text):
    with pytest.raises(ValueError):
        parse_duration(text)


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "0s"),
        (45, "45s"),
        (60, "1m"),
        (5400, "1h30m"),
        (86400, "1d"),
        (90061, "1d1h1m1s"),
        (3661, "1h1m1s"),
        (3600, "1h"),
        (1, "1s"),
        (59, "59s"),
        (86399, "23h59m59s"),
    ],
)
def test_format_valid(seconds, expected):
    assert format_duration(seconds) == expected


@pytest.mark.parametrize("seconds", [-1, -86400, 1.5, 0.5, "90", None])
def test_format_invalid(seconds):
    with pytest.raises(ValueError):
        format_duration(seconds)


@pytest.mark.parametrize("n", [0, 1, 59, 60, 61, 3599, 3600, 3661, 5400, 86399, 86400, 90061, 123456789])
def test_round_trip(n):
    assert parse_duration(format_duration(n)) == n
