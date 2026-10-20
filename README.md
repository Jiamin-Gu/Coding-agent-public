# coder：从零实现的 Coding Agent

[![tests](https://github.com/Jiamin-Gu/Coding-agent-public/actions/workflows/tests.yml/badge.svg)](https://github.com/Jiamin-Gu/Coding-agent-public/actions/workflows/tests.yml)

不依赖任何 agent 框架，直接基于 LLM 的 function calling 实现一个能**读代码、改文件、跑命令、自己修 bug** 的 coding agent，带浏览器界面和自动评测。目标是讲清楚 Claude Code / Codex 这类工具内部是怎么工作的。任何兼容 OpenAI 协议的模型都能驱动，默认 DeepSeek。

**当前版本：v2.8.1** · [更新记录](CHANGELOG.md) · [使用教程](docs/usage.md) · [评测](docs/evaluation.md) · [架构与设计决策](docs/design.md) · [成果示例](examples/README.md)

## 亮点

- **自己实现的 agent 循环**：不用 LangChain 等框架，直接基于 function calling 实现"调用模型 → 执行工具 → 回传结果"，支持流式输出、思考模型和截图输入
- **工具设计**：精确唯一替换的 `edit_file`、带行号分段读取、正则搜索、带超时的命令执行、后台进程（启动开发服务器、读输出、连同子进程一起停止）；所有错误都作为观察结果回传给模型自我纠正
- **可靠性**：先读后改；改了代码没验证通过就不许结束（verify-on-stop）；循环检测；工具参数不是合法 JSON、回复被截断时不执行也不让对话报废；运行中可以插话
- **上下文管理**：两级压缩，先无损裁剪早期的长输出，不够再摘要；用户原始要求和改过的文件原样保留。压力测试下压缩次数减少 40%、未命中缓存的输入减少 19%
- **团队模式**：主 agent 先写验收测试和接口契约，子 agent 并行实现、只能写自己负责的文件，通过共享黑板保持一致；对比实验表明中小任务拆分只会增加成本，所以默认不拆
- **安全与可撤销**：可选的沙箱模式（agent 在项目副本上工作、你确认后才应用到项目；命令在 Docker 容器里执行，默认断网、非 root、只读根文件系统）；发给模型前遮蔽密钥；网页访问令牌 + Origin/Host 检查；改文件、执行命令前确认；每轮一个检查点，一键撤销
- **MCP 客户端**：自己实现协议（不依赖官方 SDK），支持 stdio 和 Streamable HTTP，配置用通用的 mcpServers 格式，可以接入搜索、读网页、浏览器等外部工具
- **自动评测**：22 个带隐藏测试的自写任务（DeepSeek 51/51 通过）+ SWE-bench Lite 子集（10 个真实 issue，Docker 中搭建环境，10/10 解决）；Kimi、GLM、Qwen、MiniMax 都能驱动；token 账本分析每一次调用的花费
- **工程**：166 个单元测试（用脚本化的假模型，不消耗 API），可以 `pip install`

## 快速开始

需要 Python 3.10+、Git，以及一个兼容 OpenAI 协议的模型 API（例如 [DeepSeek](https://platform.deepseek.com/)）。没有 API 也可以先用演示模式看效果。

```bash
git clone https://github.com/Jiamin-Gu/Coding-agent-public.git
cd Coding-agent-public
```

- **Windows**：双击 `start.bat`。第一次运行会安装依赖、创建 `.env`、打开浏览器，并弹出「模型设置」让你选服务商、填 API Key
- **macOS / Linux**：`bash start.sh`

也可以手动启动：

```bash
pip install -r requirements.txt
python -m coder.web                # 浏览器界面；加 --demo 进入演示模式（假模型）
python -m coder 工作区路径 --auto -p "写一个计算器模块，配上 pytest 测试并跑通"   # 命令行，一次性任务
```

## 可选功能（默认关闭）

- **沙箱模式**：agent 在项目的副本上工作，命令在 Docker 容器里执行，每轮结束列出改动，你确认后才应用到真实项目。镜像的 Dockerfile 就在本项目里（`coder/sandbox_image/`），只需要另外装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)，再运行一次 `python -m coder.sandbox build` 在本机构建镜像；之后在网页的 ⚙ 设置里打开，或者在 `.env` 里写 `CODER_SANDBOX=1`
- **MCP 工具**（联网搜索、读网页、操作浏览器等）：本项目带的是 MCP **客户端**，工具来自外部的 MCP 服务器，需要你自己准备（任何标准的 MCP 服务器都可以，比如官方的网页读取服务器、Playwright 浏览器服务器），在 `~/.coder/mcp.json`（所有项目通用）或项目里的 `.coder/mcp.json` 里配置，用通用的 mcpServers 格式（Cursor、Claude 等工具都用这种）。没有配置就没有这些工具，其他功能不受影响

详见 [使用教程](docs/usage.md) 里的"沙箱模式"和"MCP 工具"。

## 用起来是什么样

1. **选工作区**：打开一个项目文件夹（或者不选，直接问问题，比如贴一道 LeetCode 题）
2. **布置任务**：比如"写一个计算器模块，配上 pytest 测试并跑通"。你会实时看到它读文件、改代码、运行测试、根据报错修改，直到测试通过
3. **审核和撤销**：改文件、执行命令前可以先确认；不满意可以一键撤销到任意一轮之前
4. **大项目**：打开团队模式，主 agent 拆分模块、派给子 agent 并行完成

详细说明见 [使用教程](docs/usage.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [使用教程](docs/usage.md) | 配置、工作区、发送图片、演示模式、界面、命令参数、沙箱、MCP 工具、团队模式、常见问题 |
| [评测](docs/evaluation.md) | 评测集、基线结果、压缩压力测试、团队模式对比、多模型验证、SWE-bench Lite |
| [架构与设计决策](docs/design.md) | 模块结构、agent 循环、每个关键设计为什么这样做、路线图 |
| [成果示例](examples/README.md) | agent 在评测中交付的完整代码、团队模式的产出、界面演示 |
| [更新记录](CHANGELOG.md) | 每个版本改了什么、为什么改 |

## 运行测试与发布

```bash
pip install pytest
python -m pytest            # 166 个测试，用假模型，不调用 API
```

- **CI**：每次推送和 PR，GitHub Actions 在 Ubuntu（Python 3.10 / 3.12）和 Windows（Python 3.12）上跑全部测试（`.github/workflows/tests.yml`）
- **CD**：推送版本标签（例如 `v2.8.1`）时自动发布（`.github/workflows/release.yml`）：跑全部测试 → 检查标签、代码里的版本号和 CHANGELOG 一致（`scripts/release_check.py`）→ 打包 → 在全新的虚拟环境里装好安装包做冒烟测试（`scripts/smoke_installed.py`）→ 创建 GitHub Release，说明取自 CHANGELOG 里这一版的内容，附上安装包。任何一步不通过就停下、不发布。试跑可以用 `v2.8.1-rc.1` 这样的标签（发布成预发布）

## 许可证

[MIT](LICENSE)
