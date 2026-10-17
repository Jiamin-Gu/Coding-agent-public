# pallets__flask-5063

**Issue**：Flask routes to return domain/sub-domains information

仓库 `pallets/flask`，版本 2.3，提交 `182ce3dd15`

官方答案见 SWE-bench Lite 数据集。下面是各模型驱动 coder 交出的补丁和判分结果（FAIL_TO_PASS：修之前失败、应该修好的测试；PASS_TO_PASS：原来就通过、不能改坏的测试）。

| 模型 | 结果 | 判分 | 调用次数 | tokens | 补丁 |
|---|---|---|---|---|---|
| deepseek-v4-flash | ✅ | FAIL_TO_PASS 2/2，PASS_TO_PASS 54/54 | 46 | 1,409,589 | [deepseek-v4-flash.diff](deepseek-v4-flash.diff) |
| kimi-k2.7-code | ❌ | FAIL_TO_PASS 0/2，PASS_TO_PASS 54/54 | 60 | 1,645,332 | [kimi-k2.7-code.diff](kimi-k2.7-code.diff) |
| glm-5.2 | ✅ | FAIL_TO_PASS 2/2，PASS_TO_PASS 54/54 | 26 | 594,067 | [glm-5.2.diff](glm-5.2.diff) |
| qwen3.7-plus | ❌ | FAIL_TO_PASS 1/2，PASS_TO_PASS 54/54 | 37 | 468,783 | [qwen3.7-plus.diff](qwen3.7-plus.diff) |
| minimax-m3 | ✅ | FAIL_TO_PASS 2/2，PASS_TO_PASS 54/54 | 60 | 1,941,222 | [minimax-m3.diff](minimax-m3.diff) |
