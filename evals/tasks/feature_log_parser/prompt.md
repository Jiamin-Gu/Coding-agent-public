logs/app.log 是应用日志。请在 log_stats.py 中实现函数 `analyze(path: str) -> dict`，返回：

- `total`：有效日志行的数量（跳过空行和格式不正确的行）
- `by_level`：每个日志级别的行数，例如 `{"INFO": 3, "ERROR": 3, "WARN": 1}`
- `error_users`：出现过 ERROR 的用户名列表，去重并按字母排序
- `avg_latency_ms`：所有有效行 latency 的平均值，保留 1 位小数（float）；没有有效行时为 0.0
- `slowest`：latency 最大的那一行的 action；没有有效行时为 None

格式不正确的行要跳过，不能让程序崩溃。
