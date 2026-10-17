"""入口模块能被导入（防止只在启动时才暴露的语法错误）。"""
import importlib


def test_entrypoints_import():
    for name in ("coder.__main__", "coder.web.__main__", "coder.eval", "coder.replay", "coder.analyze",
                 "coder.sandbox", "coder.swebench", "coder.mcp", "coder.portforward"):
        importlib.import_module(name)
