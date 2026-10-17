# debug_duration_parser

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

duration.py 里的 `parse_duration` 和 `format_duration` 有问题，`tests/test_duration.py` 中有测试失败。

请修复这两个函数，使它们完全符合各自文档字符串里描述的规则。注意现有测试并不完整，请对照规则逐条检查，补充你自己的测试。

## 结果

- 隐藏测试复验：**通过**（36 passed in 0.06s）
- 调用模型 11 次，工具调用 13 次（其中出错 0 次），运行命令 5 条，耗时 41 秒
- token：输入 101,473（命中缓存 95,616），输出 8,816

## agent 新建或修改的文件

- `duration.py`（修改）
- `tests/test_duration.py`（修改）

agent 自检时写过、最后又用命令删除的临时文件（不包含在 code/ 里）：
- `_check_duration.py`

## agent 的总结

修复完成，所有测试通过（72 项）。

## 修改内容

### `duration.py`

**`parse_duration`** 原实现只做了 `re.findall(r"(\d+)([dhms])")`，存在多处不符合文档规则的问题：大小写敏感、不支持小数、不四舍五入、不校验顺序/重复/非法字符、不处理"纯数字表示秒"。重写为：

- 用 `_PLAIN_NUMBER` 处理"只有数字"的情况，按秒返回，并用 `Decimal` + `ROUND_HALF_UP` 实现 0.5 进位（避免 Python 银行家舍入 `round(0.5)==0`）。
- 用 `_UNIT_PART`（`IGNORECASE`，要求小数点前后都有数字）逐段扫描，跳过各部分间的任意空白，首尾空白由 `strip` 处理。
- 用 `seen` + `last_order` 校验"每个单位最多一次且按 d→h→m→s 顺序"。
- 任何不匹配（负数、未知单位、多余字符、缺单位的数字、`.5h`、`1.h` 等）都抛 `ValueError`。
- 小数累加后再整体四舍五入到整秒。

**`format_duration`** 原实现会把所有单位（含 0）都拼出来（`5400` → `"0d1h30m0s"`）。重写为：

- 校验输入：负数抛 `ValueError`；非整数（如 `1.5`、字符串/`None`）抛 `ValueError`；整数值的 float（如 `2.0`）可接受。
- 按 d→h→m→s 取整商，只保留非 0 单位，全 0 返回 `"0s"`（如 `5400` → `"1h30m"`、`90061` → `"1d1h1m1s"`）。

### `tests/test_duration.py`

补齐了覆盖每条规则的测试（参数化）：

- 合法解析：大小写、空格/制表符/换行、无空格、首尾空白、小数、0.5 进位、纯数字、`0s` 等。
- 非法解析：空/空白、单位乱序、单位重复、负数、未知单位、小数点位置错误、用空格分隔的数值与单位、缺单位、多余字符等。
- 格式化：`0 → "0s"`、省略 0 单位、各典型值。
- 非法格式化：负数、非整数、字符串、`None`。
- 往返性质 `parse_duration(format_duration(n)) == n`（含 0 到大数多个取值）。

另外用 2 万个随机数做了往返 fuzz 校验，并验证了 `1.005h` 的精确进位（`3618`），全部通过。

## 运行过的命令

```
python -m pytest tests/test_duration.py -v
python -c "
python -c "print('hello')"
python _check_duration.py
del _check_duration.py
```

