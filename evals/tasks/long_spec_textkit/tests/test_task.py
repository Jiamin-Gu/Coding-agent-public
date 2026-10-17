import pytest

import textkit as t


@pytest.mark.parametrize("src, out", [("Hello, World!", "hello-world"), ("  A--B  ", "a-b"),
                                      ("C++ & Python 3", "c-python-3"), ("你好 world", "world"), ("!!!", ""),
                                      ("Ünïcödé Test", "n-c-d-test"), ("already-slug", "already-slug")])
def test_slugify(src, out):
    assert t.slugify(src) == out


@pytest.mark.parametrize("src, out", [("parseHTTPResponse", "parse_http_response"), ("userID", "user_id"),
                                      ("HTMLParser", "html_parser"), ("getV2Data", "get_v2_data"),
                                      ("simple", "simple"), ("version2Update", "version2_update")])
def test_camel_to_snake(src, out):
    assert t.camel_to_snake(src) == out


@pytest.mark.parametrize("src, out", [("parse_http_response", "parseHttpResponse"), ("_private_var", "_privateVar"),
                                      ("a__b", "aB"), ("HELLO_WORLD", "helloWorld"), ("simple", "simple")])
def test_snake_to_camel(src, out):
    assert t.snake_to_camel(src) == out


def test_truncate_middle():
    assert t.truncate_middle("abcdefghij", 5) == "ab…ij"
    assert t.truncate_middle("abcdefghij", 4) == "ab…j"
    assert t.truncate_middle("abc", 3) == "abc"
    assert t.truncate_middle("abcdef", 1) == "…"
    assert t.truncate_middle("abcdefghij", 6) == "abc…ij"
    with pytest.raises(ValueError):
        t.truncate_middle("abc", 0)


def test_normalize_whitespace():
    assert t.normalize_whitespace("  a\t\tb\n\nc  ") == "a b c"
    assert t.normalize_whitespace("中文\u3000\u3000空格") == "中文 空格"
    assert t.normalize_whitespace("   ") == ""


def test_extract_emails():
    assert t.extract_emails("联系 Bob@Example.com 或 alice.w+tag@mail.co.uk，抄送 bob@example.com。") == [
        "bob@example.com", "alice.w+tag@mail.co.uk"]
    assert t.extract_emails("写信到 a@b.cn.") == ["a@b.cn"]
    assert t.extract_emails("x@y.c") == []
    assert t.extract_emails("first: Z_9%x-y@sub-domain.example.org, then z_9%x-y@SUB-domain.example.org") == [
        "z_9%x-y@sub-domain.example.org"]


def test_word_count():
    assert t.word_count("Hello, 世界! it's 2026") == 5
    assert t.word_count("") == 0
    assert t.word_count("中文和English混合") == 6   # 5 个汉字 + 1 个英文单词
    assert t.word_count("--- !!! ...") == 0


def test_levenshtein():
    assert t.levenshtein("kitten", "sitting") == 3
    assert t.levenshtein("", "abc") == 3
    assert t.levenshtein("flaw", "lawn") == 2
    assert t.levenshtein("same", "same") == 0
    assert t.levenshtein("abc", "") == 3


def test_is_palindrome():
    assert t.is_palindrome("A man, a plan, a canal: Panama") is True
    assert t.is_palindrome("race a car") is False
    assert t.is_palindrome("") is True
    assert t.is_palindrome("!!") is True
    assert t.is_palindrome("No 'x' in Nixon") is True


@pytest.mark.parametrize("src, out", [
    ("the lord of the rings", "The Lord of the Rings"), ("NASA and the moon", "NASA and the Moon"),
    ("what is it for", "What Is It For"), ("the CEO of IBM", "The CEO of IBM"), ("  hello   world ", "Hello World"),
    ("gone WITH the wind", "Gone WITH the Wind"), ("a", "A"), ("iPHONE review", "Iphone Review"),
])
def test_title_case(src, out):
    assert t.title_case(src) == out


def test_wrap():
    assert t.wrap("the quick brown fox", 10) == ["the quick", "brown fox"]
    assert t.wrap("abcdefghij xy", 4) == ["abcd", "efgh", "ij", "xy"]
    assert t.wrap("a bb ccc", 4) == ["a bb", "ccc"]
    assert t.wrap("", 5) == [] and t.wrap("   ", 5) == []
    assert t.wrap("one  two\nthree", 7) == ["one two", "three"]
    with pytest.raises(ValueError):
        t.wrap("abc", 0)


def test_parse_kv():
    assert t.parse_kv('a=1; b = two ;c=') == {"a": "1", "b": "two", "c": ""}
    assert t.parse_kv('x="a;b=c" ; y=2;') == {"x": "a;b=c", "y": "2"}
    assert t.parse_kv('k=1;k=2') == {"k": "2"}
    assert t.parse_kv('q=" padded "') == {"q": " padded "}
    assert t.parse_kv(';;') == {}
    assert t.parse_kv('url=http://x/?a=1') == {"url": "http://x/?a=1"}


@pytest.mark.parametrize("bad", ["novalue", "=1", 'x="unclosed', "a=1;;b"])
def test_parse_kv_errors(bad):
    with pytest.raises(ValueError):
        t.parse_kv(bad)
