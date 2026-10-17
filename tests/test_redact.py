"""遮蔽密钥：常见格式都能认出来，普通代码不误伤；模型看不到密钥，也不能把占位符写回文件。"""
from coder.redact import MARK, redact

from test_agent import make_agent, reply, tool_call

KEY = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6"


def test_known_formats_are_masked():
    samples = [
        KEY,
        "sk-ant-api03-" + "x" * 40,
        "ghp_" + "A" * 36,
        "AKIAIOSFODNN7EXAMPLE",
        "AIza" + "B" * 35,
        "xoxb-1234567890-abcdefghij",
        "sk_live_" + "c" * 24,
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----",
    ]
    for s in samples:
        out, n = redact(f"before {s} after")
        assert n == 1 and s not in out and MARK in out and out.startswith("before ") and out.endswith(" after"), s


def test_assignments_in_env_ini_and_config_files():
    env = "DEBUG=true\nDATABASE_PASSWORD=hunter2hunter2\nexport GITHUB_TOKEN=abcd1234efgh\nPORT=8000\n"
    out, n = redact(env)
    assert n == 2 and "hunter2" not in out and "abcd1234" not in out and "DEBUG=true" in out and "PORT=8000" in out
    ini = "[default]\naws_access_key_id = AKIAIOSFODNN7EXAMPLE\naws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"
    out, _ = redact(ini)
    assert "wJalrXUtnFEMI" not in out and "AKIA" not in out and out.count("\n") == ini.count("\n")
    out, _ = redact('{"api_key": "abc123def456", "name": "demo"}')
    assert "abc123def456" not in out and '"name": "demo"' in out


def test_ordinary_code_is_not_touched():
    code = '''import os
API_KEY = os.getenv("API_KEY")
token = self.peek()
tokens = tokenize(expression)
password = input("password: ")
secret_len = len(secret)
def get_token(self) -> str:
    return self._token
MAX_TOKENS = 4096
url = "https://example.com/sk-learn"
'''
    assert redact(code) == (code, 0)


def test_agent_masks_tool_results_and_blocks_write_back(tmp_path):
    (tmp_path / ".env").write_text(f"OPENAI_API_KEY={KEY}\nDEBUG=1\n", encoding="utf-8")
    agent, llm = make_agent(tmp_path, [
        reply(calls=[tool_call("r", "read_file", path=".env")]),
        reply(calls=[tool_call("w", "write_file", path=".env",
                               content=f"OPENAI_API_KEY={MARK}:openai-style]\nDEBUG=0\n")]),
        reply(calls=[tool_call("e", "edit_file", path=".env", old_string="DEBUG=1", new_string="DEBUG=0")]),
        reply("改好了"),
    ])
    agent.run("把 DEBUG 关掉")
    sent = "\n".join(str(m.get("content")) for m in llm.seen[-1])
    assert KEY not in sent and MARK in sent                  # 模型从没见过真正的密钥
    assert "不能把它写回文件" in llm.seen[2][-1]["content"]   # 整个文件重写被拒绝
    assert (tmp_path / ".env").read_text(encoding="utf-8") == f"OPENAI_API_KEY={KEY}\nDEBUG=0\n"  # 只改了不含密钥的行
