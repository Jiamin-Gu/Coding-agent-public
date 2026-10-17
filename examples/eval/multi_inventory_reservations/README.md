# multi_inventory_reservations

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

给 inventory 包增加"预留"功能：客户下单时先预留库存，发货时再真正扣减。

1. `Inventory` 新增方法：
   - `reserve(order_id, item_id, qty)`：为订单预留库存。可用库存不足时抛出 `InventoryError`；同一个订单可以预留多种商品，也可以对同一商品多次预留（数量累加）；qty 必须为正，否则抛出 `ValueError`；商品不存在抛出 `InventoryError`
   - `release(order_id)`：取消这个订单的全部预留；订单不存在时抛出 `InventoryError`
   - `fulfill(order_id)`：订单发货，按预留数量扣减实际库存，并删除这个订单的预留；订单不存在时抛出 `InventoryError`
   - `available(item_id) -> int`：可用库存 = 实际库存 - 所有订单对这个商品的预留之和
2. 直接出库 `ship` 也只能使用可用库存，不能动用已经被预留的部分
3. 补货报告 `low_stock` 改为按可用库存判断
4. 预留信息要和商品一起持久化：重新创建 `Store` / `Inventory` 后预留仍然存在；旧格式的 JSON 文件（没有预留信息）要能正常读取
5. 命令行增加三个子命令：`reserve <order_id> <item_id> <qty>`、`release <order_id>`、`fulfill <order_id>`，出错时和其他命令一样打印错误并返回 1

`tests/` 里的现有测试必须继续通过。

## 结果

- 隐藏测试复验：**通过**（14 passed in 0.18s）
- 调用模型 17 次，工具调用 22 次（其中出错 0 次），运行命令 7 条，耗时 31 秒
- token：输入 109,774（命中缓存 103,552），输出 5,378

## agent 新建或修改的文件

- `inventory/cli.py`（修改）
- `inventory/reports.py`（修改）
- `inventory/service.py`（修改）
- `inventory/storage.py`（修改）

agent 自检时写过、最后又用命令删除的临时文件（不包含在 code/ 里）：
- `_tmp_cli_check.py`
- `tests/test_reservations_tmp.py`

## agent 的总结

已完成预留功能，现有 4 个测试全部通过。

改动说明：

**`inventory/storage.py`**
- `Store` 新增 `reservations: dict[order_id, dict[item_id, qty]]` 字段。
- 读取时若 JSON 中没有 `reservations`（旧格式）则默认为空；写入时一并保存，实现与商品一起持久化。

**`inventory/service.py`**
- `reserve(order_id, item_id, qty)`：qty 非正抛 `ValueError`，商品不存在抛 `InventoryError`，可用库存不足抛 `InventoryError`；支持同一订单多商品、同商品多次预留（累加）。
- `release(order_id)`：删除该订单全部预留，订单不存在抛 `InventoryError`。
- `fulfill(order_id)`：按预留数量扣减实际库存并删除预留，订单不存在抛 `InventoryError`。
- `available(item_id)`：实际库存 − 所有订单预留之和。
- `ship` 改为按 `available` 判断，不能动用已预留部分。

**`inventory/reports.py`**
- `low_stock` 改为按 `available` 与补货线比较。

**`inventory/cli.py`**
- 新增 `reserve <order_id> <item_id> <qty>`、`release <order_id>`、`fulfill <order_id>` 三个子命令，异常处理与其它命令一致（打印错误、返回 1）。

验证：现有测试通过；另外临时测试覆盖了可用库存、多次预留累加、ship 受限、持久化、旧格式读取及 CLI 成功/失败路径，均通过（临时文件已清理）。

## 运行过的命令

```
python -m pytest tests/ -q
python -c "
python -c "print('hello')"
python -m pytest tests/ -q
python _tmp_cli_check.py
del _tmp_cli_check.py tests\test_reservations_tmp.py
python -m pytest tests/ -q
```

