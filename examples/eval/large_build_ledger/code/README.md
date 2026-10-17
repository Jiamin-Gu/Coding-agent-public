# ledger 记账工具

一个简单的命令行记账工具，数据保存在一个 JSON 文件里。既可以作为 Python 包调用，
也可以在命令行使用。金额使用 `decimal.Decimal` 精确计算，不会有浮点误差。

## 安装 / 运行环境

需要 Python 3.8+。在项目根目录下即可直接运行，无需安装：

```
python -m ledger --help
```

如需作为包使用，也可以从项目根目录导入：

```python
from ledger import Ledger
```

## 命令行用法

```
python -m ledger [--file PATH] 子命令 ...
```

- `--file PATH`：数据文件，默认 `ledger.json`。
- 成功时退出码为 `0`。
- 出错时（参数不合法、记录不存在、导入失败等）在标准错误输出一行 `错误：原因`，退出码为 `1`。

### 子命令

| 子命令 | 说明 | 标准输出 |
|---|---|---|
| `add KIND AMOUNT CATEGORY DATE [--note NOTE]` | 添加一条记录，`KIND` 为 `income` 或 `expense` | `已添加 #ID` |
| `list [--from DATE] [--to DATE] [--category C] [--kind K]` | 按条件列出记录（`--from`/`--to` 含边界） | 每条一行 `#ID DATE KIND CATEGORY AMOUNT NOTE`；无记录时输出 `（无记录）` |
| `delete ID` | 删除一条记录 | `已删除 #ID` |
| `balance [--from DATE] [--to DATE]` | 计算余额（收入减支出） | 例如 `-12.50` |
| `report YEAR MONTH` | 某月报表 | 第一行 `收入 X 支出 Y 结余 Z`，之后每个支出分类一行 `CATEGORY AMOUNT` |
| `budget set CATEGORY AMOUNT` | 设置某支出分类的每月预算 | `已设置预算 CATEGORY AMOUNT` |
| `budget status YEAR MONTH` | 查看预算使用情况 | 每行 `CATEGORY 已用 SPENT / 预算 BUDGET`，超支时行尾加 ` 超支` |
| `export FILE` | 导出全部记录为 CSV | `已导出 N 条` |
| `import FILE` | 从 CSV 导入记录 | `已导入 N 条` |

### 示例

```console
$ python -m ledger --file money.json add expense 12.50 餐饮 2026-01-05 --note 午饭
已添加 #1

$ python -m ledger --file money.json add income 100 工资 2026-01-01
已添加 #2

$ python -m ledger --file money.json list
#2 2026-01-01 income 工资 100.00
#1 2026-01-05 expense 餐饮 12.50 午饭

$ python -m ledger --file money.json balance
87.50

$ python -m ledger --file money.json report 2026 1
收入 100.00 支出 12.50 结余 87.50
餐饮 12.50

$ python -m ledger --file money.json budget set 餐饮 200
已设置预算 餐饮 200.00

$ python -m ledger --file money.json budget status 2026 1
餐饮 已用 12.50 / 预算 200.00

$ python -m ledger --file money.json export out.csv
已导出 2 条
```

数据规则：

- `id` 为从 1 开始递增的整数，删除或撤销后不会复用。
- `amount` 为正数，最多两位小数；对外返回时统一为保留两位小数的字符串。
- `category` 为非空字符串，保存时会去掉首尾空白。
- `date` 为 `YYYY-MM-DD` 格式的合法日期。
- `note` 可以为空。

## Python 接口

```python
from ledger import Ledger

led = Ledger("money.json")                         # 打开或新建

rid = led.add("expense", "12.50", "餐饮", "2026-01-05", "午饭")  # -> 1
led.add("income", 100, "工资", "2026-01-01")       # amount 可为 str / int / Decimal

led.get(rid)          # -> {"id": 1, "kind": "expense", "amount": "12.50", ...}
led.delete(rid)       # 不存在时抛 KeyError
led.list(start="2026-01-01", end="2026-01-31", category="餐饮", kind="expense")
led.search("午")      # 备注或分类包含关键字（不区分大小写）
led.balance()         # -> "87.50"
led.monthly_report(2026, 1)
led.set_budget("餐饮", "200")
led.budget_status(2026, 1)
led.export_csv("out.csv")   # -> 导出条数
led.import_csv("out.csv")   # -> 导入条数
led.undo()                  # -> True/False
```

方法一览：

| 方法 | 说明 |
|---|---|
| `Ledger(path)` | 打开（或新建）数据文件；文件不存在时视为空账本 |
| `add(kind, amount, category, date, note="") -> int` | 添加记录，返回 id；参数不合法抛 `ValueError` |
| `get(id) -> dict` | 取一条记录，不存在抛 `KeyError` |
| `delete(id) -> None` | 删除记录，不存在抛 `KeyError` |
| `list(start=None, end=None, category=None, kind=None) -> list[dict]` | 筛选，按 `(date, id)` 升序 |
| `search(keyword) -> list[dict]` | 备注或分类包含关键字（不区分大小写），按 `(date, id)` 升序 |
| `balance(start=None, end=None) -> str` | 收入合计减支出合计 |
| `monthly_report(year, month) -> dict` | 月度报表，`by_category` 只统计支出，按金额降序、同额按分类名升序 |
| `set_budget(category, amount) -> None` | 设置/覆盖某支出分类的每月预算 |
| `budget_status(year, month) -> list[dict]` | 各类预算使用情况，按分类名升序 |
| `export_csv(path) -> int` | 导出全部记录（按 `(date, id)` 升序），返回条数 |
| `import_csv(path) -> int` | 导入 CSV，新记录分配新 id；任一行不合法则抛 `ValueError`（含行号）且一条都不导入 |
| `undo() -> bool` | 撤销最近一次 `add`/`delete`/`import_csv`，无历史时返回 `False` |

每次修改后会立即保存到文件。用同一个文件重新创建 `Ledger` 能读到之前的记录、id 计数和预算；
撤销历史只在当前 `Ledger` 对象里有效，不会保存。

## CSV 格式

导出/导入的 CSV 使用 UTF-8 编码，表头为：

```
date,kind,category,amount,note
```

导入时表头必须完全匹配；空行忽略；任意一行不合法时抛 `ValueError`，错误信息包含行号
（表头算第 1 行），并且不会导入任何记录。

## 测试

```console
python -m pytest
```
