# pytest-dev__pytest-11143

**Issue**：Rewrite fails when first expression of file is a number and mistaken as docstring 

仓库 `pytest-dev/pytest`，版本 8.0，提交 `6995257cf4`

官方答案见 SWE-bench Lite 数据集。下面是各模型驱动 coder 交出的补丁和判分结果（FAIL_TO_PASS：修之前失败、应该修好的测试；PASS_TO_PASS：原来就通过、不能改坏的测试）。

| 模型 | 结果 | 判分 | 调用次数 | tokens | 补丁 |
|---|---|---|---|---|---|
| deepseek-v4-flash | ✅ | FAIL_TO_PASS 1/1，PASS_TO_PASS 114/114 | 21 | 238,847 | [deepseek-v4-flash.diff](deepseek-v4-flash.diff) |
| kimi-k2.7-code | ✅ | FAIL_TO_PASS 1/1，PASS_TO_PASS 114/114 | 19 | 161,430 | [kimi-k2.7-code.diff](kimi-k2.7-code.diff) |
| glm-5.2 | ✅ | FAIL_TO_PASS 1/1，PASS_TO_PASS 114/114 | 7 | 51,943 | [glm-5.2.diff](glm-5.2.diff) |
| qwen3.7-plus | ✅ | FAIL_TO_PASS 1/1，PASS_TO_PASS 114/114 | 22 | 203,337 | [qwen3.7-plus.diff](qwen3.7-plus.diff) |
| minimax-m3 | ✅ | FAIL_TO_PASS 1/1，PASS_TO_PASS 114/114 | 37 | 426,180 | [minimax-m3.diff](minimax-m3.diff) |
