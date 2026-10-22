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
NEWEST_TESTED = (3, 13)  # CI 上测试过的最新版本；更新的版本刚发布时，有的依赖可能还没有对应的安装包
RECOMMENDED = "3.12"
BUILD_FAILED = ("Failed to build", "Failed building wheel", "Microsoft Visual C++", "error: subprocess-exited-with-error")
DEPS = ["fastapi", "uvicorn", "openai", "dotenv"]


def python(*args: str, quiet: bool = False) -> int:
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL} if quiet else {}
    return subprocess.call([sys.executable, *args], cwd=ROOT, **kw)


def install(requirements: str) -> tuple[int, str]:
    """pip install，输出照常显示，同时留一份用来判断失败原因。"""
    proc = subprocess.Popen([sys.executable, "-m", "pip", "install", "-r", requirements], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    lines = []
    for line in proc.stdout:
        print(line, end="")
        lines.append(line)
    return proc.wait(), "".join(lines)


def explain_failure(output: str) -> None:
    if any(s in output for s in BUILD_FAILED):
        print("\n[错误] 有依赖包需要在这台电脑上从源码编译，但没有编译工具，所以装不上。")
        if sys.version_info[:2] > NEWEST_TESTED:
            print(f"原因是 Python 版本太新（当前 {platform.python_version()}）：新版本刚发布时，一些依赖包还没有提供对应的安装包，"
                  "pip 只能尝试从源码编译。")
        print(f"解决办法：安装 Python {RECOMMENDED}（https://www.python.org/downloads/，可以和现在的版本共存，安装时勾选 Add python.exe to PATH），"
              "删掉本目录下的 .venv 文件夹（如果有），再重新运行。")
        return
    print("\n[错误] 依赖安装失败，请检查网络后重试。国内网络可以改用镜像：")
    print(f"  {sys.executable} -m pip install -r requirements.txt -i {MIRROR}")


def main() -> int:
    if sys.version_info < (3, 10):
        print(f"[错误] Python 版本太低，需要 3.10 或更高版本，当前是 {platform.python_version()}。")
        print("请从 https://www.python.org/downloads/ 安装新版本后重新运行。")
        return 1
    if sys.version_info[:2] > NEWEST_TESTED:
        print(f"[提示] 当前 Python {platform.python_version()} 比本项目测试过的版本（3.10～{NEWEST_TESTED[0]}.{NEWEST_TESTED[1]}）新。"
              f"新版本刚发布时，个别依赖可能还没有对应的安装包；如果下面安装失败，请改用 Python {RECOMMENDED}。\n")
    if python("-c", "import " + ", ".join(DEPS), quiet=True):
        print("第一次运行，正在安装依赖，请稍候……")
        code, output = install("requirements.txt")
        if code:
            explain_failure(output)
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
