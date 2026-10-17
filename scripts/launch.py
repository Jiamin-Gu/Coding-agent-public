"""一键启动（start.bat / start.sh 调用）：检查 Python 版本、第一次运行时安装依赖、创建配置文件，然后启动网页。

只用标准库（这时依赖可能还没装）。中文提示都从这里输出：Windows 批处理文件里写中文，cmd 执行完外部程序后
会从错误的位置接着读文件，把中文行截断成乱码，所以 start.bat 里只留英文。
参数原样交给 coder.web，比如工作区路径（把文件夹拖到 start.bat 上）、--demo。
"""
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
DEPS = ["fastapi", "uvicorn", "openai", "dotenv"]


def python(*args: str, quiet: bool = False) -> int:
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL} if quiet else {}
    return subprocess.call([sys.executable, *args], cwd=ROOT, **kw)


def main() -> int:
    if sys.version_info < (3, 10):
        print(f"[错误] Python 版本太低，需要 3.10 或更高版本，当前是 {platform.python_version()}。")
        print("请从 https://www.python.org/downloads/ 安装新版本后重新运行。")
        return 1
    if python("-c", "import " + ", ".join(DEPS), quiet=True):
        print("第一次运行，正在安装依赖，请稍候……")
        if python("-m", "pip", "install", "-r", "requirements.txt"):
            print("\n[错误] 依赖安装失败，请检查网络后重试。国内网络可以改用镜像：")
            print(f"  {sys.executable} -m pip install -r requirements.txt -i {MIRROR}")
            return 1
    env = ROOT / ".env"
    if not env.exists() and (ROOT / ".env.example").exists():
        shutil.copy(ROOT / ".env.example", env)
        print("第一次使用：浏览器打开后会弹出「模型设置」，选择服务商、填写 API Key 即可。")
        print("暂时没有 API Key 的话，可以先体验演示模式：start.bat --demo（macOS / Linux：bash start.sh --demo）\n")
    print("正在启动 coder，浏览器会自动打开。关闭这个窗口即可停止服务。\n")
    return python("-m", "coder.web", *sys.argv[1:])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
