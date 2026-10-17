import pytest

from inventory.cli import main
from inventory.reports import low_stock
from inventory.service import Inventory, InventoryError
from inventory.storage import Store


@pytest.fixture
def inv(tmp_path):
    return Inventory(Store(tmp_path / "inv.json"))


def test_add_receive_ship(inv):
    inv.add_item("A", "苹果", on_hand=5, reorder_level=2)
    inv.receive("A", 3)
    inv.ship("A", 4)
    assert inv.get("A").on_hand == 4
    with pytest.raises(InventoryError):
        inv.ship("A", 10)
    with pytest.raises(ValueError):
        inv.receive("A", 0)


def test_persistence(tmp_path):
    path = tmp_path / "inv.json"
    Inventory(Store(path)).add_item("A", "苹果", on_hand=5)
    assert Inventory(Store(path)).get("A").on_hand == 5


def test_low_stock(inv):
    inv.add_item("B", "香蕉", on_hand=1, reorder_level=2)
    inv.add_item("A", "苹果", on_hand=5, reorder_level=2)
    assert low_stock(inv) == ["B"]


def test_cli(tmp_path, capsys):
    path = tmp_path / "inv.json"
    assert main(["add", "A", "苹果", "--qty", "3", "--reorder", "5"], path=path) == 0
    assert main(["low"], path=path) == 0
    assert "A" in capsys.readouterr().out
    assert main(["ship", "A", "9"], path=path) == 1
