# long_refactor_logging

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

app 包里的调试日志都是用 print 输出的，请改成标准库 logging：

1. 新建 `app/log.py`，提供 `get_logger(name) -> logging.Logger`，返回名为 `"app.<name>"` 的 logger（例如 `get_logger("db")` 返回名为 `"app.db"` 的 logger）。不要在 log.py 里添加 handler 或调用 `logging.basicConfig`，日志输出到哪里由使用方决定
2. 每个模块用 `get_logger("<模块名>")` 获取自己的 logger，模块名就是文件名（不含 `.py`）
3. 以 `"[LOG][ERROR] "` 开头的 print 改为 `logger.error`，以 `"[LOG][WARN] "` 开头的改为 `logger.warning`，以 `"[LOG] "` 开头的改为 `logger.info`。日志内容是去掉前缀后的原文，一个字都不要改
4. 其他 print（给用户看的输出）保持不变，包括内容里恰好提到 `[LOG]` 的
5. 程序的行为和返回值不变

## 结果

- 隐藏测试复验：**通过**（8 passed in 0.07s）
- 调用模型 8 次，工具调用 23 次（其中出错 0 次），运行命令 1 条，耗时 15 秒
- token：输入 32,900（命中缓存 29,056），输出 3,726

## agent 新建或修改的文件

- `app/config.py`（修改）
- `app/db.py`（修改）
- `app/emails.py`（修改）
- `app/log.py`（新建）
- `app/main.py`（修改）
- `app/orders.py`（修改）
- `app/payments.py`（修改）
- `app/reports.py`（修改）
- `app/users.py`（修改）

## agent 的总结

改造完成，验证通过。

## 改动摘要

**新增 `app/log.py`**
```python
import logging


def get_logger(name):
    return logging.getLogger(f"app.{name}")
```
不加 handler、不调用 `basicConfig`，输出目标交给使用方。

**各模块**（文件名即 logger 名）在顶部加 `from .log import get_logger` 和 `logger = get_logger("<模块名>")`，并把调试 print 替换为对应级别：

| 文件 | logger 名 | info / warning / error |
|---|---|---|
| config.py | `app.config` | 1 / 1 / 0 |
| db.py | `app.db` | 1 / 0 / 1 |
| emails.py | `app.emails` | 1 / 1 / 0 |
| main.py | `app.main` | 2 / 0 / 0 |
| orders.py | `app.orders` | 1 / 1 / 0 |
| payments.py | `app.payments` | 1 / 1 / 1 |
| reports.py | `app.reports` | 1 / 1 / 0 |
| users.py | `app.users` | 1 / 1 / 1 |

- `[LOG][ERROR] ` → `logger.error`，`[LOG][WARN] ` → `logger.warning`，`[LOG] ` → `logger.info`，仅去掉前缀，正文一字未改（f-string 结构保留）。
- 保留的用户可见 print：`提示：调试信息以 [LOG] 开头的旧格式已经废弃`（不以 `[LOG] ` 开头）、`订单金额：…`、`支付成功`、`已创建用户：…`。
- 运行结果与返回值不变（`run()` 仍返回 `"paid"`，各函数返回值一致），logger 名称确认为 `app.<模块名>`。

## 运行过的命令

```
python -c "import logging; from app import main, db; logging.basicConfig(level=logging.DEBUG, format='%(name)s:%(levelname)s:%(message)s'); print('sta
```

