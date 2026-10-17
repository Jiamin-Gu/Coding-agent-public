# 后台进程：写服务、后台启动、验证、停止（v2.3.0）

命令行一次性模式，自动模式，模型 `deepseek-v4-flash`，空目录开始。

**任务**：写一个只用标准库的 HTTP 服务 server.py：GET /health 返回 JSON {"ok": true}，端口 8765。然后在后台启动它，
用一个 Python 脚本请求 /health 验证返回正确，最后停掉服务并告诉我结果。

**过程**（6 次工具调用）：

| 步骤 | 工具 | 结果 |
|---|---|---|
| 1 | `list_dir` | 空目录 |
| 2 | `write_file server.py` | 46 行 |
| 3 | `write_file verify_health.py` | 23 行 |
| 4 | `start_process python server.py`，`wait_for: "listening"` | 看到 `listening on http://127.0.0.1:8765` 立即返回，进程 p1 运行中 |
| 5 | `run_command python verify_health.py` | `status: 200`、`body: {'ok': True}`、`RESULT: PASS` |
| 6 | `stop_process p1` | 进程已退出，返回服务端最后的日志 `"GET /health HTTP/1.1" 200 -` |

以前没有后台进程工具时，`run_command python server.py` 只能等到超时；而且超时后只杀掉 shell，
python 进程还占着输出管道，工具会一直卡住。现在服务在后台运行，停止时连同子进程一起终止，跑完后 8765 端口已释放。

`code/` 是 agent 写的两个文件。
