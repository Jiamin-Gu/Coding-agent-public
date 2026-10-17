# pallets__flask-4992

**Issue**：Add a file mode parameter to flask.Config.from_file()

仓库 `pallets/flask`，版本 2.3，提交 `4c288bc97e`

官方答案见 SWE-bench Lite 数据集。下面是各模型驱动 coder 交出的补丁和判分结果（FAIL_TO_PASS：修之前失败、应该修好的测试；PASS_TO_PASS：原来就通过、不能改坏的测试）。

| 模型 | 结果 | 判分 | 调用次数 | tokens | 补丁 |
|---|---|---|---|---|---|
| deepseek-v4-flash | ✅ | FAIL_TO_PASS 1/1，PASS_TO_PASS 18/18 | 17 | 153,699 | [deepseek-v4-flash.diff](deepseek-v4-flash.diff) |
| kimi-k2.7-code | ✅ | FAIL_TO_PASS 1/1，PASS_TO_PASS 18/18 | 55 | 1,067,784 | [kimi-k2.7-code.diff](kimi-k2.7-code.diff) |
| glm-5.2 | ❌ | FAIL_TO_PASS 0/1，PASS_TO_PASS 18/18 | 25 | 690,211 | [glm-5.2.diff](glm-5.2.diff) |
| qwen3.7-plus | ❌ | FAIL_TO_PASS 0/1，PASS_TO_PASS 18/18 | 12 | 67,606 | [qwen3.7-plus.diff](qwen3.7-plus.diff) |
| minimax-m3 | ❌ | FAIL_TO_PASS 0/1，PASS_TO_PASS 18/18 | 25 | 268,338 | [minimax-m3.diff](minimax-m3.diff) |
