"""记账工具的核心实现：:class:`ledger.core.Ledger`。"""
from __future__ import annotations

import csv
import datetime
import json
import os
import re
import time
from decimal import Decimal

from .money import format_money, parse_amount

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_KINDS = ("income", "expense")
_CSV_HEADER = ["date", "kind", "category", "amount", "note"]


def _validate_kind(kind):
    if kind not in _KINDS:
        raise ValueError(f"非法类型: {kind!r}")
    return kind


def _validate_category(category):
    if not isinstance(category, str):
        raise ValueError(f"非法分类: {category!r}")
    category = category.strip()
    if not category:
        raise ValueError("分类不能为空")
    return category


def _validate_date(date):
    if not isinstance(date, str) or _DATE_RE.fullmatch(date) is None:
        raise ValueError(f"非法日期: {date!r}")
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise ValueError(f"非法日期: {date!r}") from None
    return date


class Ledger:
    """一个基于 JSON 文件的记账本。"""

    def __init__(self, path):
        self._path = os.fspath(path)
        self._next_id = 1
        self._records = {}   # id -> {"id","kind","amount"(Decimal),"category","date","note"}
        self._budgets = {}   # category -> Decimal
        self._history = []   # 仅存在内存中的撤销历史
        self._load()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return
        if not content.strip():
            return
        data = json.loads(content)
        self._next_id = int(data.get("next_id", 1))
        for rec in data.get("records", []):
            rec_id = int(rec["id"])
            self._records[rec_id] = {
                "id": rec_id,
                "kind": rec["kind"],
                "amount": Decimal(rec["amount"]),
                "category": rec["category"],
                "date": rec["date"],
                "note": rec.get("note", ""),
            }
        self._budgets = {
            category: Decimal(amount)
            for category, amount in data.get("budgets", {}).items()
        }

    def _save(self):
        data = {
            "next_id": self._next_id,
            "records": [
                {
                    "id": rec["id"],
                    "kind": rec["kind"],
                    "amount": format_money(rec["amount"]),
                    "category": rec["category"],
                    "date": rec["date"],
                    "note": rec["note"],
                }
                for rec in sorted(
                    self._records.values(), key=lambda r: (r["date"], r["id"])
                )
            ],
            "budgets": {
                category: format_money(amount)
                for category, amount in self._budgets.items()
            },
        }
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # 优先原子替换；Windows 上文件可能被索引/杀毒软件短暂占用，
        # 因此失败时重试几次，仍失败则退回就地写入。
        for attempt in range(5):
            try:
                os.replace(tmp, self._path)
                return
            except PermissionError:
                time.sleep(0.05 * (attempt + 1))
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        try:
            os.remove(tmp)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _public(rec):
        return {
            "id": rec["id"],
            "kind": rec["kind"],
            "amount": format_money(rec["amount"]),
            "category": rec["category"],
            "date": rec["date"],
            "note": rec["note"],
        }

    @staticmethod
    def _in_range(rec, start, end):
        if start is not None and rec["date"] < start:
            return False
        if end is not None and rec["date"] > end:
            return False
        return True

    # ------------------------------------------------------------------
    # 记录操作
    # ------------------------------------------------------------------
    def add(self, kind, amount, category, date, note=""):
        kind = _validate_kind(kind)
        amount = parse_amount(amount)
        category = _validate_category(category)
        date = _validate_date(date)
        if note is None:
            note = ""

        rec_id = self._next_id
        self._next_id += 1
        self._records[rec_id] = {
            "id": rec_id,
            "kind": kind,
            "amount": amount,
            "category": category,
            "date": date,
            "note": note,
        }
        self._history.append(("add", rec_id))
        self._save()
        return rec_id

    def get(self, id):
        if id not in self._records:
            raise KeyError(id)
        return self._public(self._records[id])

    def delete(self, id):
        if id not in self._records:
            raise KeyError(id)
        rec = self._records.pop(id)
        self._history.append(("delete", rec))
        self._save()

    def list(self, start=None, end=None, category=None, kind=None):
        result = [
            rec
            for rec in self._records.values()
            if self._in_range(rec, start, end)
            and (category is None or rec["category"] == category)
            and (kind is None or rec["kind"] == kind)
        ]
        result.sort(key=lambda r: (r["date"], r["id"]))
        return [self._public(r) for r in result]

    def search(self, keyword):
        keyword = keyword.lower()
        result = [
            rec
            for rec in self._records.values()
            if keyword in rec["note"].lower() or keyword in rec["category"].lower()
        ]
        result.sort(key=lambda r: (r["date"], r["id"]))
        return [self._public(r) for r in result]

    def balance(self, start=None, end=None):
        total = Decimal("0")
        for rec in self._records.values():
            if not self._in_range(rec, start, end):
                continue
            if rec["kind"] == "income":
                total += rec["amount"]
            else:
                total -= rec["amount"]
        return format_money(total)

    def monthly_report(self, year, month):
        prefix = f"{year:04d}-{month:02d}"
        income = Decimal("0")
        expense = Decimal("0")
        by_cat = {}
        for rec in self._records.values():
            if not rec["date"].startswith(prefix):
                continue
            if rec["kind"] == "income":
                income += rec["amount"]
            else:
                expense += rec["amount"]
                by_cat[rec["category"]] = by_cat.get(
                    rec["category"], Decimal("0")
                ) + rec["amount"]
        by_category = [
            {"category": category, "amount": format_money(amount)}
            for category, amount in sorted(
                by_cat.items(), key=lambda item: (-item[1], item[0])
            )
        ]
        return {
            "income": format_money(income),
            "expense": format_money(expense),
            "net": format_money(income - expense),
            "by_category": by_category,
        }

    # ------------------------------------------------------------------
    # 预算
    # ------------------------------------------------------------------
    def set_budget(self, category, amount):
        category = _validate_category(category)
        amount = parse_amount(amount)
        self._budgets[category] = amount
        self._save()

    def budget_status(self, year, month):
        prefix = f"{year:04d}-{month:02d}"
        spent = {}
        for rec in self._records.values():
            if rec["kind"] != "expense" or not rec["date"].startswith(prefix):
                continue
            spent[rec["category"]] = spent.get(
                rec["category"], Decimal("0")
            ) + rec["amount"]

        result = []
        for category in sorted(self._budgets):
            budget = self._budgets[category]
            used = spent.get(category, Decimal("0"))
            result.append(
                {
                    "category": category,
                    "budget": format_money(budget),
                    "spent": format_money(used),
                    "remaining": format_money(budget - used),
                    "over": used > budget,
                }
            )
        return result

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------
    def export_csv(self, path):
        records = sorted(
            self._records.values(), key=lambda r: (r["date"], r["id"])
        )
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(_CSV_HEADER)
            for rec in records:
                writer.writerow(
                    [
                        rec["date"],
                        rec["kind"],
                        rec["category"],
                        format_money(rec["amount"]),
                        rec["note"],
                    ]
                )
        return len(records)

    def import_csv(self, path):
        pending = []
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header != _CSV_HEADER:
                raise ValueError(
                    "表头不合法，应为 date,kind,category,amount,note"
                )
            for row in reader:
                line_no = reader.line_num
                if not row or all(cell.strip() == "" for cell in row):
                    continue
                if len(row) != 5:
                    raise ValueError(f"第 {line_no} 行格式不合法")
                date, kind, category, amount, note = row
                try:
                    kind_v = _validate_kind(kind)
                    amount_v = parse_amount(amount)
                    category_v = _validate_category(category)
                    date_v = _validate_date(date)
                except ValueError as exc:
                    raise ValueError(f"第 {line_no} 行不合法: {exc}") from None
                pending.append(
                    {
                        "kind": kind_v,
                        "amount": amount_v,
                        "category": category_v,
                        "date": date_v,
                        "note": note,
                    }
                )

        ids = []
        for rec in pending:
            rec_id = self._next_id
            self._next_id += 1
            rec["id"] = rec_id
            self._records[rec_id] = rec
            ids.append(rec_id)
        if ids:
            self._history.append(("import", ids))
            self._save()
        return len(ids)

    # ------------------------------------------------------------------
    # 撤销
    # ------------------------------------------------------------------
    def undo(self):
        if not self._history:
            return False
        op, payload = self._history.pop()
        if op == "add":
            self._records.pop(payload, None)
        elif op == "delete":
            self._records[payload["id"]] = payload
        elif op == "import":
            for rec_id in payload:
                self._records.pop(rec_id, None)
        self._save()
        return True
