"""发给模型之前遮蔽工具结果里的密钥。

agent 读文件、执行命令得到的内容会原样发给模型服务商，项目里的 .env、配置文件、命令输出（env、cat ~/.aws/credentials）
都可能带着密钥。这里把高可信度的密钥格式、私钥块、看起来是密钥的赋值替换成占位符，模型和界面都只看到占位符。

只遮蔽有把握的格式，宁可漏掉也不误伤普通代码：误伤会让模型看到错的代码。
占位符不能被写回文件（否则真正的密钥会被覆盖成占位符），写文件和改文件时由 agent 检查并拒绝。
"""
import re

MARK = "[已遮蔽的密钥"

# (说明, 正则)：匹配到的整段都换掉
TOKEN_PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S)),
    ("anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai-style", re.compile(r"\bsk-(?:proj-|live-|test-)?[A-Za-z0-9_\-]{20,}")),
    ("github", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("slack", re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("stripe", re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
]

SECRET_NAME = r"[A-Za-z0-9_.\-]*(?:(?:api|access|secret|client|auth)[_\-]?key|apikey|secret|token|passw(?:or)?d|pwd|private[_\-]?key|credential)s?"
# 引号里的字面量赋给像密钥的名字：password = "hunter22"、"api_key": "abc…"（代码里的 os.getenv(...) 不会被误伤）
QUOTED_ASSIGN = re.compile(r"(?i)(\b" + SECRET_NAME + r"[\"']?\s*[:=]\s*)([\"'])([^\"'\s]{8,})\2")
# .env / env 命令输出的写法：API_KEY=xxxx（等号两边没有空格，值没有引号）
ENV_ASSIGN = re.compile(r"(?m)^([ \t]*(?:export[ \t]+)?[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIALS?)"
                        r"[A-Z0-9_]*=)([^\s\"'#]{8,})[ \t]*$")
# aws/ini 配置：aws_secret_access_key = xxxx。代码里也有 token = self.peek() 这种写法，
# 所以要求值像随机串：至少 16 个字符、同时有字母和数字、没有括号和点这类代码符号
INI_ASSIGN = re.compile(r"(?im)^([ \t]*" + SECRET_NAME + r"[ \t]*=[ \t]*)"
                        r"((?=[^\s\"'#]*\d)(?=[^\s\"'#]*[A-Za-z])[^\s\"'#()\[\]{}.,]{16,})[ \t]*$")


def _mark(kind: str) -> str:
    return f"{MARK}:{kind}]"


def redact(text: str) -> tuple[str, int]:
    """返回 (遮蔽后的文本, 遮蔽的处数)。"""
    if not text:
        return text, 0
    count = 0

    def sub_all(pattern, repl, s):
        nonlocal count
        s, n = pattern.subn(repl, s)
        count += n
        return s

    for kind, pattern in TOKEN_PATTERNS:
        text = sub_all(pattern, _mark(kind), text)
    # 已经换成占位符的不再处理（占位符本身含冒号等字符）
    text = sub_all(QUOTED_ASSIGN, lambda m: m.group(0) if MARK in m.group(3) else
                   f"{m.group(1)}{m.group(2)}{_mark('value')}{m.group(2)}", text)
    text = sub_all(ENV_ASSIGN, lambda m: m.group(0) if MARK in m.group(2) else f"{m.group(1)}{_mark('value')}", text)
    text = sub_all(INI_ASSIGN, lambda m: m.group(0) if MARK in m.group(2) else f"{m.group(1)}{_mark('value')}", text)
    return text, count


def placeholder_in(args: dict) -> bool:
    """写文件、改文件的参数里有没有占位符。"""
    return any(isinstance(args.get(k), str) and MARK in args[k] for k in ("content", "old_string", "new_string"))


WRITE_BACK_ERROR = ("内容里包含被遮蔽的密钥占位符（" + MARK + ":…]）。为了保护密钥，你看到的是占位符而不是真实的值，"
                    "不能把它写回文件，否则真正的密钥会被覆盖。请用 edit_file 只修改不含密钥的部分"
                    "（old_string / new_string 都不要包含占位符）；需要设置密钥时，请让用户自己填写。")
