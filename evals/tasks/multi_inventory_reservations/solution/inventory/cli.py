import argparse

from .reports import low_stock
from .service import Inventory, InventoryError
from .storage import Store


def main(argv=None, path="inventory.json"):
    parser = argparse.ArgumentParser(prog="inventory")
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("id")
    a.add_argument("name")
    a.add_argument("--qty", type=int, default=0)
    a.add_argument("--reorder", type=int, default=0)
    r = sub.add_parser("receive")
    r.add_argument("id")
    r.add_argument("qty", type=int)
    s = sub.add_parser("ship")
    s.add_argument("id")
    s.add_argument("qty", type=int)
    sub.add_parser("low")
    rv = sub.add_parser("reserve")
    rv.add_argument("order_id")
    rv.add_argument("id")
    rv.add_argument("qty", type=int)
    rl = sub.add_parser("release")
    rl.add_argument("order_id")
    ff = sub.add_parser("fulfill")
    ff.add_argument("order_id")
    args = parser.parse_args(argv)
    inv = Inventory(Store(path))
    try:
        if args.cmd == "add":
            inv.add_item(args.id, args.name, args.qty, args.reorder)
        elif args.cmd == "receive":
            inv.receive(args.id, args.qty)
        elif args.cmd == "ship":
            inv.ship(args.id, args.qty)
        elif args.cmd == "low":
            print("\n".join(low_stock(inv)) or "（无）")
        elif args.cmd == "reserve":
            inv.reserve(args.order_id, args.id, args.qty)
        elif args.cmd == "release":
            inv.release(args.order_id)
        elif args.cmd == "fulfill":
            inv.fulfill(args.order_id)
    except (InventoryError, ValueError) as e:
        print(f"错误：{e}")
        return 1
    return 0
