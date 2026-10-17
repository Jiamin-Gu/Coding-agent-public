# long_spec_textkit

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

按照 `docs/SPEC.md` 的规格说明，在 `textkit.py` 中实现其中的 12 个函数。每条规则都要满足，示例必须完全一致。请为每个函数写测试并运行通过。

## 结果

- 隐藏测试复验：**通过**（38 passed in 0.07s）
- 调用模型 8 次，工具调用 8 次（其中出错 0 次），运行命令 3 条，耗时 48 秒
- token：输入 68,667（命中缓存 63,744），输出 12,123

## agent 新建或修改的文件

- `test_textkit.py`（新建）
- `textkit.py`（新建）

## agent 的总结

全部 55 个测试通过。已在 `textkit.py` 中实现规格要求的 12 个函数，并在 `test_textkit.py` 中为每个函数编写了测试（覆盖 SPEC 的全部示例，并补充了边界用例）。

实现要点：

1. **slugify** — 小写后用 `[^a-z0-9]+` 替换为单个 `-` 并 strip 首尾。
2. **camel_to_snake** — 两段正则：先拆「缩写+首字母大写单词」（`HTTPResponse`→`HTTP_Response`），再拆「小写/数字+大写」，最后转小写；数字自然粘在前一个字母后。
3. **snake_to_camel** — 保留开头的下划线，中间连续下划线合并为一个分隔，首词小写、后续词 `capitalize`。
4. **truncate_middle** — 开头字符数用 `max_len // 2`（即 `ceil((max_len-1)/2)`），结尾补齐，`end` 为 0 时不再多取字符；`max_len < 1` 抛 `ValueError`。
5. **normalize_whitespace** — `\s+`（含全角空格 `\u3000`）替换为单空格后 strip。
6. **extract_emails** — 正则 `[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}`，末尾句点因 TLD 需字母而不被吞；按出现顺序去重并小写。
7. **word_count** — 统计 `[A-Za-z0-9']+` 与 `[\u4e00-\u9fff]` 的匹配数之和。
8. **levenshtein** — 标准滚动数组 DP。
9. **is_palindrome** — 去掉非 `[A-Za-z0-9]` 字符、转小写后比较。
10. **title_case** — 按空白分词，依次应用「全大写且长度≥2 保留」「小词且非首尾小写」「其余首字母大写」。
11. **wrap** — 先规范化空白，超长单词按 `width` 切片，再贪心成行；`width < 1` 抛 `ValueError`。
12. **parse_kv** — 手工扫描以正确处理带引号值中的 `;`/`=`，支持空部分忽略、空值、重复键覆盖，未闭合引号/缺 `=`/空键抛 `ValueError`。

运行结果：`python -m pytest test_textkit.py -q` → **55 passed**。

## 运行过的命令

```
dir /a
python --version && python -c "import pytest; print('pytest', pytest.__version__)"
python -m pytest test_textkit.py -q
```

