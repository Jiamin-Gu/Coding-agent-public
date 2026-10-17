# 记账工具 ledger：需求文档

## 1. 概述

一个命令行记账工具，数据保存在一个 JSON 文件里。既可以作为 Python 包调用，也可以在命令行使用。

## 2. 交付物

- Python 包 `ledger/`（放在项目根目录），核心类 `ledger.Ledger`
- 命令行入口：`python -m ledger --file 数据文件 子命令 ...`
- `tests/` 下的 pytest 测试
- `README.md`：说明用法

## 3. 数据规则

- 每条记录有这些字段：
  - `id`：整数，从 1 开始递增；删除或撤销后**不会复用**
  - `kind`：`"income"`（收入）或 `"expense"`（支出）
  - `amount`：正数，最多两位小数
  - `category`：分类，非空字符串，去掉首尾空白后保存
  - `date`：`"YYYY-MM-DD"` 格式的合法日期
  - `note`：备注，可以为空
- 对外返回的记录是 dict，金额是保留两位小数的字符串，例如：
  `{"id": 1, "kind": "expense", "amount": "12.50", "category": "餐饮", "date": "2026-01-05", "note": "午饭"}`
- 金额计算必须精确，不能有浮点误差。所有返回的金额都是保留两位小数的字符串，例如 `"0.30"`、`"-12.00"`
- 参数不合法（kind、amount、category、date 不符合上面的规则）时抛出 `ValueError`
- 每次修改后立即保存到文件。用同一个文件重新创建 `Ledger`，能读到之前的记录、id 计数和预算（撤销历史不保存）
- 文件不存在时视为空账本

## 4. Python 接口：`ledger.Ledger`

- `Ledger(path)`：打开（或新建）数据文件
- `add(kind, amount, category, date, note="") -> int`：添加一条记录，返回 id。amount 可以是 str、int 或 Decimal
- `get(id) -> dict`：取一条记录；不存在时抛出 `KeyError`
- `delete(id) -> None`：删除一条记录；不存在时抛出 `KeyError`
- `list(start=None, end=None, category=None, kind=None) -> list[dict]`：按条件筛选（start、end 是包含边界的日期），按 `(date, id)` 升序
- `search(keyword) -> list[dict]`：备注或分类中包含关键字的记录（不区分大小写），按 `(date, id)` 升序
- `balance(start=None, end=None) -> str`：收入合计减支出合计（可以按日期范围）
- `monthly_report(year, month) -> dict`：某个月的报表：
  `{"income": "...", "expense": "...", "net": "...", "by_category": [{"category": "餐饮", "amount": "..."}, ...]}`
  其中 `net = income - expense`；`by_category` 只统计**支出**，按金额降序，金额相同时按分类名升序
- `set_budget(category, amount) -> None`：设置某个支出分类的每月预算（正数，最多两位小数）；再次设置会覆盖
- `budget_status(year, month) -> list[dict]`：每个设置了预算的分类一项：
  `{"category": ..., "budget": ..., "spent": ..., "remaining": ..., "over": bool}`
  `spent` 是该分类当月的支出合计，`remaining = budget - spent`（可以为负），`over` 表示 `spent > budget`；按分类名升序
- `export_csv(path) -> int`：导出全部记录（按 `(date, id)` 升序），返回导出的条数。CSV 使用 UTF-8 编码，有表头，列依次为 `date,kind,category,amount,note`
- `import_csv(path) -> int`：从同样格式的 CSV 导入，新记录分配新的 id，返回导入的条数。表头必须是上面的列名；空行忽略。**任意一行不合法时抛出 `ValueError`，错误信息里包含出错的行号（表头算第 1 行），并且一条都不导入**
- `undo() -> bool`：撤销最近一次 add、delete 或 import_csv（一次导入整体撤销）。可以连续撤销；没有可撤销的操作时返回 False。撤销历史只在当前 `Ledger` 对象里有效

## 5. 命令行

`python -m ledger [--file PATH] 子命令 ...`，`--file` 默认是 `ledger.json`。成功时退出码 0；出错时（参数不合法、记录不存在、导入失败等）在**标准错误**输出一行 `错误：原因`，退出码 1。

| 子命令 | 输出（标准输出） |
|---|---|
| `add KIND AMOUNT CATEGORY DATE [--note NOTE]` | `已添加 #ID` |
| `list [--from DATE] [--to DATE] [--category C] [--kind K]` | 每条记录一行：`#ID DATE KIND CATEGORY AMOUNT NOTE`，字段之间一个空格，备注为空时行尾没有空格；没有记录时输出 `（无记录）` |
| `delete ID` | `已删除 #ID` |
| `balance [--from DATE] [--to DATE]` | 余额，例如 `-12.50` |
| `report YEAR MONTH` | 第一行 `收入 X 支出 Y 结余 Z`，之后每个支出分类一行 `CATEGORY AMOUNT`（顺序同 by_category） |
| `budget set CATEGORY AMOUNT` | `已设置预算 CATEGORY AMOUNT`（金额保留两位小数） |
| `budget status YEAR MONTH` | 每个分类一行 `CATEGORY 已用 SPENT / 预算 BUDGET`，超支的行末尾再加 ` 超支` |
| `export FILE` | `已导出 N 条` |
| `import FILE` | `已导入 N 条` |
