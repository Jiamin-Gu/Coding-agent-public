# pytest-dev__pytest-9359

**Issue**：Error message prints extra code line when using assert in python3.9

仓库 `pytest-dev/pytest`，版本 7.0，提交 `e2ee3144ed`

官方答案见 SWE-bench Lite 数据集。下面是各模型驱动 coder 交出的补丁和判分结果（FAIL_TO_PASS：修之前失败、应该修好的测试；PASS_TO_PASS：原来就通过、不能改坏的测试）。

| 模型 | 结果 | 判分 | 调用次数 | tokens | 补丁 |
|---|---|---|---|---|---|
| deepseek-v4-flash | ✅ | FAIL_TO_PASS 1/1，PASS_TO_PASS 54/54 | 42 | 1,156,704 | [deepseek-v4-flash.diff](deepseek-v4-flash.diff) |
