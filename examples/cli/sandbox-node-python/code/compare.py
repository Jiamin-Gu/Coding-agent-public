#!/usr/bin/env python3
"""Compare the Node.js slugify implementation with python-slugify on 5 examples."""

import subprocess

from slugify import slugify as py_slugify

EXAMPLES = [
    "Hello World",
    "Hello, World!",
    "  Leading and Trailing Spaces  ",
    "Version 2.0 — Released!",
    "Don't Stop Believin'",
]

NODE_SCRIPT = (
    "const slugify = require('./slugify');"
    "const s = process.argv[1];"
    "process.stdout.write(slugify(s));"
)


def js_slugify(text: str) -> str:
    result = subprocess.run(
        ["node", "-e", NODE_SCRIPT, text],
        capture_output=True,
        text=True,
        check=True,
        cwd=__file__.rsplit("/", 1)[0] or ".",
    )
    return result.stdout


def main() -> None:
    print(f"{'Example':<34} {'Python':<24} {'Node.js':<24} Match")
    print("-" * 90)
    mismatches = 0
    for example in EXAMPLES:
        py_result = py_slugify(example)
        js_result = js_slugify(example)
        match = py_result == js_result
        if not match:
            mismatches += 1
        print(
            f"{example:<34} {py_result:<24} {js_result:<24} "
            f"{'✓' if match else '✗'}"
        )
    print("-" * 90)
    print(f"Matched: {len(EXAMPLES) - mismatches}/{len(EXAMPLES)}")


if __name__ == "__main__":
    main()