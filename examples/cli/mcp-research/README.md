# MCP：联网查资料并写总结（v2.6.0）

命令行一次性模式，自动模式，模型 `deepseek-v4-flash`，空目录开始。
MCP 配置是用户级的 `~/.coder/mcp.json`，接了一个本机的 HTTP MCP 服务器（搜索后端是本机 Docker 里的 SearXNG，读网页用官方的 fetch 服务器），
agent 拿到 `mcp__hub__search__searxng_web_search`（搜索）和 `mcp__hub__fetch__fetch`（读网页）等工具。

**任务**：搜索 PEP 701（f-string 语法改进）并阅读 PEP 原文，在 docs/pep701.md 里用中文总结它解决了什么问题、主要改动（附代码示例）；
再搜一条最近关于 Python 3.14 正式发布的新闻，把标题、日期和链接附在文末。所有信息注明来源网址，查不到的不要编造。

**结果**：agent 先搜索，再用 fetch 读了 PEP 701 原文（Motivation / Rationale / Specification / Consequences）和 Python 官方的 3.14.0 发布页，
写出 146 行的总结（`code/docs/pep701.md`）：
- 基本信息（状态、创建和决议日期、目标版本）、PEP 498 留下的四类限制、新的 PEG 文法和三个新 token、向后兼容性，代码示例取自 PEP 原文
- 文末附 Python 3.14.0 发布：2025 年 10 月 7 日，链接指向 python.org 官方发布页
- 参考来源只列了实际读过的两个网址，没有编造链接
