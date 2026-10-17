"""验收测试：S2 总体约定 + S3 异常体系（导入、继承关系、时间约定）。"""

from datetime import datetime

import pytest

from shopkit import Shop
from shopkit import (
    CouponError,
    NotFoundError,
    ShopError,
    StateError,
    StockError,
    ValidationError,
)


class FakeClock:
    """固定的本地时钟助手：返回固定 datetime，并记录被调用次数。"""

    def __init__(self, when=None):
        self.when = when if when is not None else datetime(2026, 3, 1, 9, 30, 0)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.when


# --- S3: 异常体系 ---------------------------------------------------------


def test_shop_error_inherits_exception():
    assert issubclass(ShopError, Exception)


@pytest.mark.parametrize(
    "exc",
    [ValidationError, NotFoundError, StockError, StateError, CouponError],
)
def test_all_business_errors_inherit_shop_error(exc):
    assert issubclass(exc, ShopError)


def test_business_error_classes_are_distinct():
    classes = [ValidationError, NotFoundError, StockError, StateError, CouponError]
    assert len(set(classes)) == len(classes)


def test_errors_importable_from_package_root():
    import shopkit

    for name in (
        "ShopError",
        "ValidationError",
        "NotFoundError",
        "StockError",
        "StateError",
        "CouponError",
    ):
        assert hasattr(shopkit, name)


def test_root_and_errors_module_expose_same_classes():
    from shopkit.errors import CouponError as C2
    from shopkit.errors import NotFoundError as N2
    from shopkit.errors import ShopError as S2
    from shopkit.errors import StateError as St2
    from shopkit.errors import StockError as Sk2
    from shopkit.errors import ValidationError as V2

    assert ShopError is S2
    assert ValidationError is V2
    assert NotFoundError is N2
    assert StockError is Sk2
    assert StateError is St2
    assert CouponError is C2


def test_shop_error_is_catchable_as_exception():
    with pytest.raises(Exception):
        raise ValidationError("bad")


# --- S2: 时间约定 ---------------------------------------------------------


def test_default_clock_uses_now_and_formats_seconds():
    shop = Shop()
    now = shop._now()
    assert isinstance(now, str)
    # clock().isoformat(timespec="seconds") -> "2026-03-01T09:30:00"
    assert len(now) == 19
    assert now[10] == "T"
    datetime.fromisoformat(now)


def test_injected_clock_is_used_for_now():
    clock = FakeClock(datetime(2026, 3, 1, 9, 30, 0))
    shop = Shop(clock=clock)
    assert shop._now() == "2026-03-01T09:30:00"


def test_clock_called_on_each_now():
    clock = FakeClock(datetime(2026, 3, 1, 9, 30, 0))
    shop = Shop(clock=clock)
    shop._now()
    shop._now()
    assert clock.calls == 2


def test_money_helpers_importable_from_money_module():
    from shopkit.money import format_money, parse_money, round_money

    assert callable(parse_money)
    assert callable(round_money)
    assert callable(format_money)
