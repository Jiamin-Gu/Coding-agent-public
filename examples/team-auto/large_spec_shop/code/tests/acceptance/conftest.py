import sys
from datetime import datetime
from pathlib import Path

import pytest

# Make the workspace root importable so `import shopkit` works when pytest is
# invoked from the repository root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shopkit import Shop  # noqa: E402


class FakeClock:
    def __init__(self, when):
        self.when = when

    def __call__(self):
        return self.when

    def set(self, when):
        self.when = when


@pytest.fixture
def clock():
    return FakeClock(datetime(2026, 3, 1, 9, 30, 0))


@pytest.fixture
def shop(clock):
    return Shop(clock=clock)
