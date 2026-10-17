# 评测成果示例

Coding-agent 在评测中完成的任务。每个任务挑一次通过的运行，从轨迹重放出最终代码，并用隐藏测试复验。

| 任务 | 复验 | 模型调用 | 输入 tokens | 输出 tokens | 耗时 | 新建/修改的文件 | 评测 |
|---|---|---|---|---|---|---|---|
| [large_build_ledger](large_build_ledger/README.md) | ✅ | 59 | 1,324,322 | 60,567 | 318s | 9 | `20261008-145845-deepseek-flashteam-always` |
| [large_library_softdelete](large_library_softdelete/README.md) | ✅ | 66 | 1,275,528 | 48,044 | 266s | 21 | `20261008-145845-deepseek-flashteam-always` |
| [large_spec_shop](large_spec_shop/README.md) | ✅ | 154 | 5,229,702 | 195,619 | 1189s | 20 | `20261011-113509-deepseek-v4-flashteam-always` |

`large_spec_shop` 是 v2.2 岗位分工版本的产出：3 个测试岗位写验收测试，7 个后端任务实现，安全审查报告 3 个问题后由负责的 agent 返工、复查通过。旧的项目记忆版本可以从 `evals/results/20261009-035302-deepseek-v4-flashteam-always` 重新生成。
