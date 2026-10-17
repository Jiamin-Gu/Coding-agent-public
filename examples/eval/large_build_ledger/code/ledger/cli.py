"""命令行入口：``python -m ledger``。"""

from __future__ import annotations

import argparse
import sys

from .core import Ledger, _fmt, _validate_amount, _validate_category


class _ArgumentParser(argparse.ArgumentParser):
    """参数出错时也统一输出 ``错误：...`` 并返回退出码 1。"""

    def error(self, message):
        sys.stderr.write("错误：%s\n" % message)
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="ledger", description="命令行记账工具")
    parser.add_argument(
        "--file",
        dest="ledger_file",
        default="ledger.json",
        help="数据文件（默认 ledger.json）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="添加一条记录")
    p_add.add_argument("kind", help="income 或 expense")
    p_add.add_argument("amount", help="正数，最多两位小数")
    p_add.add_argument("category", help="分类")
    p_add.add_argument("date", help="日期 YYYY-MM-DD")
    p_add.add_argument("--note", default="", help="备注")

    p_list = sub.add_parser("list", help="列出记录")
    p_list.add_argument("--from", dest="start", default=None, help="起始日期（含）")
    p_list.add_argument("--to", dest="end", default=None, help="结束日期（含）")
    p_list.add_argument("--category", default=None, help="按分类筛选")
    p_list.add_argument("--kind", default=None, help="按类型筛选")

    p_delete = sub.add_parser("delete", help="删除一条记录")
    p_delete.add_argument("id", type=int, help="记录 id")

    p_balance = sub.add_parser("balance", help="余额")
    p_balance.add_argument("--from", dest="start", default=None, help="起始日期（含）")
    p_balance.add_argument("--to", dest="end", default=None, help="结束日期（含）")

    p_report = sub.add_parser("report", help="月度报表")
    p_report.add_argument("year", type=int)
    p_report.add_argument("month", type=int)

    p_budget = sub.add_parser("budget", help="预算")
    budget_sub = p_budget.add_subparsers(dest="budget_command", required=True)
    p_budget_set = budget_sub.add_parser("set", help="设置预算")
    p_budget_set.add_argument("category")
    p_budget_set.add_argument("amount")
    p_budget_status = budget_sub.add_parser("status", help="查看预算使用情况")
    p_budget_status.add_argument("year", type=int)
    p_budget_status.add_argument("month", type=int)

    p_export = sub.add_parser("export", help="导出 CSV")
    p_export.add_argument("file", help="导出的 CSV 文件")

    p_import = sub.add_parser("import", help="导入 CSV")
    p_import.add_argument("file", help="要导入的 CSV 文件")

    return parser


def _dispatch(args) -> None:
    ledger = Ledger(args.ledger_file)
    command = args.command

    if command == "add":
        rid = ledger.add(
            args.kind, args.amount, args.category, args.date, note=args.note
        )
        print("已添加 #%d" % rid)

    elif command == "list":
        records = ledger.list(
            start=args.start, end=args.end, category=args.category, kind=args.kind
        )
        if not records:
            print("（无记录）")
        else:
            for record in records:
                fields = [
                    "#%d" % record["id"],
                    record["date"],
                    record["kind"],
                    record["category"],
                    record["amount"],
                ]
                if record["note"]:
                    fields.append(record["note"])
                print(" ".join(fields))

    elif command == "delete":
        ledger.delete(args.id)
        print("已删除 #%d" % args.id)

    elif command == "balance":
        print(ledger.balance(args.start, args.end))

    elif command == "report":
        report = ledger.monthly_report(args.year, args.month)
        print(
            "收入 %s 支出 %s 结余 %s"
            % (report["income"], report["expense"], report["net"])
        )
        for item in report["by_category"]:
            print("%s %s" % (item["category"], item["amount"]))

    elif command == "budget":
        if args.budget_command == "set":
            category = _validate_category(args.category)
            amount = _validate_amount(args.amount)
            ledger.set_budget(category, amount)
            print("已设置预算 %s %s" % (category, _fmt(amount)))
        else:
            for item in ledger.budget_status(args.year, args.month):
                line = "%s 已用 %s / 预算 %s" % (
                    item["category"],
                    item["spent"],
                    item["budget"],
                )
                if item["over"]:
                    line += " 超支"
                print(line)

    elif command == "export":
        count = ledger.export_csv(args.file)
        print("已导出 %d 条" % count)

    elif command == "import":
        count = ledger.import_csv(args.file)
        print("已导入 %d 条" % count)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _dispatch(args)
    except KeyError as exc:
        identifier = exc.args[0] if exc.args else ""
        sys.stderr.write("错误：记录不存在：#%s\n" % identifier)
        return 1
    except (ValueError, OSError) as exc:
        sys.stderr.write("错误：%s\n" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
