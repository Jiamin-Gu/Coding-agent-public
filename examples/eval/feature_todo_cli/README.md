# feature_todo_cli

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

给 todo.py 增加功能，并修一个问题：

1. 新增 `done <id>` 子命令，把对应的待办标记为完成。同时提供同名函数 `done(todo_id: int) -> dict`，返回被修改的待办；id 不存在时抛出 KeyError
2. `list` 子命令支持 `--pending` 参数，只显示未完成的待办
3. 修复：如果手动从 todos.json 里删掉中间某一条，再添加新待办，新 id 可能和已有的重复。新 id 应该等于现有最大 id + 1

保持现有命令的输出格式不变。

## 结果

- 隐藏测试复验：**通过**（4 passed in 0.33s）
- 调用模型 11 次，工具调用 10 次（其中出错 0 次），运行命令 4 条，耗时 15 秒
- token：输入 35,058（命中缓存 30,848），输出 2,152

## agent 新建或修改的文件

- `todo.py`（修改）

agent 自检时写过、最后又用命令删除的临时文件（不包含在 code/ 里）：
- `_t.py`

## agent 的总结

所有功能已实现并通过测试。

## 修改内容（todo.py）

1. **新增 `done(todo_id: int) -> dict` 函数**：遍历待办，找到 id 匹配项后置 `done=True` 并保存，返回该待办；找不到则 `raise KeyError(todo_id)`。

2. **新增 `done <id>` 子命令**：`id` 为 int 类型，调用上面的函数并输出 `已完成 #<id>: <title>`。

3. **`list --pending` 参数**：加了 `--pending`（`store_true`），列出时跳过已完成项，其余输出格式不变。

4. **修复 id 重复问题**：`add` 里把 `len(todos) + 1` 改成 `max((t["id"] for t in todos), default=0) + 1`，即现有最大 id + 1。

## 验证结果
- 添加 3 条后手动从 todos.json 删除中间一条，再添加新待办，新 id 为 4（不再重复）。
- `done 2` 正确把 #2 标记为完成，`list` 显示 `[x] #2 …`。
- `list --pending` 只显示未完成项，输出格式与原来一致。
- 不存在的 id 调用 `done` 会抛出 `KeyError`。

测试产生的 `todos.json` 和临时脚本已清理。

## 运行过的命令

```
del todos.json 2>nul & python todo.py add "task one" & python todo.py add "task two" & python todo.py add "task three" & python todo.py list & echo --
python -c "import todo; todo.add('x'); print(todo.done(1)); 
python -c "import todo; todo.add('z'); 
del todos.json 2>nul & python _t.py & del _t.py todos.json 2>nul & dir
```

