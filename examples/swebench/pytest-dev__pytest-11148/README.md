# pytest-dev__pytest-11148

**Issue**：Module imported twice under import-mode=importlib

仓库 `pytest-dev/pytest`，版本 8.0，提交 `2f7415cfbc`

官方答案见 SWE-bench Lite 数据集。下面是各模型驱动 coder 交出的补丁和判分结果（FAIL_TO_PASS：修之前失败、应该修好的测试；PASS_TO_PASS：原来就通过、不能改坏的测试）。

| 模型 | 结果 | 判分 | 调用次数 | tokens | 补丁 |
|---|---|---|---|---|---|
| deepseek-v4-flash | ✅ | FAIL_TO_PASS 2/2，PASS_TO_PASS 129/129 | 22 | 646,347 | [deepseek-v4-flash.diff](deepseek-v4-flash.diff) |
| kimi-k2.7-code | ✅ | FAIL_TO_PASS 2/2，PASS_TO_PASS 129/129 | 57 | 2,071,930 | [kimi-k2.7-code.diff](kimi-k2.7-code.diff) |
| qwen3.7-plus | ✅ | FAIL_TO_PASS 2/2，PASS_TO_PASS 129/129 | 60 | 1,265,940 | [qwen3.7-plus.diff](qwen3.7-plus.diff) |
| minimax-m3 | ✅ | FAIL_TO_PASS 2/2，PASS_TO_PASS 129/129 | 24 | 279,961 | [minimax-m3.diff](minimax-m3.diff) |
