from datetime import datetime

import pytest

from shopkit import Shop


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def set(self, now):
        self.now = now


@pytest.fixture
def clock():
    return Clock(datetime(2026, 3, 1, 9, 30, 0))


@pytest.fixture
def shop(clock):
    return Shop(clock=clock)
