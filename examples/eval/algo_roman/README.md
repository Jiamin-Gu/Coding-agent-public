# algo_roman

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

在 roman.py 中实现两个函数：

- `to_roman(n: int) -> str`：把 1 到 3999 的整数转成罗马数字（例如 1994 → "MCMXCIV"）
- `from_roman(s: str) -> int`：把罗马数字转回整数

超出范围的数字、不规范或不合法的罗马数字（例如 "IIII"、"VX"、"IC"、空字符串、小写字母）都要抛出 ValueError。

## 结果

- 隐藏测试复验：**通过**（12 passed in 0.03s）
- 调用模型 8 次，工具调用 7 次（其中出错 0 次），运行命令 4 条，耗时 16 秒
- token：输入 25,955（命中缓存 23,168），输出 3,371

## agent 新建或修改的文件

- `roman.py`（新建）

agent 自检时写过、最后又用命令删除的临时文件（不包含在 code/ 里）：
- `_test_roman.py`

## agent 的总结

已在 `roman.py` 中实现两个函数，并通过测试验证。

**实现要点：**

- **`to_roman(n)`**：用贪心法按标准符号表（含 `IV/IX/XL/XC/CD/CM` 六种减法组合）从大到小拼接。非整数（含 `bool`）、以及不在 1–3999 范围的值抛 `ValueError`。
- **`from_roman(s)`**：从左到右解析，遇到合法的减法组合（`IV/IX/XL/XC/CD/CM`）时按减法计值，否则累加。解析后**用 `to_roman(total)` 重新编码并比对原字符串**，从而拒绝 `IIII`、`VX`、`IC`、`IIV` 等不规范写法；空字符串、非字符串、含小写或非法字符的输入也抛 `ValueError`。

**验证结果：** 1–3999 全部满足 `from_roman(to_roman(n)) == n`；边界值（1、3999、1994 等）与各类非法输入（`IIII`、`VX`、`IC`、空串、小写、`MMMM`、`0`、`4000`、`True` 等）均正确抛出 `ValueError`。测试脚本已删除。

## 运行过的命令

```
dir /a /b
python -c "from roman import to_roman, from_roman; cases=[(1,'I'),(4,'IV'),(9,'IX'),(14,'XIV'),(40,'XL'),(90,'XC'),(400,'CD'),(900,'CM'),(1994,'MCMXCI
python _test_roman.py
del _test_roman.py
```

