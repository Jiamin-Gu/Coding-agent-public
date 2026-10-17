import os

DEFAULTS = {"page_size": 20, "debug": False, "timeout": 5}

_BOOL_TRUE = {"true", "1", "yes"}


def _as_int(value):
    return int(value)


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _BOOL_TRUE


_CONVERTERS = {"page_size": _as_int, "timeout": _as_int, "debug": _as_bool}


def get(name):
    """读取配置：优先使用环境变量 APP_<NAME>，否则用默认值，并转换为正确的类型。"""
    raw = os.environ.get(f"APP_{name.upper()}", DEFAULTS[name])
    return _CONVERTERS[name](raw)
