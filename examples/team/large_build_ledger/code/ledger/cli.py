"""命令行入口：``python -m ledger [--file PATH] 子命令 ...``。

成功信息打印到标准输出并返回 0；出错时向标准错误打印一行
``错误：原因`` 并返回 1。
"""
from __future__ import annotations

import argparse
import sys

from ledger import Ledger
from ledger.money import format_money, parse_amount


class _CliError(Exception):
    """由自定义 ArgumentParser 抛出，用于取代 argparse 默认的 usage+退出码2。"""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _CliError(message)


def _build_parser():
    parser = _Parser(prog="ledger", description="一个基于 JSON 文件的记账工具")
    parser.add_argument(
        "--file",
        dest="data_file",
        default="ledger.json",
        metavar="PATH",
        help="数据文件路径",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="添加一条记录")
    p_add.add_argument("kind", help="income 或 expense")
    p_add.add_argument("amount")
    p_add.add_argument("category")
    p_add.add_argument("date", help="YYYY-MM-DD")
    p_add.add_argument("--note", default="")

    p_list = sub.add_parser("list", help="列出记录")
    p_list.add_argument("--from", dest="from", default=None)
    p_list.add_argument("--to", dest="to", default=None)
    p_list.add_argument("--category", default=None)
    p_list.add_argument("--kind", default=None)

    p_delete = sub.add_parser("delete", help="删除记录")
    p_delete.add_argument("id", type=int)

    p_balance = sub.add_parser("balance", help="显示余额")
    p_balance.add_argument("--from", dest="from", default=None)
    p_balance.add_argument("--to", dest="to", default=None)

    p_report = sub.add_parser("report", help="月度报表")
    p_report.add_argument("year", type=int)
    p_report.add_argument("month", type=int)

    p_budget = sub.add_parser("budget", help="预算")
    bsub = p_budget.add_subparsers(dest="budget_cmd", required=True)
    p_bset = bsub.add_parser("set", help="设置预算")
    p_bset.add_argument("category")
    p_bset.add_argument("amount")
    p_bstatus = bsub.add_parser("status", help="查看预算执行情况")
    p_bstatus.add_argument("year", type=int)
    p_bstatus.add_argument("month", type=int)

    p_export = sub.add_parser("export", help="导出 CSV")
    p_export.add_argument("file")

    p_import = sub.add_parser("import", help="导入 CSV")
    p_import.add_argument("file")

    return parser


def _print_error(message):
    print(f"错误：{message}", file=sys.stderr)


def _reason(exc):
    if isinstance(exc, KeyError):
        key = exc.args[0] if exc.args else ""
        return f"记录不存在: {key}"
    return str(exc)


def _cmd_add(ledger, args):
    rec_id = ledger.add(
        args.kind, args.amount, args.category, args.date, args.note
    )
    print(f"已添加 #{rec_id}")


def _cmd_list(ledger, args):
    records = ledger.list(
        start=getattr(args, "from"),
        end=args.to,
        category=args.category,
        kind=args.kind,
    )
    if not records:
        print("（无记录）")
        return
    for rec in records:
        line = (
            f"#{rec['id']} {rec['date']} {rec['kind']} "
            f"{rec['category']} {rec['amount']}"
        )
        if rec["note"]:
            line += f" {rec['note']}"
        print(line)


def _cmd_delete(ledger, args):
    ledger.delete(args.id)
    print(f"已删除 #{args.id}")


def _cmd_balance(ledger, args):
    print(ledger.balance(start=getattr(args, "from"), end=args.to))


def _cmd_report(ledger, args):
    report = ledger.monthly_report(args.year, args.month)
    print(
        f"收入 {report['income']} 支出 {report['expense']} "
        f"结余 {report['net']}"
    )
    for item in report["by_category"]:
        print(f"{item['category']} {item['amount']}")


def _cmd_budget_set(ledger, args):
    ledger.set_budget(args.category, args.amount)
    amount = format_money(parse_amount(args.amount))
    print(f"已设置预算 {args.category} {amount}")


def _cmd_budget_status(ledger, args):
    for item in ledger.budget_status(args.year, args.month):
        line = (
            f"{item['category']} 已用 {item['spent']} "
            f"/ 预算 {item['budget']}"
        )
        if item["over"]:
            line += " 超支"
        print(line)


def _cmd_export(ledger, args):
    count = ledger.export_csv(args.file)
    print(f"已导出 {count} 条")


def _cmd_import(ledger, args):
    count = ledger.import_csv(args.file)
    print(f"已导入 {count} 条")


def _dispatch(args):
    ledger = Ledger(args.data_file)

    if args.cmd == "add":
        _cmd_add(ledger, args)
    elif args.cmd == "list":
        _cmd_list(ledger, args)
    elif args.cmd == "delete":
        _cmd_delete(ledger, args)
    elif args.cmd == "balance":
        _cmd_balance(ledger, args)
    elif args.cmd == "report":
        _cmd_report(ledger, args)
    elif args.cmd == "budget":
        if args.budget_cmd == "set":
            _cmd_budget_set(ledger, args)
        else:
            _cmd_budget_status(ledger, args)
    elif args.cmd == "export":
        _cmd_export(ledger, args)
    elif args.cmd == "import":
        _cmd_import(ledger, args)
    else:  # pragma: no cover - argparse 已保证 cmd 合法
        raise _CliError(f"未知子命令: {args.cmd}")


def main(argv=None):
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _CliError as exc:
        _print_error(str(exc))
        return 1

    try:
        _dispatch(args)
    except _CliError as exc:
        _print_error(str(exc))
        return 1
    except (ValueError, KeyError, OSError) as exc:
        _print_error(_reason(exc))
        return 1
    return 0
