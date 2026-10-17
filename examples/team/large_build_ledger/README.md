# large_build_ledger

由 Coding-agent 在评测中完成（模型 `deepseek-flashteam-always`，评测 `20261008-145845-deepseek-flashteam-always`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

按照 `docs/PRD.md` 的需求文档，从零实现这个记账工具：Python 包、命令行、测试和 README。

接口、输出格式和错误处理要严格符合文档。请为主要功能编写 pytest 测试，并确保全部通过。

## 结果

- 隐藏测试复验：**通过**（26 passed in 4.41s）
- 调用模型 59 次，工具调用 80 次（其中出错 1 次），运行命令 28 条，耗时 318 秒
- token：输入 1,324,322（命中缓存 1,257,472），输出 60,567

## agent 新建或修改的文件

- `README.md`（新建）
- `ledger/__init__.py`（新建）
- `ledger/__main__.py`（新建）
- `ledger/cli.py`（新建）
- `ledger/core.py`（新建）
- `ledger/money.py`（新建）
- `pyproject.toml`（新建）
- `tests/acceptance/test_cli.py`（新建）
- `tests/acceptance/test_core.py`（新建）

## 团队分工（团队模式）

主 agent 拆分的任务（每个任务由一个子 agent 完成，只能写自己负责的文件）：

- **core** [done]：ledger/__init__.py, ledger/money.py, ledger/core.py
- **cli** [done]：ledger/cli.py, ledger/__main__.py
- **docs** [done]：README.md, pyproject.toml

接口契约：

- **core-api**（lead）：模块与文件：ledger/package 位于项目根。ledger/__init__.py 必须 `from ledger.core import Ledger` 并定义 `__all__ = ["Ledger"]`。ledger/money.py 提供金额工具（内部使用）。ledger/core.py 定义 `class Ledger`。

金额规则（money.py + 全局）：内部一律用 decimal.Decimal 精确计算，绝不用 float。对外金额是保留两位小数的字符串，例如 "0.30"、"-12.00"、"100.00"。
- 解析：接受 str / int / Decimal（其它类型抛 ValueError；bool 视为非法）。str 用 Decimal(s) 解析，必须有限、非指数造成超过两位小数。合法条件：value > 0 且 value == value.quantize(Decimal("0.01"))（即最多两位小数）。0、负数、"abc"、"1.234"、"1e-3" 均非法。
- 格式化：`format_money(d) -> str`，用 `d.quantize(Decimal("0.01"))` 后 `str()`，负数带前导 '-'（如 "-10.00"）。

Ledger(path)：path 为 str 或 os.PathLike，UTF-8。文件不存在视为空账本。

数据文件格式（JSON，UTF-8，内部约定，core 自管）：
{"next_id": <int 从1开始, 每次分配后+1, 删除/撤销都不回退不复用>,
 "records": [ {"id":int,"kind":"income"|"expense","amount":"<两位小数字符串>","category":str,"date":"YYYY-MM-DD","note":str}, ... ],
 "budgets": {"<category>": "<两位小数字符串>", ...}}
每次修改后立即写入（可先写临时文件再替换）。加载时若文件不存在或为空则为空账本。

方法签名与语义：
- `add(kind, amount, category, date, note="") -> int`：校验 kind∈{income,expense}；amount 按金额规则（>0，<=2位小数）；category 非空（strip 后保存）；date 必须是 "YYYY-MM-DD" 的合法日历日期（用 datetime.date.fromisoformat 且字符串长度为10并严格匹配格式，拒绝 "2026-1-5"）。note 任意（可为空，不 strip 也无妨）。不合法抛 ValueError（add 不得写入任何内容）。返回分配的新 id。
- `get(id) -> dict`：返回上述对外 dict（字段顺序 id,kind,amount,category,date,note）。不存在抛 KeyError。
- `delete(id) -> None`：不存在抛 KeyError。
- `list(start=None, end=None, category=None, kind=None) -> list[dict]`：start/end 为含边界的 "YYYY-MM-DD" 字符串比较；category 精确匹配（调用方给的是 strip 后值）；kind 精确匹配。结果按 (date, id) 升序。
- `search(keyword) -> list[dict]`：note 或 category 中包含 keyword（小写化后子串匹配，不区分大小写），按 (date,id) 升序。空 keyword 匹配全部。
- `balance(start=None, end=None) -> str`：范围内 income 之和 - expense 之和，返回两位小数字符串（无记录返回 "0.00"）。
- `monthly_report(year, month) -> dict`：`{"income": str, "expense": str, "net": str, "by_category": [{"category": str, "amount": str}, ...]}`。net=income-expense。by_category 只统计该月 expense，按 amount 降序、金额相同按 category 升序。无支出时 by_category 为 []。
- `set_budget(category, amount) -> None`：category strip 后非空，amount 按金额规则（>0,<=2位小数），否则 ValueError。重复设置覆盖。
- `budget_status(year, month) -> list[dict]`：对每个已设预算分类一项 `{"category","budget","spent","remaining","over"}`；spent=该分类当月 expense 合计（无则 "0.00"），remaining=budget-spent（可负），over = spent > budget（bool）。按 category 升序。
- `export_csv(path) -> int`：全部记录按 (date,id) 升序写出 UTF-8 CSV（用 csv 模块，newline=""），表头恰好 `date,kind,category,amount,note`，amount 为两位小数字符串。返回条数。
- `import_csv(path) -> int`：读取同格式 CSV。用 csv.reader；表头必须恰为 `["date","kind","category","amount","note"]`（否则 ValueError）。逐行校验（空行忽略，忽略后不占数据但物理行号仍前进），行号用 `reader.line_num`（表头为第1行）。任一行不合法抛 ValueError，错误信息包含出错行号（如 "第 3 行..."），且一条都不导入（原子性：先全部校验通过再统一分配 id 写入）。新记录分配新 id，返回导入条数。
- `undo() -> bool`：撤销最近一次 add / delete / import_csv。add→删除该记录；delete→恢复该记录（原 id）；import_csv→删除该次导入的全部记录。可连续撤销；无可撤销返回 False。撤销不回收 id（next_id 不回退）。历史只存于对象内存，不持久化；set_budget 不进入撤销历史。每次撤销后立即保存。

错误处理：参数不合法 ValueError；记录不存在 KeyError。
- **cli-module**（lead）：文件：ledger/cli.py 提供 `main(argv=None) -> int`；ledger/__main__.py 内容为 `import sys; from ledger.cli import main; sys.exit(main())`。

调用形式：`python -m ledger [--file PATH] 子命令 ...`，--file 默认 "ledger.json"，位置在子命令之前。用 argparse 实现；解析出错时要输出一行 `错误：<原因>` 到 stderr 并返回 1（不要用 argparse 默认的 usage+exit2）。建议自定义 ArgumentParser.error 抛异常再由 main 捕获。

main 返回 int（成功 0）。捕获 ValueError、KeyError 等，向 **stderr** 打印一行 `错误：<原因>`，返回 1；成功信息打印到 **stdout**。

成功输出格式（严格）：
- `add KIND AMOUNT CATEGORY DATE [--note NOTE]` → stdout `已添加 #ID`
- `list [--from DATE] [--to DATE] [--category C] [--kind K]`：每条一行 `#ID DATE KIND CATEGORY AMOUNT NOTE`（单空格分隔；note 为空时行尾无空格、即只到 AMOUNT）；无记录输出 `（无记录）`（全角括号）。
- `delete ID` → `已删除 #ID`
- `balance [--from DATE] [--to DATE]` → 余额字符串，如 `-12.50`
- `report YEAR MONTH` → 第一行 `收入 X 支出 Y 结余 Z`（X/Y/Z 两位小数），随后每个支出分类一行 `CATEGORY AMOUNT`（顺序同 by_category）
- `budget set CATEGORY AMOUNT` → `已设置预算 CATEGORY AMOUNT`（金额两位小数）
- `budget status YEAR MONTH` → 每分类一行 `CATEGORY 已用 SPENT / 预算 BUDGET`；该分类 over 时行尾追加 ` 超支`（例如 `餐饮 已用 30.00 / 预算 20.00 超支`）
- `export FILE` → `已导出 N 条`
- `import FILE` → `已导入 N 条`

注意 `--from` 的 argparse dest 名可用 `getattr(args, "from")` 读取（不要写 args.from）。ID 参数用 int。YEAR/MONTH 用 int。DATE 直接传给 core（由 core 校验）。

自测：`python -m pytest tests/acceptance/test_cli.py -q` 必须全通过（这些测试文件不可修改）。

黑板上的决策和留言：

- [decision] docs → all：docs 任务完成：创建 README.md（中文，含项目简介/安装/Python 包各方法示例/CLI 各子命令示例与输出/数据文件 JSON 与 CSV 格式说明/`python -m pytest` 测试运行方式，示例输出严格对齐 PRD）与 pyproject.toml（setuptools，name=ledger，version=0.1.0，requires-python>=3.8，packages=["ledger"]，optional-dependencies.test=["pytest>=7.0"]）。已验证 pyproject.toml 为合法 TOML，且 `python -m pytest tests/acceptance` 仍能正常收集（当前仅因 ledger/ 包尚未创建而 import 报错）。未修改 ledger/ 下任何代码。
- [decision] core → all：core 任务完成：ledger/money.py + ledger/core.py + ledger/__init__.py 已实现并通过全部 51 个 tests/acceptance/test_core.py。

接口与 core-api 契约完全一致（Ledger(path); add/get/delete/list/search/balance/monthly_report/set_budget/budget_status/export_csv/import_csv/undo；内部 Decimal；对外两位小数字符串；JSON 持久化 {"next_id","records","budgets"}；id 从1递增不复用；撤销历史仅内存；set_budget 不入历史；每次修改立即保存）。

一个不影响契约的实现细节：_save() 优先写 .tmp 再 os.replace 原子替换；在 Windows 上该替换偶发 PermissionError（索引/杀毒短暂占用），故加了重试并在最后退回就地写入。对外行为不变。

import_csv 的错误信息形如 "第 N 行不合法: ..."（N 为 reader.line_num，表头=1），符合 CLI 测试对行号的要求。cli-module 可直接 from ledger import Ledger。
- [decision] cli → all：cli 任务完成：ledger/cli.py + ledger/__main__.py 已实现，`python -m pytest tests/acceptance/test_cli.py -q` 13/13 通过（全量 tests/acceptance 64 passed）。

实现要点：
- 自定义 ArgumentParser.error 抛 _CliError，main 捕获后向 stderr 打印一行 `错误：原因` 并返回 1；成功 stdio 输出到 stdout 返回 0。捕获 ValueError/KeyError/OSError/_CliError。
- 全局 `--file` 的 argparse dest 命名为 `data_file`（不能叫 file！），因为 export/import 子命令有位置参数 file，同名 dest 会被子命令覆盖导致读错数据文件。默认 "ledger.json"。
- `--from` 用 `getattr(args, "from")` 读取；ID/YEAR/MONTH 用 int。
- set_budget 后输出金额用 ledger.money.format_money(parse_amount(...)) 归一化为两位小数（唯一一处直接使用 money 内部工具，用于满足“金额两位小数”输出要求）。

## agent 的总结

全部完成，验收测试 64/64 通过，工作区干净无残留文件。

## 完成总结

严格按 `docs/PRD.md` 从零实现了 `ledger` 记账工具，接口、输出格式、错误处理均与文档一致。

**交付物**
- `ledger/__init__.py`：导出 `Ledger`
- `ledger/money.py`：`Decimal` 精确金额解析（拒绝 0/负数/超两位小数/非法字符串）与两位小数格式化
- `ledger/core.py`：`Ledger` 全部方法 `add / get / delete / list / search / balance / monthly_report / set_budget / budget_status / export_csv / import_csv / undo`
  - JSON 持久化 `{"next_id", "records", "budgets"}`，每次修改立即保存，重建可读回记录/id 计数/预算，撤销历史仅存内存
  - id 从 1 递增、删除或撤销后不复用
  - `import_csv` 表头严格校验、空行忽略、任一行非法即抛含行号的 `ValueError` 且原子性不导入
  - `undo` 支持连续撤销 add/delete/import，无操作返回 `False`
- `ledger/cli.py` + `ledger/__main__.py`：`python -m ledger [--file PATH] 子命令 ...`，成功退出码 0，出错时标准错误输出一行 `错误：原因`、退出码 1；9 个子命令输出格式严格对齐 PRD
- `tests/acceptance/test_core.py`、`test_cli.py`：64 个 pytest 用例（Python API + CLI 子进程），覆盖全部主要功能与边界
- `README.md`、`pyproject.toml`

**协作方式**：先写验收测试与接口契约，再拆分为 `core` / `cli` / `docs` 三个文件互不重叠的子任务派发；`cli` 依赖 `core`，故先并行 `core`+`docs`，再派 `cli`。三份汇报均通过我独立复跑验证。

**验证结果**：`python -m pytest` → **64 passed**，无收集错误；另外手工核验了金额精度、持久化、CSV 往返、CLI 错误路径与空账本等边界。

其中 CLI 任务发现并修复了一个关键坑：argparse 全局 `--file` 的 dest 若命名为 `file`，会被 `export/import` 的位置参数同名覆盖导致读错数据文件，已改为 `data_file`。

## 运行过的命令

```
dir /a
python --version && python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8')); print('OK', d['pro
python -m pytest --version
python -c "from pip._vendor import tomli; import pathlib; d=tomli.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8')); print('TOML OK:',
python -m pytest tests/acceptance -q 2>&1 | more
python --version && python -m pytest tests/acceptance/test_core.py -q
python -m pytest tests/acceptance/test_core.py -q
for /L %i in (1,1,5) do @python -m pytest tests/acceptance/test_core.py -q 2>&1 | findstr /C:"passed" /C:"failed"
python -c "from decimal import Decimal; from ledger import Ledger; import tempfile,os; p=os.path.join(tempfile.mkdtemp(),'l.json'); l=Ledger(p); print
python -c "
python -c "print('hello')"
python -c "exec(open(0).read())" < NUL & echo done
python -c "exec('x=1\ny=2\nprint(x+y)')"
python -c "exec('from ledger import Ledger\nimport tempfile, os\nl = Ledger(os.path.join(tempfile.mkdtemp(), \"l.json\"))\nfor b in (True, False):\n  
python -m py_compile ledger/__init__.py ledger/money.py ledger/core.py && python -m pytest tests/acceptance/test_core.py -q
python -m pytest tests/acceptance/test_cli.py -q
cd /d "%TEMP%" && mkdir clitest_x 2>nul & cd clitest_x && del /q d.json o.csv 2>nul & python -m ledger --file d.json add expense 12.50 餐饮 2026-01-05 -
python -m ledger --file "%TEMP%\clitest_x\d.json" add expense 12.50 餐饮 2026-01-05 --note 午饭 & echo EXIT=%errorlevel% & type "%TEMP%\clitest_x\d.json"
python -m ledger --file "%TEMP%\clitest_x\d.json" export "%TEMP%\clitest_x\o.csv" & echo EXIT=%errorlevel% & type "%TEMP%\clitest_x\o.csv"
python -m pytest tests/acceptance/test_cli.py -q
python -m pytest tests/acceptance -q
set F=%TEMP%\clitest_x\e.json & del /q "%F%" 2>nul & echo =1= no args: & python -m ledger --file "%F%" & echo exit=%errorlevel% & echo =2= bad subcomm
python -m pytest tests -q
python -c "import tempfile,os,json; from ledger import Ledger; d=tempfile.mkdtemp(); p=os.path.join(d,'l.json'); l=Ledger(p); print(l.add('expense','1
python -m ledger -h >nul 2>nul & echo help_exit=%errorlevel% & python -m ledger --file nonexist_dir_xyz/x.json list 2>&1 & echo list_exit=%errorlevel%
cmd /c "python -m ledger badcmd 2>err.txt & echo EXIT=%errorlevel%" & type err.txt & del err.txt
cmd /c "python -m ledger --file t.json add expense -1 餐饮 2026-01-05 2>err2.txt & echo EXIT=%errorlevel%" & type err2.txt & del err2.txt & del t.json 2
python -m pytest -q
```

