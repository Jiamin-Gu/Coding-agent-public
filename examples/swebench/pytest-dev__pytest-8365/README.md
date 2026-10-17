# pytest-dev__pytest-8365

**Issue**：tmpdir creation fails when the username contains illegal characters for directory names

仓库 `pytest-dev/pytest`，版本 6.3，提交 `4964b468c8`

官方答案见 SWE-bench Lite 数据集。下面是各模型驱动 coder 交出的补丁和判分结果（FAIL_TO_PASS：修之前失败、应该修好的测试；PASS_TO_PASS：原来就通过、不能改坏的测试）。

| 模型 | 结果 | 判分 | 调用次数 | tokens | 补丁 |
|---|---|---|---|---|---|
| deepseek-v4-flash | ✅ | FAIL_TO_PASS 1/1，PASS_TO_PASS 32/32 | 30 | 716,873 | [deepseek-v4-flash.diff](deepseek-v4-flash.diff) |
