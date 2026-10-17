"""测试的公共设置。"""
import pytest


@pytest.fixture(autouse=True)
def _no_verify_on_stop(monkeypatch):
    """verify-on-stop（改了代码没验证就想结束时否决一次）默认开启；大多数测试测的是别的功能，
    脚本化的假模型写完代码就结束，这里关掉。专门测它的用例自己把 agent.verify_on_stop 设回 True。"""
    monkeypatch.setenv("CODER_VERIFY_ON_STOP", "0")
