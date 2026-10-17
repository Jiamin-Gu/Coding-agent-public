# ledger 记账工具

`ledger` 是一个简单的命令行记账工具，数据保存在一个 JSON 文件里。它既可以作为 Python 包调用，也可以在命令行使用。

金额计算全部使用 `decimal.Decimal` 精确完成，避免浮点误差；对外返回的金额一律是保留两位小数的字符串，例如 `"0.30"`、`"-12.00"`、`"100.00"`。

## 功能概览

- 添加、查看、删除记录（收入 / 支出）
- 按日期、分类、类型筛选，按关键字搜索
- 统计余额、生成月度报表（按分类汇总支出）
- 设置分类月度预算并查看使用情况
- 导出 / 导入 CSV
- 撤销最近一次添加、删除或导入

## 安装

需要 Python 3.8 或更高版本。

直接使用源码即可（无需安装，在项目根目录运行）：

```bash
python -m ledger --help
```

或安装到当前环境：

```bash
python -m pip install .
```

安装测试依赖（运行 pytest 用）：

```bash
python -m pip install ".[test]"
```

## Python 包用法

```python
from decimal import Decimal
from ledger import Ledger

l = Ledger("ledger.json")          # 文件不存在时视为空账本

# 添加记录，返回自增 id（从 1 开始，删除/撤销后不复用）
id1 = l.add("expense", "12.50", "餐饮", "2026-01-05", "午饭")  # -> 1
id2 = l.add("income", 100, "工资", "2026-01-01")               # amount 可为 int
id3 = l.add("income", Decimal("0.3"), "工资", "2026-01-02")    # 也接受 Decimal

l.get(id1)
# {'id': 1, 'kind': 'expense', 'amount': '12.50', 'category': '餐饮',
#  'date': '2026-01-05', 'note': '午饭'}

l.list()                                   # 全部记录，按 (date, id) 升序
l.list(start="2026-01-01", end="2026-01-31")   # 日期范围（含边界）
l.list(category="餐饮", kind="expense")         # 精确匹配分类和类型
l.search("午饭")                            # 备注或分类包含关键字（不区分大小写）

l.balance()                                # '87.80' 收入合计减支出合计
l.balance(start="2026-01-01", end="2026-01-31")

l.monthly_report(2026, 1)
# {'income': '100.30', 'expense': '12.50', 'net': '87.80',
#  'by_category': [{'category': '餐饮', 'amount': '12.50'}]}

l.set_budget("餐饮", "50.00")              # 设置分类月度预算，重复设置会覆盖
l.budget_status(2026, 1)
# [{'category': '餐饮', 'budget': '50.00', 'spent': '12.50',
#   'remaining': '37.50', 'over': False}]

l.delete(id1)                              # 删除记录，不存在时抛 KeyError

l.export_csv("out.csv")                    # 导出全部记录，返回条数
l.import_csv("in.csv")                     # 导入记录，返回条数

l.undo()                                   # 撤销最近一次 add / delete / import_csv
```

### 方法说明

| 方法 | 说明 |
|---|---|
| `Ledger(path)` | 打开（或新建）数据文件，`path` 为 `str` 或 `os.PathLike`，UTF-8 编码 |
| `add(kind, amount, category, date, note="") -> int` | 添加一条记录并返回 id。`kind` 只能是 `"income"` 或 `"expense"`；`amount` 为正数、最多两位小数，可为 `str` / `int` / `Decimal`；`category` 非空（保存时去掉首尾空白）；`date` 为 `"YYYY-MM-DD"` 的合法日期 |
| `get(id) -> dict` | 返回一条记录，不存在时抛 `KeyError` |
| `delete(id) -> None` | 删除一条记录，不存在时抛 `KeyError` |
| `list(start=None, end=None, category=None, kind=None) -> list[dict]` | 按条件筛选（`start`/`end` 含边界），按 `(date, id)` 升序 |
| `search(keyword) -> list[dict]` | 备注或分类包含关键字（不区分大小写）的记录，按 `(date, id)` 升序 |
| `balance(start=None, end=None) -> str` | 收入合计减支出合计，返回两位小数字符串，无记录时 `"0.00"` |
| `monthly_report(year, month) -> dict` | 月度报表，`by_category` 只统计支出，按金额降序、金额相同按分类名升序 |
| `set_budget(category, amount) -> None` | 设置分类月度预算（正数、最多两位小数），重复设置覆盖 |
| `budget_status(year, month) -> list[dict]` | 每个已设预算分类的使用情况，按分类名升序 |
| `export_csv(path) -> int` | 导出全部记录为 UTF-8 CSV，返回条数 |
| `import_csv(path) -> int` | 从 CSV 导入，新记录分配新 id，返回条数；任一行不合法则抛 `ValueError` 且一条都不导入 |
| `undo() -> bool` | 撤销最近一次 `add` / `delete` / `import_csv`，无操作可撤销时返回 `False` |

参数不合法时抛 `ValueError`，记录不存在时抛 `KeyError`。

## 命令行用法

```
python -m ledger [--file PATH] 子命令 ...
```

`--file` 指定数据文件，默认是 `ledger.json`，必须写在子命令之前。成功时退出码为 `0`；出错时在**标准错误**输出一行 `错误：原因`，退出码为 `1`。

### add

```console
$ python -m ledger add expense 12.50 餐饮 2026-01-05 --note 午饭
已添加 #1
```

### list

```console
$ python -m ledger list
#2 2026-01-01 income 工资 100.00
#1 2026-01-05 expense 餐饮 12.50 午饭
```

每条记录一行 `#ID DATE KIND CATEGORY AMOUNT NOTE`，字段之间一个空格，备注为空时行尾没有空格。没有记录时输出：

```console
$ python -m ledger list
（无记录）
```

支持筛选：`--from DATE`、`--to DATE`、`--category C`、`--kind K`。

```console
$ python -m ledger list --kind income
$ python -m ledger list --from 2026-01-01 --to 2026-01-31
```

### delete

```console
$ python -m ledger delete 1
已删除 #1
```

### balance

```console
$ python -m ledger balance
-12.50
```

支持 `--from DATE`、`--to DATE`。

### report

```console
$ python -m ledger report 2026 1
收入 100.00 支出 50.00 结余 50.00
餐饮 30.00
交通 20.00
```

第一行为 `收入 X 支出 Y 结余 Z`，之后每个支出分类一行 `CATEGORY AMOUNT`（顺序同 `monthly_report` 的 `by_category`）。

### budget set

```console
$ python -m ledger budget set 餐饮 50.00
已设置预算 餐饮 50.00
```

### budget status

```console
$ python -m ledger budget status 2026 1
餐饮 已用 30.00 / 预算 50.00
```

超支的行末尾会追加 ` 超支`：

```console
$ python -m ledger budget status 2026 1
餐饮 已用 30.00 / 预算 20.00 超支
```

### export

```console
$ python -m ledger export out.csv
已导出 1 条
```

### import

```console
$ python -m ledger import in.csv
已导入 1 条
```

## 数据文件格式

数据文件是 UTF-8 编码的 JSON，结构如下：

```json
{
  "next_id": 3,
  "records": [
    {
      "id": 1,
      "kind": "expense",
      "amount": "12.50",
      "category": "餐饮",
      "date": "2026-01-05",
      "note": "午饭"
    },
    {
      "id": 2,
      "kind": "income",
      "amount": "100.00",
      "category": "工资",
      "date": "2026-01-01",
      "note": ""
    }
  ],
  "budgets": {
    "餐饮": "50.00"
  }
}
```

各字段含义：

- `next_id`：下一个要分配的 id，从 1 开始，每次分配后加 1；删除或撤销都不会回退，也不会复用 id。
- `records`：记录列表。
  - `id`：整数。
  - `kind`：`"income"`（收入）或 `"expense"`（支出）。
  - `amount`：正数，字符串形式，最多两位小数。
  - `category`：分类，非空字符串。
  - `date`：`"YYYY-MM-DD"` 格式的合法日期。
  - `note`：备注，可以为空字符串。
- `budgets`：分类到月度预算金额（字符串）的映射。

每次修改后都会立即写入文件，用同一个文件重新创建 `Ledger` 即可读回记录、id 计数和预算（撤销历史不保存）。文件不存在或为空时视为空账本。

### CSV 格式

导出与导入使用同一格式，UTF-8 编码，含表头，列依次为：

```csv
date,kind,category,amount,note
2026-01-01,income,工资,100.00,
2026-01-05,expense,餐饮,12.50,午饭
```

导入时表头必须恰好是 `date,kind,category,amount,note`；空行会被忽略。任意一行不合法时抛出 `ValueError`，错误信息中包含出错的行号（表头算第 1 行，例如 `第 3 行...`），并且一条都不会导入。

## 运行测试

在项目根目录执行：

```bash
python -m pytest
```

只运行命令行验收测试：

```bash
python -m pytest tests/acceptance/test_cli.py -q
```
