# debug_csv_report

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

运行 `python report.py data/sales.csv` 会报错。请修复 report.py，使输出与 `data/expected.txt` 完全一致。

`summarize()` 之后还会用来处理其他同样格式的 CSV 文件，格式规则见它的文档字符串，请确保这些情况都能正确处理。

## 结果

- 隐藏测试复验：**通过**（4 passed in 0.20s）
- 调用模型 6 次，工具调用 7 次（其中出错 0 次），运行命令 2 条，耗时 10 秒
- token：输入 15,603（命中缓存 12,800），输出 1,792

## agent 新建或修改的文件

- `report.py`（修改）

## agent 的总结

已修复 `report.py`，输出与 `data/expected.txt` 完全一致。

原代码的问题：用 `line.strip().split(",")` 逐行按逗号切分，无法处理带引号的字段、引号内的逗号/换行/转义引号，也没处理 BOM 和金额中的千位分隔符。

修改内容（`summarize()`）：
- 改用标准库 `csv.reader` 解析，自动处理双引号包裹、字段内的逗号与换行、以及 `""` 转义引号。
- 读取时用 `encoding="utf-8-sig"` 自动去除 UTF-8 BOM；配合 `newline=""` 交给 csv 处理换行。
- 跳过空行（`csv.reader` 对空行返回空列表）。
- 金额先 `replace(",", "")` 去掉千位分隔符，再转 `float`，负数退款也能正确累加。

这些处理覆盖了文档字符串里描述的所有情况，因此 `summarize()` 也能复用于其他同格式的 CSV 文件。

## 运行过的命令

```
python report.py data/sales.csv > out.txt 2>&1 && fc out.txt data\expected.txt && echo MATCH
del out.txt
```

