# bug_stats

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

stats.py 里的统计函数有几个 bug，用户报告：

1. `median([3, 1, 4, 2])` 返回 3，应该是 2.5；而且调用后，传进去的列表顺序被改变了
2. `mode([1, 2, 2, 3])` 返回 3，应该是 2（出现次数相同时，返回其中最小的值）
3. 对空列表调用这三个函数时，报错信息很难懂，应该统一抛出 ValueError

请修复这些问题，不要改变函数的名字和参数。

## 结果

- 隐藏测试复验：**通过**（7 passed in 0.01s）
- 调用模型 8 次，工具调用 8 次（其中出错 0 次），运行命令 4 条，耗时 8 秒
- token：输入 17,866（命中缓存 15,104），输出 1,231

## agent 新建或修改的文件

- `stats.py`（修改）

agent 自检时写过、最后又用命令删除的临时文件（不包含在 code/ 里）：
- `_check.py`

## agent 的总结

已修复 `stats.py` 中的三个问题（函数名和参数保持不变）：

1. **median**：
   - 用 `sorted(values)` 复制后排序，不再修改传入的列表；
   - 偶数个元素时取中间两个数的平均值，`median([3,1,4,2])` 现在返回 `2.5`。

2. **mode**：先求最大出现次数，再用 `min(...)` 在所有达到该次数的值中取最小值。`mode([1,2,2,3])` 返回 `2`，出现次数相同时返回最小值。

3. **空列表**：三个函数开头都加了非空检查，统一 `raise ValueError(...)`，并附上清晰的中文提示。

验证结果：
```
median: 2.5  list unchanged: True
median odd: 2
mode: 2 / mode tie: 1
mean: 2.0
mean/median/mode -> 各自 ValueError 提示
```

## 运行过的命令

```
python -c "import stats; a=[3,1,4,2]; print(stats.median(a), a); print(stats.mode([1,2,2,3])); print(stats.mean([1,2,3])); [print(f.__name__, (lambda:
python -c "import stats
python _check.py
del _check.py
```

