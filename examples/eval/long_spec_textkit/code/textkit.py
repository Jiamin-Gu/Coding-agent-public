"""A small collection of text utility functions.

See docs/SPEC.md for the detailed specification.
"""

import re

__all__ = [
    "slugify",
    "camel_to_snake",
    "snake_to_camel",
    "truncate_middle",
    "normalize_whitespace",
    "extract_emails",
    "word_count",
    "levenshtein",
    "is_palindrome",
    "title_case",
    "wrap",
    "parse_kv",
]


# 1. slugify
def slugify(text: str) -> str:
    """Lowercase *text* and turn every run of non-alphanumeric characters into a single '-'."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# 2. camel_to_snake
def camel_to_snake(name: str) -> str:
    """Convert a camelCase/PascalCase name to snake_case (all lowercase)."""
    # Split an acronym from a following capitalized word: "HTTPResponse" -> "HTTP_Response"
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    # Split a lowercase/digit from a following uppercase: "parseHTTP" -> "parse_HTTP"
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


# 3. snake_to_camel
def snake_to_camel(name: str) -> str:
    """Convert a snake_case name to lowerCamelCase, preserving leading underscores."""
    prefix_match = re.match(r"^_+", name)
    prefix = prefix_match.group(0) if prefix_match else ""
    rest = name[len(prefix):]
    parts = [part for part in rest.split("_") if part != ""]
    if not parts:
        return prefix + rest
    camel = parts[0].lower() + "".join(word.capitalize() for word in parts[1:])
    return prefix + camel


# 4. truncate_middle
def truncate_middle(text: str, max_len: int) -> str:
    """Truncate *text* in the middle so the result is exactly *max_len* characters."""
    if max_len < 1:
        raise ValueError("max_len must be >= 1")
    if len(text) <= max_len:
        return text
    start = max_len // 2  # ceil((max_len - 1) / 2)
    end = max_len - 1 - start
    result = text[:start] + "\u2026"
    if end:
        result += text[-end:]
    return result


# 5. normalize_whitespace
def normalize_whitespace(text: str) -> str:
    """Collapse every run of whitespace into a single space and strip the ends."""
    return re.sub(r"\s+", " ", text).strip()


# 6. extract_emails
_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}"
)


def extract_emails(text: str) -> list:
    """Return unique, lowercased e-mail addresses in order of first appearance."""
    seen = {}
    for match in _EMAIL_RE.finditer(text):
        address = match.group(0).lower()
        if address not in seen:
            seen[address] = None
    return list(seen)


# 7. word_count
_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def word_count(text: str) -> int:
    """Count English words plus individual CJK characters."""
    return len(_WORD_RE.findall(text)) + len(_CJK_RE.findall(text))


# 8. levenshtein
def levenshtein(a: str, b: str) -> int:
    """Return the Levenshtein edit distance between *a* and *b*."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(
                min(
                    previous[j] + 1,        # deletion
                    current[j - 1] + 1,     # insertion
                    previous[j - 1] + cost,  # substitution
                )
            )
        previous = current
    return previous[-1]


# 9. is_palindrome
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")


def is_palindrome(text: str) -> bool:
    """Return True if *text* reads the same forwards and backwards (ignoring case/punctuation)."""
    cleaned = _NON_ALNUM_RE.sub("", text).lower()
    return cleaned == cleaned[::-1]


# 10. title_case
_SMALL_WORDS = {
    "a", "an", "the", "and", "but", "or", "for", "nor",
    "on", "at", "to", "of", "in", "by",
}


def title_case(text: str) -> str:
    """Title-case *text* using the rules described in the specification."""
    words = text.split()
    last = len(words) - 1
    result = []
    for index, word in enumerate(words):
        if len(word) >= 2 and word.isupper():
            result.append(word)
        elif word.lower() in _SMALL_WORDS and index != 0 and index != last:
            result.append(word.lower())
        else:
            result.append(word[:1].upper() + word[1:].lower())
    return " ".join(result)


# 11. wrap
def wrap(text: str, width: int) -> list:
    """Greedily wrap *text* to lines of at most *width* characters."""
    if width < 1:
        raise ValueError("width must be >= 1")
    normalized = normalize_whitespace(text)
    if not normalized:
        return []

    tokens = []
    for word in normalized.split(" "):
        while len(word) > width:
            tokens.append(word[:width])
            word = word[width:]
        tokens.append(word)

    lines = []
    current = ""
    for token in tokens:
        if not current:
            current = token
        elif len(current) + 1 + len(token) <= width:
            current += " " + token
        else:
            lines.append(current)
            current = token
    if current:
        lines.append(current)
    return lines


# 12. parse_kv
def parse_kv(text: str) -> dict:
    """Parse a ``key=value`` list separated by ``;`` into a dict."""
    result = {}
    n = len(text)
    i = 0
    while i < n:
        eq = text.find("=", i)
        semi = text.find(";", i)
        if semi == -1:
            semi = n

        if eq == -1 or eq > semi:
            # No '=' before the next ';': the part must be empty (ignored).
            if text[i:semi].strip() != "":
                raise ValueError("missing '=' in part: %r" % text[i:semi])
            i = semi + 1
            continue

        key = text[i:eq].strip()
        if key == "":
            raise ValueError("empty key in part: %r" % text[i:semi])

        value_start = eq + 1
        probe = value_start
        while probe < n and text[probe].isspace():
            probe += 1

        if probe < n and text[probe] == '"':
            close = text.find('"', probe + 1)
            if close == -1:
                raise ValueError("unterminated quoted value")
            result[key] = text[probe + 1:close]
            next_semi = text.find(";", close + 1)
            i = n if next_semi == -1 else next_semi + 1
        else:
            result[key] = text[value_start:semi].strip()
            i = semi + 1

    return result
