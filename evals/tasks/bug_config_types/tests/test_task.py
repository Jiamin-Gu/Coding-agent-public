import subprocess
import sys

from app import settings
from app.pagination import paginate
from app.server import startup_messages


def test_defaults_have_right_types(monkeypatch):
    for name in ("APP_PAGE_SIZE", "APP_DEBUG", "APP_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    assert settings.get("page_size") == 20
    assert settings.get("timeout") == 5
    assert settings.get("debug") is False
    assert paginate(list(range(100)), 2) == list(range(20, 40))
    assert startup_messages() == ["server started"]


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("APP_PAGE_SIZE", "5")
    monkeypatch.setenv("APP_DEBUG", "TRUE")
    assert paginate(list(range(100)), 1) == [0, 1, 2, 3, 4]
    assert startup_messages() == ["server started", "debug mode on"]
    monkeypatch.setenv("APP_DEBUG", "no")
    assert startup_messages() == ["server started"]


def test_demo_runs():
    proc = subprocess.run([sys.executable, "-m", "app.demo"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
