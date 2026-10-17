import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from . import providers

# 依次读取：当前目录的 .env、本项目根目录的 .env、~/.coder/.env（pip 安装后可以把配置放这里）
# load_dotenv 不覆盖已有的值，所以排在前面的优先
ENV_FILES = [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env",
             Path(os.getenv("CODER_HOME") or Path.home() / ".coder") / ".env"]
for _f in ENV_FILES:
    load_dotenv(_f)


@dataclass
class Config:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    provider: str = "deepseek"     # 服务商预设（见 providers.py），决定要不要加额外的请求头
    max_steps: int = 50            # 单次任务最多调用 LLM 的轮数，防止死循环
    max_tool_output: int = 12_000  # 单个工具结果最多返回给模型的字符数
    # 上下文超过这么多 token 才自动压缩；0 表示不压缩。现在的模型上下文窗口普遍是几十万 token 起步，
    # 压缩只是接近上限时的兜底：过早压缩要重读文件、让缓存失效，还可能记错东西
    context_limit: int = 200_000
    sandbox: bool = False          # 沙箱模式：命令在 Docker 容器里执行（见 sandbox.py）

    @classmethod
    def from_env(cls) -> "Config":
        base_url = os.getenv("CODER_BASE_URL", "")
        # 没写服务商时按接口地址判断，兼容旧配置
        provider = os.getenv("CODER_PROVIDER") or (providers.detect(base_url) if base_url else cls.provider)
        return cls(
            # 兼容旧变量名 DEEPSEEK_API_KEY
            api_key=os.getenv("CODER_API_KEY") or os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=base_url or providers.get(provider).base_url or cls.base_url,
            model=os.getenv("CODER_MODEL", cls.model),
            provider=provider,
            max_steps=int(os.getenv("CODER_MAX_STEPS", cls.max_steps)),
            context_limit=int(os.getenv("CODER_CONTEXT_LIMIT", cls.context_limit)),
            sandbox=os.getenv("CODER_SANDBOX", "").strip().lower() in ("1", "true", "docker", "on"),
        )


def settings_file() -> Path:
    """界面上保存的设置写到哪个 .env：已经在用的那个（按读取顺序的第一个），都没有就放 ~/.coder/.env。"""
    return next((f for f in ENV_FILES if f.is_file()), ENV_FILES[-1])


def save_settings(values: dict[str, str], path: Path | None = None) -> Path:
    """把设置写进 .env：已有的变量就地替换，没有的追加在末尾，注释和其他配置保持不变。同时更新当前进程的环境变量。"""
    path = path or settings_file()
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    remaining = dict(values)
    for i, line in enumerate(lines):
        m = re.match(r"\s*([A-Z_]+)\s*=", line)  # 注释掉的行不动
        if m and m.group(1) in remaining:
            lines[i] = f"{m.group(1)}={remaining.pop(m.group(1))}"
    lines += [f"{k}={v}" for k, v in remaining.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ.update(values)
    return path
