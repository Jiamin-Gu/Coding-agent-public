"""ledger 核心逻辑：``ledger.Ledger``。

数据保存在一个 JSON 文件里，金额一律使用 :class:`decimal.Decimal` 计算，
对外返回时格式化为保留两位小数的字符串，保证没有浮点误差。
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date as _date
from decimal import Decimal, InvalidOperation
from pathlib import Path

_INCOME = "income"
_EXPENSE = "expense"
_KINDS = (_INCOME, _EXPENSE)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_CENT = Decimal("0.01")
_CSV_HEADER = ["date", "kind", "category", "amount", "note"]


def _fmt(amount: Decimal) -> str:
    """把金额格式化为保留两位小数的字符串。"""
    return str(amount.quantize(_CENT))


def _validate_kind(value) -> str:
    if value not in _KINDS:
        raise ValueError("kind 必须是 income 或 expense：%r" % (value,))
    return value


def _validate_amount(value) -> Decimal:
    """校验金额并返回量化到两位小数的 Decimal。"""
    if isinstance(value, bool):
        raise ValueError("金额不合法：%r" % (value,))
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("金额不合法：%r" % (value,))
        try:
            amount = Decimal(text)
        except InvalidOperation:
            raise ValueError("金额不合法：%r" % (value,)) from None
    else:
        raise ValueError("金额不合法：%r" % (value,))

    if not amount.is_finite():
        raise ValueError("金额不合法：%r" % (value,))
    try:
        quantized = amount.quantize(_CENT)
    except InvalidOperation:
        raise ValueError("金额不合法：%r" % (value,)) from None
    if quantized != amount:
        raise ValueError("金额最多两位小数：%r" % (value,))
    if quantized <= 0:
        raise ValueError("金额必须为正数：%r" % (value,))
    return quantized


def _validate_category(value) -> str:
    if not isinstance(value, str):
        raise ValueError("分类不合法：%r" % (value,))
    category = value.strip()
    if not category:
        raise ValueError("分类不能为空")
    return category


def _validate_date(value) -> str:
    if not isinstance(value, str):
        raise ValueError("日期不合法：%r" % (value,))
    if not _DATE_RE.fullmatch(value):
        raise ValueError("日期格式必须是 YYYY-MM-DD：%r" % (value,))
    try:
        _date.fromisoformat(value)
    except ValueError:
        raise ValueError("日期不合法：%r" % (value,)) from None
    return value


class Ledger:
    """一个保存在 JSON 文件里的记账本。"""

    def __init__(self, path):
        self.path = Path(path)
        self._records: dict = {}
        self._next_id = 1
        self._budgets: dict = {}
        self._undo: list = []
        self._load()

    # ------------------------------------------------------------------ 持久化
    def _load(self) -> None:
        if not self.path.exists():
            return
        text = self.path.read_text(encoding="utf-8")
        if not text.strip():
            return
        data = json.loads(text)
        for record in data.get("records", []):
            rid = int(record["id"])
            self._records[rid] = {
                "id": rid,
                "kind": record["kind"],
                "amount": Decimal(str(record["amount"])),
                "category": record["category"],
                "date": record["date"],
                "note": record.get("note", ""),
            }
        default_next = max(self._records) + 1 if self._records else 1
        self._next_id = int(data.get("next_id", default_next))
        self._budgets = {
            key: Decimal(str(value)) for key, value in data.get("budgets", {}).items()
        }

    def _save(self) -> None:
        data = {
            "next_id": self._next_id,
            "records": [
                {
                    "id": record["id"],
                    "kind": record["kind"],
                    "amount": _fmt(record["amount"]),
                    "category": record["category"],
                    "date": record["date"],
                    "note": record["note"],
                }
                for record in self._sorted()
            ],
            "budgets": {key: _fmt(value) for key, value in self._budgets.items()},
        }
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------ 内部工具
    @staticmethod
    def _public(record: dict) -> dict:
        return {
            "id": record["id"],
            "kind": record["kind"],
            "amount": _fmt(record["amount"]),
            "category": record["category"],
            "date": record["date"],
            "note": record["note"],
        }

    def _sorted(self) -> list:
        return sorted(self._records.values(), key=lambda r: (r["date"], r["id"]))

    @staticmethod
    def _as_id(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            raise KeyError(value) from None

    # ------------------------------------------------------------------ 增删查
    def add(self, kind, amount, category, date, note="") -> int:
        kind = _validate_kind(kind)
        amount = _validate_amount(amount)
        category = _validate_category(category)
        date = _validate_date(date)
        note = "" if note is None else str(note)

        rid = self._next_id
        self._next_id += 1
        self._records[rid] = {
            "id": rid,
            "kind": kind,
            "amount": amount,
            "category": category,
            "date": date,
            "note": note,
        }
        self._undo.append(("add", rid))
        self._save()
        return rid

    def get(self, id) -> dict:
        rid = self._as_id(id)
        if rid not in self._records:
            raise KeyError(rid)
        return self._public(self._records[rid])

    def delete(self, id) -> None:
        rid = self._as_id(id)
        if rid not in self._records:
            raise KeyError(rid)
        record = self._records.pop(rid)
        self._undo.append(("delete", record))
        self._save()

    def list(self, start=None, end=None, category=None, kind=None) -> list:
        result = []
        for record in self._sorted():
            if start is not None and record["date"] < start:
                continue
            if end is not None and record["date"] > end:
                continue
            if category is not None and record["category"] != category:
                continue
            if kind is not None and record["kind"] != kind:
                continue
            result.append(self._public(record))
        return result

    def search(self, keyword) -> list:
        needle = str(keyword).lower()
        result = []
        for record in self._sorted():
            if needle in record["note"].lower() or needle in record["category"].lower():
                result.append(self._public(record))
        return result

    # ------------------------------------------------------------------ 统计
    def balance(self, start=None, end=None) -> str:
        total = Decimal("0")
        for record in self._records.values():
            if start is not None and record["date"] < start:
                continue
            if end is not None and record["date"] > end:
                continue
            if record["kind"] == _INCOME:
                total += record["amount"]
            else:
                total -= record["amount"]
        return _fmt(total)

    def monthly_report(self, year, month) -> dict:
        prefix = "%04d-%02d-" % (int(year), int(month))
        income = Decimal("0")
        expense = Decimal("0")
        by_category: dict = {}
        for record in self._records.values():
            if not record["date"].startswith(prefix):
                continue
            if record["kind"] == _INCOME:
                income += record["amount"]
            else:
                expense += record["amount"]
                by_category[record["category"]] = (
                    by_category.get(record["category"], Decimal("0")) + record["amount"]
                )
        ordered = sorted(by_category.items(), key=lambda item: (-item[1], item[0]))
        return {
            "income": _fmt(income),
            "expense": _fmt(expense),
            "net": _fmt(income - expense),
            "by_category": [
                {"category": category, "amount": _fmt(amount)}
                for category, amount in ordered
            ],
        }

    # ------------------------------------------------------------------ 预算
    def set_budget(self, category, amount) -> None:
        category = _validate_category(category)
        amount = _validate_amount(amount)
        self._budgets[category] = amount
        self._save()

    def budget_status(self, year, month) -> list:
        prefix = "%04d-%02d-" % (int(year), int(month))
        spent: dict = {}
        for record in self._records.values():
            if record["kind"] != _EXPENSE:
                continue
            if not record["date"].startswith(prefix):
                continue
            spent[record["category"]] = (
                spent.get(record["category"], Decimal("0")) + record["amount"]
            )
        result = []
        for category in sorted(self._budgets):
            budget = self._budgets[category]
            used = spent.get(category, Decimal("0"))
            result.append(
                {
                    "category": category,
                    "budget": _fmt(budget),
                    "spent": _fmt(used),
                    "remaining": _fmt(budget - used),
                    "over": used > budget,
                }
            )
        return result

    # ------------------------------------------------------------------ CSV
    def export_csv(self, path) -> int:
        records = self._sorted()
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(_CSV_HEADER)
            for record in records:
                writer.writerow(
                    [
                        record["date"],
                        record["kind"],
                        record["category"],
                        _fmt(record["amount"]),
                        record["note"],
                    ]
                )
        return len(records)

    def import_csv(self, path) -> int:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))

        if not rows:
            raise ValueError("CSV 缺少表头")
        if rows[0] != _CSV_HEADER:
            raise ValueError(
                "CSV 表头必须是 date,kind,category,amount,note"
            )

        parsed = []
        for lineno, row in enumerate(rows[1:], start=2):
            if not row or all(field.strip() == "" for field in row):
                continue
            if len(row) != 5:
                raise ValueError("第 %d 行格式错误：需要 5 列" % lineno)
            raw_date, raw_kind, raw_category, raw_amount, raw_note = row
            try:
                kind = _validate_kind(raw_kind)
                amount = _validate_amount(raw_amount)
                category = _validate_category(raw_category)
                date = _validate_date(raw_date)
            except ValueError as exc:
                raise ValueError("第 %d 行数据不合法：%s" % (lineno, exc)) from None
            parsed.append((kind, amount, category, date, raw_note))

        new_ids = []
        for kind, amount, category, date, note in parsed:
            rid = self._next_id
            self._next_id += 1
            self._records[rid] = {
                "id": rid,
                "kind": kind,
                "amount": amount,
                "category": category,
                "date": date,
                "note": note,
            }
            new_ids.append(rid)

        if new_ids:
            self._undo.append(("import", new_ids))
            self._save()
        return len(parsed)

    # ------------------------------------------------------------------ 撤销
    def undo(self) -> bool:
        if not self._undo:
            return False
        action, payload = self._undo.pop()
        if action == "add":
            self._records.pop(payload, None)
        elif action == "delete":
            self._records[payload["id"]] = payload
        elif action == "import":
            for rid in payload:
                self._records.pop(rid, None)
        self._save()
        return True
