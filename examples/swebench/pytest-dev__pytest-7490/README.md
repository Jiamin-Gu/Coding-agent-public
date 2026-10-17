# pytest-dev__pytest-7490

**Issue**：Pytest 6: Dynamically adding xfail marker in test no longer ignores failure

仓库 `pytest-dev/pytest`，版本 6.0，提交 `7f7a36478a`

官方答案见 SWE-bench Lite 数据集。下面是各模型驱动 coder 交出的补丁和判分结果（FAIL_TO_PASS：修之前失败、应该修好的测试；PASS_TO_PASS：原来就通过、不能改坏的测试）。

| 模型 | 结果 | 判分 | 调用次数 | tokens | 补丁 |
|---|---|---|---|---|---|
| deepseek-v4-flash | ✅ | FAIL_TO_PASS 2/2，PASS_TO_PASS 78/78 | 29 | 636,231 | [deepseek-v4-flash.diff](deepseek-v4-flash.diff) |
