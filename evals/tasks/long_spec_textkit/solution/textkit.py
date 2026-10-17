import math
import re

SMALL_WORDS = {"a", "an", "the", "and", "but", "or", "for", "nor", "on", "at", "to", "of", "in", "by"}


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def camel_to_snake(name):
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def snake_to_camel(name):
    lead = len(name) - len(name.lstrip("_"))
    words = [w for w in name[lead:].split("_") if w]
    if not words:
        return name
    return "_" * lead + words[0].lower() + "".join(w[:1].upper() + w[1:].lower() for w in words[1:])


def truncate_middle(text, max_len):
    if max_len < 1:
        raise ValueError("max_len 必须至少为 1")
    if len(text) <= max_len:
        return text
    keep = max_len - 1
    head = math.ceil(keep / 2)
    tail = keep - head
    return text[:head] + "…" + (text[-tail:] if tail else "")


def normalize_whitespace(text):
    return " ".join(text.split())


EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}")


def extract_emails(text):
    out = []
    for m in EMAIL.findall(text):
        e = m.lower()
        if e not in out:
            out.append(e)
    return out


def word_count(text):
    return len(re.findall(r"[A-Za-z0-9']+|[\u4e00-\u9fff]", text))


def levenshtein(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def is_palindrome(text):
    s = [c.lower() for c in text if c.isascii() and c.isalnum()]
    return s == s[::-1]


def title_case(text):
    words = text.split()
    out = []
    for i, w in enumerate(words):
        if len(w) >= 2 and w.isupper():
            out.append(w)
        elif w.lower() in SMALL_WORDS and 0 < i < len(words) - 1:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return " ".join(out)


def wrap(text, width):
    if width < 1:
        raise ValueError("width 必须至少为 1")
    pieces = []
    for w in normalize_whitespace(text).split():
        pieces += [w[i:i + width] for i in range(0, len(w), width)]
    lines, cur = [], ""
    for p in pieces:
        if not cur:
            cur = p
        elif len(cur) + 1 + len(p) <= width:
            cur += " " + p
        else:
            lines.append(cur)
            cur = p
    if cur:
        lines.append(cur)
    return lines


def parse_kv(text):
    result = {}
    i, n = 0, len(text)
    while i < n:
        j = i
        while j < n and text[j] not in ";=":
            j += 1
        if j >= n or text[j] == ";":
            if text[i:j].strip():
                raise ValueError(f"缺少 '='：{text[i:j]!r}")
            i = j + 1
            continue
        key = text[i:j].strip()
        if not key:
            raise ValueError("键不能为空")
        k = j + 1
        while k < n and text[k] in " \t":
            k += 1
        if k < n and text[k] == '"':
            end = text.find('"', k + 1)
            if end == -1:
                raise ValueError("引号没有闭合")
            value = text[k + 1:end]
            k = end + 1
            while k < n and text[k] != ";":
                if not text[k].isspace():
                    raise ValueError("引号后有多余字符")
                k += 1
        else:
            end = text.find(";", k)
            end = n if end == -1 else end
            value = text[k:end].strip()
            k = end
        result[key] = value
        i = k + 1
    return result
