"""冒烟测试（CD 流水线用）：在一个全新的虚拟环境里装好打出来的安装包之后运行，确认装出来的东西能用。

只检查"包装对了没有"：模块都能导入、数据文件（网页、沙箱镜像的 Dockerfile）都打进了包里、命令行入口存在。
功能本身由测试负责（CI）。要在仓库目录以外运行，免得导入的是仓库里的源码而不是装好的包。
"""
import shutil
import sys
from pathlib import Path

import coder
from coder.agent import Agent  # noqa: F401
from coder.mcp import MCPManager  # noqa: F401
from coder.shadow import Shadow  # noqa: F401
from coder.tools import build_tools  # noqa: F401
from coder.web import server  # noqa: F401  网页服务和它依赖的会话管理都能导入

pkg = Path(coder.__file__).resolve().parent
problems = []
if "site-packages" not in str(pkg) and "dist-packages" not in str(pkg):
    problems.append(f"导入的不是装好的包：{pkg}")
for f in ("web/static/index.html", "web/static/app.js", "web/static/style.css", "sandbox_image/Dockerfile"):
    if not (pkg / f).is_file():
        problems.append(f"{f} 没打进包里")
for cmd in ("coder", "coder-web", "coder-eval"):
    if not shutil.which(cmd):
        problems.append(f"命令行入口 {cmd} 没有装上")

if problems:
    print("冒烟测试没通过：\n- " + "\n- ".join(problems))
    sys.exit(1)
print(f"冒烟测试通过：coder {coder.__version__}，装在 {pkg}")
