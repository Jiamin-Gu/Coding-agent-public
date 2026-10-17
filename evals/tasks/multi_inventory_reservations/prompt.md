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
