"""Tests for textkit.py, derived from docs/SPEC.md."""

import pytest

import textkit as tk


# 1. slugify
@pytest.mark.parametrize("text,expected", [
    ("Hello, World!", "hello-world"),
    ("  A--B  ", "a-b"),
    ("C++ & Python 3", "c-python-3"),
    ("你好 world", "world"),
    ("!!!", ""),
])
def test_slugify(text, expected):
    assert tk.slugify(text) == expected


# 2. camel_to_snake
@pytest.mark.parametrize("name,expected", [
    ("parseHTTPResponse", "parse_http_response"),
    ("userID", "user_id"),
    ("HTMLParser", "html_parser"),
    ("getV2Data", "get_v2_data"),
    ("simple", "simple"),
])
def test_camel_to_snake(name, expected):
    assert tk.camel_to_snake(name) == expected


# 3. snake_to_camel
@pytest.mark.parametrize("name,expected", [
    ("parse_http_response", "parseHttpResponse"),
    ("_private_var", "_privateVar"),
    ("a__b", "aB"),
    ("HELLO_WORLD", "helloWorld"),
    ("simple", "simple"),
])
def test_snake_to_camel(name, expected):
    assert tk.snake_to_camel(name) == expected


# 4. truncate_middle
@pytest.mark.parametrize("text,max_len,expected", [
    ("abcdefghij", 5, "ab\u2026ij"),
    ("abcdefghij", 4, "ab\u2026j"),
    ("abc", 3, "abc"),
    ("abcdef", 1, "\u2026"),
])
def test_truncate_middle(text, max_len, expected):
    assert tk.truncate_middle(text, max_len) == expected


def test_truncate_middle_length_is_exact():
    assert len(tk.truncate_middle("abcdefghij", 7)) == 7


def test_truncate_middle_raises_when_too_small():
    with pytest.raises(ValueError):
        tk.truncate_middle("abc", 0)


# 5. normalize_whitespace
@pytest.mark.parametrize("text,expected", [
    ("  a\t\tb\n\nc  ", "a b c"),
    ("中文\u3000\u3000空格", "中文 空格"),
])
def test_normalize_whitespace(text, expected):
    assert tk.normalize_whitespace(text) == expected


# 6. extract_emails
def test_extract_emails_basic():
    text = "联系 Bob@Example.com 或 alice.w+tag@mail.co.uk，抄送 bob@example.com。"
    assert tk.extract_emails(text) == ["bob@example.com", "alice.w+tag@mail.co.uk"]


def test_extract_emails_trailing_dot():
    assert tk.extract_emails("写信到 a@b.cn.") == ["a@b.cn"]


def test_extract_emails_short_tld():
    assert tk.extract_emails("x@y.c") == []


def test_extract_emails_empty():
    assert tk.extract_emails("no emails here") == []


# 7. word_count
@pytest.mark.parametrize("text,expected", [
    ("Hello, 世界! it's 2026", 5),
    ("", 0),
])
def test_word_count(text, expected):
    assert tk.word_count(text) == expected


# 8. levenshtein
@pytest.mark.parametrize("a,b,expected", [
    ("kitten", "sitting", 3),
    ("", "abc", 3),
    ("flaw", "lawn", 2),
    ("same", "same", 0),
])
def test_levenshtein(a, b, expected):
    assert tk.levenshtein(a, b) == expected


# 9. is_palindrome
@pytest.mark.parametrize("text,expected", [
    ("A man, a plan, a canal: Panama", True),
    ("race a car", False),
    ("", True),
])
def test_is_palindrome(text, expected):
    assert tk.is_palindrome(text) is expected


# 10. title_case
@pytest.mark.parametrize("text,expected", [
    ("the lord of the rings", "The Lord of the Rings"),
    ("NASA and the moon", "NASA and the Moon"),
    ("what is it for", "What Is It For"),
    ("the CEO of IBM", "The CEO of IBM"),
    ("  hello   world ", "Hello World"),
])
def test_title_case(text, expected):
    assert tk.title_case(text) == expected


# 11. wrap
@pytest.mark.parametrize("text,width,expected", [
    ("the quick brown fox", 10, ["the quick", "brown fox"]),
    ("abcdefghij xy", 4, ["abcd", "efgh", "ij", "xy"]),
    ("a bb ccc", 4, ["a bb", "ccc"]),
])
def test_wrap(text, width, expected):
    assert tk.wrap(text, width) == expected


def test_wrap_empty():
    assert tk.wrap("   ", 5) == []


def test_wrap_width_invalid():
    with pytest.raises(ValueError):
        tk.wrap("abc", 0)


# 12. parse_kv
def test_parse_kv_basic():
    assert tk.parse_kv("a=1; b = two ;c=") == {"a": "1", "b": "two", "c": ""}


def test_parse_kv_quoted_semicolon_equals():
    assert tk.parse_kv('x="a;b=c" ; y=2;') == {"x": "a;b=c", "y": "2"}


def test_parse_kv_duplicate_key():
    assert tk.parse_kv("k=1;k=2") == {"k": "2"}


def test_parse_kv_quoted_whitespace_preserved():
    assert tk.parse_kv('q=" padded "') == {"q": " padded "}


def test_parse_kv_empty():
    assert tk.parse_kv("") == {}


def test_parse_kv_consecutive_semicolons():
    assert tk.parse_kv("a=1;;b=2;") == {"a": "1", "b": "2"}


def test_parse_kv_missing_equals():
    with pytest.raises(ValueError):
        tk.parse_kv("a=1;bad;c=2")


def test_parse_kv_empty_key():
    with pytest.raises(ValueError):
        tk.parse_kv("=1")


def test_parse_kv_unterminated_quote():
    with pytest.raises(ValueError):
        tk.parse_kv('q="abc')
