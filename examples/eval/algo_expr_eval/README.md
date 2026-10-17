# algo_expr_eval

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

在 expr.py 中实现函数 `evaluate(expression: str) -> float`，计算算术表达式的值：

- 支持整数和小数、`+ - * /`、括号、一元负号（例如 `-(2+3)`、`2 * -3`），表达式中可以有任意空格
- 遵循常规的运算优先级和左结合（`2 - 3 - 4` 等于 -5）
- 表达式不合法时（括号不匹配、出现非法字符、空字符串等）抛出 ValueError
- 除以零时抛出 ZeroDivisionError
- 不允许使用 eval、exec 或类似的方式直接执行字符串

## 结果

- 隐藏测试复验：**通过**（17 passed in 0.03s）
- 调用模型 14 次，工具调用 13 次（其中出错 0 次），运行命令 6 条，耗时 24 秒
- token：输入 56,743（命中缓存 52,352），输出 4,552

## agent 新建或修改的文件

- `expr.py`（新建）

agent 自检时写过、最后又用命令删除的临时文件（不包含在 code/ 里）：
- `_test_expr.py`

## agent 的总结

完成。在 `expr.py` 中实现了 `evaluate(expression: str) -> float`。

实现要点：
- **不使用 `eval`/`exec`**，而是手写「词法分析 + 递归下降解析」。
- **词法分析** `_tokenize`：跳过任意空白；识别 `+ - * / ( )` 和数字（整数/小数）；遇到其他字符抛 `ValueError`；对 `1..2`、`.` 之类非法数字抛 `ValueError`。
- **语法**（每层处理优先级，天然左结合）：
  - `expression : term (('+' | '-') term)*`
  - `term : factor (('*' | '/') factor)*`
  - `factor : '-' factor | primary`（支持一元负号，如 `2 * -3`、`-(2+3)`、`--3`）
  - `primary : NUMBER | '(' expression ')'`
- **错误处理**：空字符串/纯空白、括号不匹配、多余 token（如 `1 2`、`2**3`、`+3`、`3+`）→ `ValueError`；除数为 0 → `ZeroDivisionError`。

验证结果：整数/小数、优先级、左结合（`2 - 3 - 4 == -5`）、嵌套括号/一元负号均正确，各类非法输入与除零也都按预期抛异常。测试用的临时脚本已删除，最终只保留 `expr.py`。

一点说明：题目只要求「一元负号」，未提到一元正号，因此我未支持前导 `+`（如 `+3`、`1++2` 会抛 `ValueError`）。如果希望也接受一元正号，我可以再补上。

## 运行过的命令

```
dir /a
python -c "from expr import evaluate; print(evaluate('1 + 2 * 3')); print(evaluate('2 - 3 - 4')); print(evaluate('-(2+3)')); print(evaluate('2 * -3'))
python -c "from expr import evaluate;
python _test_expr.py
python _test_expr.py
del _test_expr.py && python -c "from expr import evaluate; print(evaluate('2 * -3 + (4 - 1) / 3'))"
```

