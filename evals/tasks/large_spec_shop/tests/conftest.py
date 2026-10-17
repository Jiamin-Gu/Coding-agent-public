from datetime import datetime

import pytest

from shopkit import Shop


class Clock:
    """可控的时钟：测试里手动拨时间。"""

    def __init__(self, now="2026-03-01T09:00:00"):
        self.now = datetime.fromisoformat(now)

    def set(self, value):
        self.now = datetime.fromisoformat(value)

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def shop(clock):
    return Shop(clock=clock)


@pytest.fixture
def stocked(shop):
    """三个商品：两个 food、一个 book，各有库存。"""
    shop.add_product("APPLE", "苹果", "3.50", "Food")
    shop.add_product("MILK", "牛奶", "12", "food")
    shop.add_product("BOOK-1", "Python 入门", "59.90", " Book ")
    shop.receive("APPLE", 100)
    shop.receive("MILK", 20)
    shop.receive("BOOK-1", 5)
    return shop
