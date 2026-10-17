# large_build_ledger

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261008-144904-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

按照 `docs/PRD.md` 的需求文档，从零实现这个记账工具：Python 包、命令行、测试和 README。

接口、输出格式和错误处理要严格符合文档。请为主要功能编写 pytest 测试，并确保全部通过。

## 结果

- 隐藏测试复验：**通过**（26 passed in 3.46s）
- 调用模型 21 次，工具调用 28 次（其中出错 0 次），运行命令 9 条，耗时 171 秒
- token：输入 623,100（命中缓存 613,504），输出 35,256

## agent 新建或修改的文件

- `README.md`（新建）
- `conftest.py`（新建）
- `ledger/__init__.py`（新建）
- `ledger/__main__.py`（新建）
- `ledger/cli.py`（新建）
- `ledger/core.py`（新建）
- `pyproject.toml`（新建）
- `tests/test_cli.py`（新建）
- `tests/test_core.py`（新建）

## agent 的总结

已按 `docs/PRD.md` 从零实现完成，全部 47 个测试通过。

## 交付内容

**Python 包 `ledger/`**
- `core.py`：核心类 `ledger.Ledger`，所有金额用 `Decimal` 精确计算，对外统一返回保留两位小数的字符串。
- `__init__.py`：导出 `Ledger`。
- `cli.py`：命令行解析与分发。
- `__main__.py`：`python -m ledger` 入口。

**测试 `tests/`**
- `test_core.py`：增删查、参数校验、id 不复用、筛选/排序、搜索、余额精度、月度报表、预算、持久化、CSV 导入导出（含失败原子性与行号）、撤销。
- `test_cli.py`：以子进程方式跑 `python -m ledger`，校验各子命令输出格式、退出码与 `错误：…` 输出。

**其他**：`README.md`（用法/示例/API 表/CSV 格式）、`pyproject.toml`、根目录 `conftest.py`（保证 `import ledger` 可用）。

## 关键实现要点
- **精度**：金额全程 `Decimal`，`0.10 + 0.20 == "0.30"`，负数如 `-12.00`。
- **校验**：`kind`/`amount`（正数、最多两位小数、拒绝 float/bool/NaN）/`category`（去空白非空）/`date`（严格 `YYYY-MM-DD` 且为合法日期）不合法均抛 `ValueError`。
- **id 单调**：`next_id` 持久化，删除或撤销后不复用（撤销 add 后再 add 得到新 id）。
- **撤销**：内存栈，支持撤销 add/delete/import（导入整体），无历史返回 `False`，不持久化。
- **CSV**：UTF-8，表头 `date,kind,category,amount,note`；导入任一行非法即抛错且含行号（表头为第 1 行）、一条都不导入；空行忽略；读取用 `utf-8-sig` 兼容 BOM。
- **CLI**：`--file` 默认 `ledger.json`；成功退出码 0，出错在标准错误输出一行 `错误：原因` 退出码 1；解析错误也统一为该格式（自定义 `ArgumentParser.error`）。

修复过程中发现一个关键 bug：全局 `--file` 与 `export`/`import` 的位置参数同名（`dest="file"`）会互相覆盖，导致把它们当成账本文件读写；已把全局选项改为 `dest="ledger_file"` 解决。

## 运行过的命令

```
powershell -Command "(Get-Content docs/PRD.md).Count" & echo --- & dir /b
type docs\PRD.md
python --version & python -m pytest -q
python -m pytest -q
python -m pytest -q
set PYTHONUTF8=1& python -m ledger --file demo.json add expense 12.50 餐饮 2026-01-05 --note 午饭 & python -m ledger --file demo.json add income 100 工资 20
python -m ledger --file demo2.json delete 99 2>err.txt & echo returncode=%errorlevel% & type err.txt & del err.txt demo2.json 2>nul
powershell -Command "python -m ledger --file demo3.json delete 99 2>&1 | Write-Output; Write-Output ('code=' + $LASTEXITCODE); Remove-Item -Force demo
python -m pytest -q
```

