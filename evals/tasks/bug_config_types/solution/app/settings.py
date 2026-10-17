import os

DEFAULTS = {"page_size": "20", "debug": "false", "timeout": "5"}
TYPES = {"page_size": int, "timeout": int, "debug": lambda v: v.strip().lower() in ("true", "1", "yes")}


def get(name):
    raw = os.environ.get(f"APP_{name.upper()}", DEFAULTS[name])
    return TYPES.get(name, str)(raw)
