import json

import pytest

from inventory.cli import main
from inventory.reports import low_stock
from inventory.service import Inventory, InventoryError
from inventory.storage import Store


@pytest.fixture
def path(tmp_path):
    return tmp_path / "inv.json"


@pytest.fixture
def inv(path):
    inv = Inventory(Store(path))
    inv.add_item("A", "苹果", on_hand=10, reorder_level=3)
    inv.add_item("B", "香蕉", on_hand=5, reorder_level=1)
    return inv


def test_reserve_reduces_available_not_on_hand(inv):
    inv.reserve("o1", "A", 4)
    assert inv.available("A") == 6 and inv.get("A").on_hand == 10


def test_reserve_accumulates_and_multiple_items(inv):
    inv.reserve("o1", "A", 2)
    inv.reserve("o1", "A", 3)
    inv.reserve("o1", "B", 1)
    inv.reserve("o2", "A", 1)
    assert inv.available("A") == 4 and inv.available("B") == 4


def test_reserve_errors(inv):
    with pytest.raises(InventoryError):
        inv.reserve("o1", "A", 11)
    inv.reserve("o1", "A", 8)
    with pytest.raises(InventoryError):
        inv.reserve("o2", "A", 3)          # 只剩 2 个可用
    with pytest.raises(ValueError):
        inv.reserve("o3", "A", 0)
    with pytest.raises(InventoryError):
        inv.reserve("o3", "ZZZ", 1)
    assert inv.available("A") == 2       # 失败的预留不留下痕迹


def test_release(inv):
    inv.reserve("o1", "A", 4)
    inv.reserve("o1", "B", 2)
    inv.release("o1")
    assert inv.available("A") == 10 and inv.available("B") == 5
    with pytest.raises(InventoryError):
        inv.release("o1")


def test_fulfill(inv):
    inv.reserve("o1", "A", 4)
    inv.reserve("o2", "A", 1)
    inv.fulfill("o1")
    assert inv.get("A").on_hand == 6 and inv.available("A") == 5
    with pytest.raises(InventoryError):
        inv.fulfill("o1")


def test_ship_respects_reservations(inv):
    inv.reserve("o1", "A", 8)
    with pytest.raises(InventoryError):
        inv.ship("A", 3)
    inv.ship("A", 2)
    assert inv.get("A").on_hand == 8 and inv.available("A") == 0


def test_low_stock_uses_available(inv):
    assert low_stock(inv) == []
    inv.reserve("o1", "A", 7)            # 可用 3 <= 补货线 3
    assert low_stock(inv) == ["A"]


def test_reservations_persist(path, inv):
    inv.reserve("o1", "A", 4)
    again = Inventory(Store(path))
    assert again.available("A") == 6
    again.fulfill("o1")
    assert Inventory(Store(path)).get("A").on_hand == 6


def test_old_format_file(path):
    path.write_text(json.dumps({"items": [{"id": "A", "name": "苹果", "on_hand": 3, "reorder_level": 0}]}),
                    encoding="utf-8")
    inv = Inventory(Store(path))
    assert inv.available("A") == 3
    inv.reserve("o1", "A", 1)
    assert Inventory(Store(path)).available("A") == 2


def test_cli_commands(path, capsys):
    assert main(["add", "A", "苹果", "--qty", "5"], path=path) == 0
    assert main(["reserve", "o1", "A", "3"], path=path) == 0
    assert main(["reserve", "o2", "A", "3"], path=path) == 1
    assert "错误" in capsys.readouterr().out
    assert main(["fulfill", "o1"], path=path) == 0
    assert Inventory(Store(path)).get("A").on_hand == 2
    assert main(["reserve", "o3", "A", "2"], path=path) == 0
    assert main(["release", "o3"], path=path) == 0
    assert main(["release", "o3"], path=path) == 1
    assert Inventory(Store(path)).available("A") == 2
