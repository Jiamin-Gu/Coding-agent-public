# algo_lru_cache

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

在 lru_cache.py 中实现 LRUCache 类：

- `LRUCache(capacity: int)`：创建容量为 capacity 的缓存
- `get(key) -> int`：键存在时返回对应的值，并把它标记为最近使用；不存在时返回 -1
- `put(key, value) -> None`：插入或更新键值，并标记为最近使用；超过容量时，淘汰最久未使用的键

get 和 put 的时间复杂度都要求是 O(1)。写完后自己写测试验证。

## 结果

- 隐藏测试复验：**通过**（4 passed in 0.22s）
- 调用模型 12 次，工具调用 11 次（其中出错 0 次），运行命令 6 条，耗时 20 秒
- token：输入 42,812（命中缓存 38,784），输出 3,648

## agent 新建或修改的文件

- `lru_cache.py`（新建）
- `test_lru_cache.py`（新建）

agent 自检时写过、最后又用命令删除的临时文件（不包含在 code/ 里）：
- `_cross_check.py`

## agent 的总结

完成。

## 实现说明

**`lru_cache.py`** — 用「哈希表 + 双向链表（带哨兵节点）」实现：

- `cache`：`dict` 映射 `key -> _Node`，提供 O(1) 查找。
- 双向链表维护访问顺序，`head` 侧是最近使用（MRU），`tail` 侧是最久未使用（LRU）。
- `get`：命中则把节点移到头部并返回值，否则返回 `-1`。
- `put`：已存在则更新值并移到头部；否则新建节点插到头部，若超出容量就删除 `tail.prev`（LRU）并同步从字典移除。
- 每个操作只做常数次指针和字典操作，故均为 **O(1)**。

**`test_lru_cache.py`** — 7 个测试覆盖：基本读写、缺失返回 -1、淘汰最久未使用、更新已有键、容量为 1、LeetCode 经典样例、多次 `get` 后的淘汰顺序、非法容量报错。

## 验证结果

```
PASS test_basic_put_get
PASS test_capacity_one
PASS test_evict_lru
PASS test_invalid_capacity
PASS test_leetcode_example
PASS test_order_after_get
PASS test_update_existing

全部 7 个测试通过
```

另外用 `OrderedDict` 参考实现做了 2000 组、每组 200 次随机操作的对拍，结果完全一致（临时脚本已删除）。运行测试：`python test_lru_cache.py`。

## 运行过的命令

```
dir /a
python test_lru_cache.py
python test_lru_cache.py
python -c "
python _cross_check.py
del _cross_check.py
```

