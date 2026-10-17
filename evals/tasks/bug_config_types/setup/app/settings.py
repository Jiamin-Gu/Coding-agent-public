import os

DEFAULTS = {"page_size": "20", "debug": "false", "timeout": "5"}


def get(name):
    """读取配置：优先使用环境变量 APP_<NAME>，否则用默认值。"""
    return os.environ.get(f"APP_{name.upper()}", DEFAULTS[name])
