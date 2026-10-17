import argparse
import sys

from .core import Ledger, fmt, parse_amount


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ledger")
    p.add_argument("--file", default="ledger.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    for name in ("kind", "amount", "category", "date"):
        a.add_argument(name)
    a.add_argument("--note", default="")
    ls = sub.add_parser("list")
    ls.add_argument("--from", dest="start")
    ls.add_argument("--to", dest="end")
    ls.add_argument("--category")
    ls.add_argument("--kind")
    d = sub.add_parser("delete")
    d.add_argument("id", type=int)
    b = sub.add_parser("balance")
    b.add_argument("--from", dest="start")
    b.add_argument("--to", dest="end")
    r = sub.add_parser("report")
    r.add_argument("year", type=int)
    r.add_argument("month", type=int)
    bg = sub.add_parser("budget").add_subparsers(dest="bcmd", required=True)
    bs = bg.add_parser("set")
    bs.add_argument("category")
    bs.add_argument("amount")
    bst = bg.add_parser("status")
    bst.add_argument("year", type=int)
    bst.add_argument("month", type=int)
    e = sub.add_parser("export")
    e.add_argument("path")
    i = sub.add_parser("import")
    i.add_argument("path")
    args = p.parse_args(argv)
    lg = Ledger(args.file)
    try:
        if args.cmd == "add":
            print(f"已添加 #{lg.add(args.kind, args.amount, args.category, args.date, args.note)}")
        elif args.cmd == "list":
            rows = lg.list(args.start, args.end, args.category, args.kind)
            if not rows:
                print("（无记录）")
            for x in rows:
                line = f"#{x['id']} {x['date']} {x['kind']} {x['category']} {x['amount']}"
                print(line + (f" {x['note']}" if x["note"] else ""))
        elif args.cmd == "delete":
            lg.delete(args.id)
            print(f"已删除 #{args.id}")
        elif args.cmd == "balance":
            print(lg.balance(args.start, args.end))
        elif args.cmd == "report":
            rep = lg.monthly_report(args.year, args.month)
            print(f"收入 {rep['income']} 支出 {rep['expense']} 结余 {rep['net']}")
            for c in rep["by_category"]:
                print(f"{c['category']} {c['amount']}")
        elif args.cmd == "budget" and args.bcmd == "set":
            lg.set_budget(args.category, args.amount)
            print(f"已设置预算 {args.category.strip()} {fmt(parse_amount(args.amount))}")
        elif args.cmd == "budget":
            for s in lg.budget_status(args.year, args.month):
                print(f"{s['category']} 已用 {s['spent']} / 预算 {s['budget']}" + (" 超支" if s["over"] else ""))
        elif args.cmd == "export":
            print(f"已导出 {lg.export_csv(args.path)} 条")
        elif args.cmd == "import":
            print(f"已导入 {lg.import_csv(args.path)} 条")
    except KeyError as e:
        print(f"错误：记录不存在：{e.args[0]}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
