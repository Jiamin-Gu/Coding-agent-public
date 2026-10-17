# bug_config_types

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

运行 `python -m app.demo` 会报错；另外有用户反映，即使没有开启 debug，服务也打印了 "debug mode on"。

请找出原因并修复：让配置项返回正确的类型（page_size 和 timeout 为 int；debug 为 bool，"true"、"1"、"yes" 不区分大小写都算开启，其他值算关闭），同时环境变量（如 APP_PAGE_SIZE、APP_DEBUG）仍然可以覆盖默认值。

## 结果

- 隐藏测试复验：**通过**（3 passed in 0.12s）
- 调用模型 8 次，工具调用 13 次（其中出错 0 次），运行命令 5 条，耗时 10 秒
- token：输入 19,451（命中缓存 16,256），输出 1,683

## agent 新建或修改的文件

- `app/settings.py`（修改）

## agent 的总结

修复完成。

## 问题原因

`app/settings.py` 的 `get()` 原样返回环境变量或默认值的字符串，导致：

1. **`python -m app.demo` 报错**：`pagination.paginate()` 里 `size = settings.get("page_size")` 拿到的是字符串 `"20"`，`start + size` 参与切片时抛出 `TypeError: slice indices must be integers`。
2. **误打印 "debug mode on"**：`settings.get("debug")` 返回字符串 `"false"`，而任何非空字符串在 Python 中都是真值（truthy），于是 `if settings.get("debug")` 恒为真。

## 修改内容

只改了 `app/settings.py`：

- `DEFAULTS` 改为正确的类型：`page_size=20`、`timeout=5`、`debug=False`。
- 新增按配置项的类型转换器：`page_size`、`timeout` 转成 `int`；`debug` 转成 `bool`（`true`/`1`/`yes` 不区分大小写视为开启，其余视为关闭，含默认 `False`）。
- `get()` 仍优先读取 `APP_<NAME>` 环境变量，未设置时回退到默认值，最后统一做类型转换。

## 验证

- `python -m app.demo` 退出码 0，输出 `['server started']` 和正确的分页结果。
- 默认值类型正确：`20 5 False`。
- `APP_DEBUG=YES APP_PAGE_SIZE=5 APP_TIMEOUT=9` 覆盖生效，类型分别为 `bool` / `int`。
- 逐一测试 `True/TRUE/1/Yes/yes` → `True`，`false/False/0/no/off/空` → `False`。

## 运行过的命令

```
python -m app.demo
python -m app.demo
python -c "from app import settings; print(repr(settings.get('page_size')), repr(settings.get('timeout')), repr(settings.get('debug')))"
python -c "import os; os.environ['APP_DEBUG']='YES'; os.environ['APP_PAGE_SIZE']='5'; os.environ['APP_TIMEOUT']='9'; from app import settings; print(r
for %v in (True TRUE 1 Yes yes false False 0 no off "") do @python -c "import os; os.environ['APP_DEBUG']='%v'; from app import settings; print('%v ->
```

