# 成果示例

Coding-agent 实际完成的任务，代码都是 agent 写的（模型 `deepseek-flash`）。

## 评测任务（[eval/](eval/README.md)）

19 个评测任务各一份：17 个来自 v1.1.0 的基线评测（17 个任务 × 3 次，51/51 通过），2 个大任务来自 v2.0.0 的大任务基线（2 个任务 × 3 次，6/6 通过）。每个任务挑一次通过的运行：

- `code/`：任务的初始代码 + agent 的全部修改，即 agent 最终交付的项目
- `README.md`：任务描述、结果（调用次数、token、耗时）、改了哪些文件、agent 自己的总结、运行过的命令

评测时每个任务在临时目录里运行，跑完就删除，这些代码是用 `python -m coder.replay` 从评测轨迹**重放**出来的：从初始代码开始，按顺序重新执行 agent 成功的每一次写文件、改文件，以及删除临时文件的命令。重放后用隐藏测试再跑一遍，19 个全部通过，说明和当时交付的一致。

几个值得看的：

| 示例 | 看点 |
|---|---|
| [multi_inventory_reservations](eval/multi_inventory_reservations/README.md) | 在 5 个模块的现有系统里加功能，同时改数据、业务、报表、命令行和持久化 |
| [multi_pricing_bugs](eval/multi_pricing_bugs/README.md) | 结算流水线里有 4 个 bug，用户投诉只提到一部分，agent 对照文档逐个排查 |
| [debug_perf_dedupe](eval/debug_perf_dedupe/README.md) | 把 O(n²) 的去重改成并查集，20 万条记录 3 秒内完成，还修好了传递关系 |
| [long_refactor_logging](eval/long_refactor_logging/README.md) | 8 个文件统一改用 logging，没有误改"内容里提到 [LOG]"的用户提示 |
| [long_spec_textkit](eval/long_spec_textkit/README.md) | 按一份较长的规格实现 12 个函数，38 个隐藏测试全部通过 |
| [large_build_ledger](eval/large_build_ledger/README.md) | 照一份完整的需求文档从零实现命令行记账工具（记账、月报、预算、CSV 导入导出、撤销） |
| [large_library_softdelete](eval/large_library_softdelete/README.md) | 在 44 个文件的图书馆系统里给 8 种实体统一加软删除、恢复和审计日志 |

## 团队模式（[team/](team/README.md)）

同样两个大任务，用团队模式（强制拆分）完成：主 agent 写验收测试和接口契约，子 agent 分模块并行实现。每个示例的 README 里有分工、契约全文和黑板上的决策记录，可以看到子 agent 之间怎样不直接对话也能对齐接口。两个都通过了隐藏测试，但成本约为单 agent 的 3 倍（对比见项目 README 的"评测"一节）。

## 网页界面演示（[web-ui/](web-ui/)）

- [calculator](web-ui/calculator/README.md)：两轮对话写计算器模块，中间重启服务，验证对话恢复后 agent 记得上下文
- [leetcode-from-screenshot](web-ui/leetcode-from-screenshot/README.md)：粘贴题目截图，agent 读题、写解法、自己补边界用例测试

## SWE-bench Lite 子集（[swebench/](swebench/README.md)）

pytest、flask 的真实 issue，各模型驱动 coder 交出的补丁和官方测试的判分结果（FAIL_TO_PASS / PASS_TO_PASS 各通过几个）。

## 命令行演示（[cli/](cli/)）

- [mcp-research](cli/mcp-research/README.md)：经 MCP 服务器联网搜索、读 PEP 原文和官方发布页，写出注明来源的中文总结（v2.6.0 的 MCP 客户端）
- [sandbox-node-python](cli/sandbox-node-python/README.md)：沙箱模式下写 Node 模块和测试、联网确认后 pip 安装、对比两种实现（v2.4.0 的 Docker 沙箱）
- [background-process](cli/background-process/README.md)：写一个 HTTP 服务，用 `start_process` 后台启动、等到 "listening" 出现，验证 /health 后用 `stop_process` 停掉（v2.3.0 的后台进程工具）

## 再生成

跑完一次评测后，可以用新的结果重新生成：

```bash
python -m coder.replay evals/results/<某次评测的目录> --out examples/eval
```
