# 沙箱模式：Node + Python，联网要确认（v2.4.0）

命令行一次性模式，自动模式 + `--sandbox`，模型 `deepseek-v4-flash`，空目录开始。

**任务**：写一个 Node.js 模块 slugify.js，用 node 自带的 node:test 写测试并运行通过；再用 pip 安装 python-slugify，
写 compare.py 对比两种实现在 5 个例子上的结果；最后说明自己运行在什么环境里。

**过程中值得看的地方**：

- 所有命令都在 Docker 容器里执行，工作区挂载在 `/workspace`，写出的文件直接出现在本机的工作区里
- `node --test slugify.test.js`：6/6 通过（Node 22，容器里自带，本机不需要装）
- `pip install --user python-slugify` 带了 `network: true`。虽然开着自动模式，还是弹出了联网确认：

  ```
  需要确认：run_command（这个命令要联网）
  $ pip install --user python-slugify    （沙箱，联网）
  允许执行？[y] 允许这一次联网 / [n] 否 / [a] 本次会话允许命令联网
  ```

  确认后安装成功，命令结束后容器立即断网
- `python3 compare.py`：5 个例子两种实现结果全部一致
- 模型报告的运行环境：Debian 12 (Linux) 的 Docker 沙箱容器，Python 3.12.15，Node v22.23.3
- 程序退出后容器被删除（`docker ps -a --filter label=coder.sandbox=1` 为空）

`code/` 是 agent 写的三个文件。
