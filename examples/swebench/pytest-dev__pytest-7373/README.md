# pytest-dev__pytest-7373

**Issue**：Incorrect caching of skipif/xfail string condition evaluation

仓库 `pytest-dev/pytest`，版本 5.4，提交 `7b77fc086a`

官方答案见 SWE-bench Lite 数据集。下面是各模型驱动 coder 交出的补丁和判分结果（FAIL_TO_PASS：修之前失败、应该修好的测试；PASS_TO_PASS：原来就通过、不能改坏的测试）。

| 模型 | 结果 | 判分 | 调用次数 | tokens | 补丁 |
|---|---|---|---|---|---|
| deepseek-v4-flash | ✅ | FAIL_TO_PASS 1/1，PASS_TO_PASS 81/81 | 18 | 149,875 | [deepseek-v4-flash.diff](deepseek-v4-flash.diff) |
| qwen3.7-plus | ✅ | FAIL_TO_PASS 1/1，PASS_TO_PASS 81/81 | 13 | 78,779 | [qwen3.7-plus.diff](qwen3.7-plus.diff) |
