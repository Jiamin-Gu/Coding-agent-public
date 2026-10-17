# feature_log_parser

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

logs/app.log 是应用日志。请在 log_stats.py 中实现函数 `analyze(path: str) -> dict`，返回：

- `total`：有效日志行的数量（跳过空行和格式不正确的行）
- `by_level`：每个日志级别的行数，例如 `{"INFO": 3, "ERROR": 3, "WARN": 1}`
- `error_users`：出现过 ERROR 的用户名列表，去重并按字母排序
- `avg_latency_ms`：所有有效行 latency 的平均值，保留 1 位小数（float）；没有有效行时为 0.0
- `slowest`：latency 最大的那一行的 action；没有有效行时为 None

格式不正确的行要跳过，不能让程序崩溃。

## 结果

- 隐藏测试复验：**通过**（2 passed in 0.18s）
- 调用模型 4 次，工具调用 4 次（其中出错 0 次），运行命令 1 条，耗时 7 秒
- token：输入 9,297（命中缓存 7,040），输出 1,484

## agent 新建或修改的文件

- `log_stats.py`（新建）

## agent 的总结

已实现并验证通过。

`log_stats.py` 的核心逻辑：

- 用正则 `LINE_RE` 严格匹配每行格式（时间戳、级别、`user=`、`action=`、`latency=Nms`，可选 `error="..."`），不匹配的行（空行、`this line is broken`）直接跳过，不会抛异常。
- 逐行累计 `total`、`by_level`，ERROR 行收集用户名到 set，累加延迟。
- 结束时计算平均延迟（`round(..., 1)`，无有效行为 `0.0`），`slowest` 取最大 latency 行的 `action`（无有效行为 `None`）。
- `error_users` 用 `sorted()` 去重排序。

对 `logs/app.log` 的输出与预期一致：

```json
{"total": 7, "by_level": {"INFO": 3, "ERROR": 3, "WARN": 1},
 "error_users": ["alice", "bob"], "avg_latency_ms": 1544.3, "slowest": "search"}
```

## 运行过的命令

```
python -c "import log_stats, json; print(json.dumps(log_stats.analyze('logs/app.log'), ensure_ascii=False))"
```

