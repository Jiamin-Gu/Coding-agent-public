# 计算器模块（网页界面，两轮对话）

用 Coding-agent 的网页界面完成（v0.2.1，模型 `deepseek-flash`），空文件夹起步。

## 第一轮

> 写一个计算器模块 calc.py（加减乘除，除以零时抛出 ValueError），配上 pytest 测试并跑通

agent 先查看目录和本机的 Python、pytest 版本，然后新建 `calc.py` 和 `test_calc.py`，运行测试 5 个全部通过。约 7 秒，约 9.5k token（其中 6.2k 命中缓存）。

## 第二轮（重启服务后，在同一个对话里继续）

> 给 calc 加一个 power(a, b) 幂运算函数，并补上测试

验证了对话历史的持久化：重启服务后打开同一个对话，agent 记得之前的上下文，先读取现有的两个文件，再用精确编辑（`edit_file`）加上 `power` 和对应测试，运行通过。

## 运行

```bash
python -m pytest -q
```
