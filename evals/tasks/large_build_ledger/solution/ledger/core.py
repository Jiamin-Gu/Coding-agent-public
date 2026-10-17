import csv
import json
from datetime import date as _date
from decimal import Decimal, InvalidOperation
from pathlib import Path

KINDS = ("income", "expense")
CENT = Decimal("0.01")
COLUMNS = ["date", "kind", "category", "amount", "note"]


def parse_amount(value) -> Decimal:
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValueError(f"金额不合法：{value}")
    if not d.is_finite() or d <= 0 or d != d.quantize(CENT):
        raise ValueError(f"金额必须是最多两位小数的正数：{value}")
    return d.quantize(CENT)


def parse_date(value) -> str:
    try:
        return _date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ValueError(f"日期不合法：{value}")


def fmt(d: Decimal) -> str:
    return f"{d.quantize(CENT):.2f}"


def make_record(kind, amount, category, date, note=""):
    if kind not in KINDS:
        raise ValueError(f"类型只能是 income 或 expense：{kind}")
    category = str(category).strip()
    if not category:
        raise ValueError("分类不能为空")
    return {"kind": kind, "amount": fmt(parse_amount(amount)), "category": category,
            "date": parse_date(date), "note": str(note or "")}


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self._records: dict[int, dict] = {}
        self._next_id = 1
        self._budgets: dict[str, str] = {}
        self._undo: list[tuple] = []
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._records = {r["id"]: r for r in data.get("records", [])}
            self._next_id = data.get("next_id", max(self._records, default=0) + 1)
            self._budgets = data.get("budgets", {})

    def _save(self):
        data = {"next_id": self._next_id, "records": [self._records[k] for k in sorted(self._records)],
                "budgets": self._budgets}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def _insert(self, rec) -> int:
        rid = self._next_id
        self._next_id += 1
        self._records[rid] = {"id": rid, **rec}
        return rid

    def add(self, kind, amount, category, date, note="") -> int:
        rid = self._insert(make_record(kind, amount, category, date, note))
        self._save()
        self._undo.append(("add", rid))
        return rid

    def get(self, rid) -> dict:
        if rid not in self._records:
            raise KeyError(rid)
        return dict(self._records[rid])

    def delete(self, rid) -> None:
        if rid not in self._records:
            raise KeyError(rid)
        rec = self._records.pop(rid)
        self._save()
        self._undo.append(("delete", rec))

    def _sorted(self, records):
        return [dict(r) for r in sorted(records, key=lambda r: (r["date"], r["id"]))]

    def list(self, start=None, end=None, category=None, kind=None) -> list:
        start = parse_date(start) if start else None
        end = parse_date(end) if end else None
        return self._sorted(r for r in self._records.values()
                            if (start is None or r["date"] >= start) and (end is None or r["date"] <= end)
                            and (category is None or r["category"] == category) and (kind is None or r["kind"] == kind))

    def search(self, keyword) -> list:
        kw = keyword.lower()
        return self._sorted(r for r in self._records.values() if kw in r["note"].lower() or kw in r["category"].lower())

    @staticmethod
    def _sum(records, kind):
        return sum((Decimal(r["amount"]) for r in records if r["kind"] == kind), Decimal("0"))

    def balance(self, start=None, end=None) -> str:
        records = self.list(start, end)
        return fmt(self._sum(records, "income") - self._sum(records, "expense"))

    def _month(self, year, month):
        prefix = f"{int(year):04d}-{int(month):02d}-"
        return [r for r in self._records.values() if r["date"].startswith(prefix)]

    def monthly_report(self, year, month) -> dict:
        records = self._month(year, month)
        income, expense = self._sum(records, "income"), self._sum(records, "expense")
        cats: dict[str, Decimal] = {}
        for r in records:
            if r["kind"] == "expense":
                cats[r["category"]] = cats.get(r["category"], Decimal("0")) + Decimal(r["amount"])
        by_cat = sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))
        return {"income": fmt(income), "expense": fmt(expense), "net": fmt(income - expense),
                "by_category": [{"category": c, "amount": fmt(a)} for c, a in by_cat]}

    def set_budget(self, category, amount) -> None:
        category = str(category).strip()
        if not category:
            raise ValueError("分类不能为空")
        self._budgets[category] = fmt(parse_amount(amount))
        self._save()

    def budget_status(self, year, month) -> list:
        records = self._month(year, month)
        out = []
        for cat in sorted(self._budgets):
            budget = Decimal(self._budgets[cat])
            spent = sum((Decimal(r["amount"]) for r in records if r["kind"] == "expense" and r["category"] == cat),
                        Decimal("0"))
            out.append({"category": cat, "budget": fmt(budget), "spent": fmt(spent),
                        "remaining": fmt(budget - spent), "over": spent > budget})
        return out

    def export_csv(self, path) -> int:
        rows = self.list()
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS)
            for r in rows:
                w.writerow([r[c] for c in COLUMNS])
        return len(rows)

    def import_csv(self, path) -> int:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None or [h.strip() for h in header] != COLUMNS:
                raise ValueError("第 1 行：表头必须是 " + ",".join(COLUMNS))
            pending = []
            for lineno, row in enumerate(reader, start=2):
                if not row or all(not c.strip() for c in row):
                    continue
                if len(row) != len(COLUMNS):
                    raise ValueError(f"第 {lineno} 行：列数不对")
                d = dict(zip(COLUMNS, row))
                try:
                    pending.append(make_record(d["kind"], d["amount"], d["category"], d["date"], d["note"]))
                except ValueError as e:
                    raise ValueError(f"第 {lineno} 行：{e}")
        ids = [self._insert(rec) for rec in pending]
        self._save()
        self._undo.append(("import", ids))
        return len(ids)

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
