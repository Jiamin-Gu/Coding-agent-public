app 包里的调试日志都是用 print 输出的，请改成标准库 logging：

1. 新建 `app/log.py`，提供 `get_logger(name) -> logging.Logger`，返回名为 `"app.<name>"` 的 logger（例如 `get_logger("db")` 返回名为 `"app.db"` 的 logger）。不要在 log.py 里添加 handler 或调用 `logging.basicConfig`，日志输出到哪里由使用方决定
2. 每个模块用 `get_logger("<模块名>")` 获取自己的 logger，模块名就是文件名（不含 `.py`）
3. 以 `"[LOG][ERROR] "` 开头的 print 改为 `logger.error`，以 `"[LOG][WARN] "` 开头的改为 `logger.warning`，以 `"[LOG] "` 开头的改为 `logger.info`。日志内容是去掉前缀后的原文，一个字都不要改
4. 其他 print（给用户看的输出）保持不变，包括内容里恰好提到 `[LOG]` 的
5. 程序的行为和返回值不变
