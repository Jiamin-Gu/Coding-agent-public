# shopkit 需求文档

一个小型网店后台的核心逻辑：商品目录、库存、定价（阶梯价、类别折扣、税）、优惠券、订单流程、报表和持久化。只做 Python 库，不需要界面或命令行。

## 0. 总体约定

- Python 3.10+ 的包 `shopkit`，**只能用标准库**
- 对外入口：`from shopkit import Shop`。所有异常类可以从 `shopkit` 或 `shopkit.errors` 导入；金额工具函数在 `shopkit.money`
- 金额在内部一律用 `decimal.Decimal` 计算，**不能用 float**。返回值里的金额一律是保留两位小数的**字符串**，例如 `"12.30"`、`"0.00"`
- 时间：`Shop(clock=None)`。`clock` 是一个无参数函数，返回 `datetime`（不带时区）；不传时用 `datetime.now`。所有用到"当前时间"或"今天"的地方都调用 `clock()`
- 事件时间的格式：`clock().isoformat(timespec="seconds")`，例如 `"2026-03-01T09:30:00"`
- **原子性**：任何方法抛出异常时，系统状态不能有任何改变
- 检查顺序：先检查参数本身（`ValidationError`），再查找对象（`NotFoundError`），最后检查状态、库存、优惠券等业务条件

## 1. 异常（`shopkit/errors.py`）

| 异常 | 父类 | 什么时候抛出 |
|---|---|---|
| `ShopError` | `Exception` | 所有业务异常的基类 |
| `ValidationError` | `ShopError` | 参数类型或取值不合法 |
| `NotFoundError` | `ShopError` | 商品、订单不存在；从订单里删除订单中没有的商品；读取不存在的存档文件 |
| `StockError` | `ShopError` | 可用库存不足；库存调整后在手数量小于已预留数量 |
| `StateError` | `ShopError` | 订单当前状态不允许这个操作 |
| `CouponError` | `ShopError` | 优惠券不可用：不存在、已被使用、已过期、未达到最低消费 |

## 2. 金额（`shopkit/money.py`）

- `parse_money(value) -> Decimal`
  - 接受 `str`、`int`、`Decimal`。`bool`、`float` 和其他类型一律 `ValidationError`
  - 字符串先去掉首尾空白再解析，解析失败 `ValidationError`
  - 必须是有限数（不能是 NaN、Infinity）、`>= 0`、最多两位小数（`"1.5"` 可以，`"1.234"` 不行），否则 `ValidationError`
  - 返回保留两位小数的 `Decimal`：`parse_money("5")` → `Decimal("5.00")`
- `round_money(d: Decimal) -> Decimal`：四舍五入到两位小数（`ROUND_HALF_UP`），例如 `0.125` → `0.13`
- `format_money(d: Decimal) -> str`：先 `round_money`，再格式化成两位小数的字符串，例如 `Decimal("3")` → `"3.00"`，`Decimal("-3.5")` → `"-3.50"`

## 3. 商品目录

商品有：`sku`、`name`、`price`（当前价格）、`category`、`active`（是否上架）。

- `add_product(sku, name, price, category, active=True) -> dict`
  - `sku`：字符串，必须完全匹配正则 `[A-Z0-9-]{1,20}`；已经存在 → `ValidationError`
  - `name`：字符串，去掉首尾空白后不能为空，保存去掉空白后的值
  - `price`：按 `parse_money` 解析，并且必须 `> 0`
  - `category`：字符串，**去掉首尾空白并转成小写**后不能为空，保存规范化后的值。下文所有接收类别的参数都按同样的方式规范化
  - `active`：必须是 `bool`
  - 返回值同 `get_product`
- `get_product(sku) -> dict`：`{"sku": str, "name": str, "price": "12.00", "category": str, "active": bool}`
- `update_price(sku, price) -> dict`：价格规则同上；返回更新后的商品。**已经下单（placed 及之后）的订单保留下单时的价格快照，不受影响**
- `set_active(sku, active) -> dict`：`active` 必须是 `bool`；返回更新后的商品
- `list_products(category=None, active_only=False) -> list[dict]`：按 `sku` 升序；给了 `category` 就只返回该类别的商品；`active_only=True` 时只返回上架商品

## 4. 库存

每个商品有 `on_hand`（在手数量）、`reserved`（已预留数量），`available = on_hand - reserved`。新商品都是 0。

- `receive(sku, qty) -> dict`：入库。`qty` 必须是 `int`（不能是 `bool`）且 `>= 1`。返回值同 `stock`
- `adjust(sku, delta, reason) -> dict`：盘点调整。`delta` 必须是 `int`（不能是 `bool`）且不能为 0；`reason` 是字符串，去掉首尾空白后不能为空。如果调整后 `on_hand < reserved`（包括 `on_hand` 变成负数）→ `StockError`。返回值同 `stock`
- `stock(sku) -> dict`：`{"on_hand": int, "reserved": int, "available": int}`
- `set_reorder_level(sku, level) -> dict`：补货线，`level` 是 `int`（不能是 `bool`）且 `>= 0`，默认 0。返回值同 `stock`
- `low_stock() -> list[dict]`：所有满足 `reorder_level > 0` 且 `available <= reorder_level` 的商品（上架与否都算），元素为 `{"sku": str, "available": int, "reorder_level": int}`，按 `sku` 升序
- `stock_log(sku) -> list[dict]`：库存流水，按发生顺序，元素为 `{"at": 事件时间, "change": int, "reason": str}`
  - `receive` 记一条：`change` 为入库数量，`reason` 为 `"receive"`
  - `adjust` 记一条：`change` 为 `delta`，`reason` 为去掉首尾空白后的原因
  - 订单发货（见第 7 节 `ship`）为每一行记一条：`change` 为负的数量，`reason` 为 `"ship O0001"` 这样的格式（订单号）
  - 预留和释放预留不记流水

以上方法的 `sku` 不存在时 → `NotFoundError`。

## 5. 定价

### 5.1 规则设置

- `set_tier_price(sku, min_qty, unit_price)`：阶梯价。`min_qty` 是 `int`（不能是 `bool`）且 `>= 2`；`unit_price` 按 `parse_money` 解析且 `> 0`；`sku` 必须存在。同一个 `sku` 同一个 `min_qty` 再次设置会覆盖
- `clear_tier_prices(sku)`：删除这个商品的所有阶梯价
- `set_category_discount(category, percent)`：类别折扣。`percent` 是 `int`（不能是 `bool`），取值 0～90；设为 0 表示取消。不要求这个类别已经有商品
- `set_tax_rate(category, rate)`：类别税率，表示百分比（`"13"` 就是 13%）。按 `parse_money` 解析（非负、最多两位小数），并且 `<= 30`。没有设置过的类别税率为 0

### 5.2 计算规则

对购物清单里的每一行（一个 `sku` 和数量 `qty`），按顺序计算：

1. **单价** `unit_price`：商品当前价格；如果这个商品有阶梯价，并且 `qty` 大于等于某些阶梯的 `min_qty`，就用其中 `min_qty` **最大**的那个阶梯价
2. **行金额** `line_total = unit_price × qty`
3. **类别折扣** `discount = round_money(line_total × 该商品类别的折扣百分比 / 100)`
4. **折后金额** `net = line_total - discount`

然后：

5. **小计** `subtotal` = 所有行 `net` 之和
6. **优惠券折扣** `coupon_discount`：见第 6 节；没有优惠券时为 0
7. **优惠券分摊**：把 `coupon_discount` 按各行 `net` 的比例分到各行，得到每行的 `coupon_share`。按行的顺序，除最后一行外，`coupon_share = round_money(coupon_discount × net / subtotal)`；**最后一行** `coupon_share = coupon_discount - 其他各行 coupon_share 之和`（保证总和正好等于 `coupon_discount`）。没有优惠券时每行都是 0
8. **税** 每行 `tax = round_money((net - coupon_share) × 该商品类别的税率 / 100)`；总税额 `tax` = 各行 `tax` 之和
9. **应付总额** `total = subtotal - coupon_discount + tax`

### 5.3 报价

- `quote(items, coupon=None) -> dict`：按当前的商品、价格和规则计算一张购物清单，**不检查库存，不产生任何副作用**（不占用优惠券）
  - `items`：非空列表，每个元素是 `{"sku": str, "qty": int}`。列表为空、元素不是这个格式、`qty` 不是 `>= 1` 的 `int`（不能是 `bool`）→ `ValidationError`
  - 同一个 `sku` 出现多次时合并数量，这一行的位置按它**第一次出现**的位置
  - `sku` 不存在 → `NotFoundError`；商品已下架 → `ValidationError`
  - `coupon`：`None` 或优惠券代码（字符串，按第 6 节的方式规范化）；不可用 → `CouponError`
  - 返回：

```python
{
    "lines": [  # 顺序同合并后的清单
        {"sku": "A-1", "category": "food", "qty": 3, "unit_price": "10.00", "line_total": "30.00",
         "discount": "3.00", "net": "27.00", "coupon_share": "2.70", "tax": "2.19"},
    ],
    "subtotal": "27.00",
    "coupon": "SAVE10",        # 没用优惠券时为 None
    "coupon_discount": "2.70",
    "tax": "2.19",
    "total": "26.49",
}
```

## 6. 优惠券

- `add_coupon(code, kind, value, min_subtotal="0", expires=None) -> dict`
  - `code`：字符串，**去掉首尾空白并转成大写**后必须完全匹配 `[A-Z0-9]{3,16}`，并且不能已经存在。所有接收优惠券代码的参数都按同样的方式规范化
  - `kind`：`"fixed"`（减固定金额）或 `"percent"`（按比例打折）
  - `value`：`fixed` 时按 `parse_money` 解析且 `> 0`；`percent` 时是 `int`（不能是 `bool`），取值 1～100
  - `min_subtotal`：最低消费，按 `parse_money` 解析
  - `expires`：`None` 或 `"YYYY-MM-DD"` 格式（必须正好 10 个字符）的合法日期。**到期当天仍然可用**，`clock()` 的日期晚于它才算过期
  - 以上不合法 → `ValidationError`。返回值同 `get_coupon`
- `get_coupon(code) -> dict`：`{"code": str, "kind": str, "value": "5.00"（fixed）或 15（percent，int）, "min_subtotal": "0.00", "expires": "2026-12-31" 或 None, "used_by": 订单号或 None}`。不存在 → `NotFoundError`
- **可用条件**（报价和下单时检查）：存在、没有被占用（`used_by` 为 `None`）、没有过期、`subtotal >= min_subtotal`。任何一条不满足都是 `CouponError`（包括代码不存在）
- **折扣金额**：`fixed` 为 `min(value, subtotal)`；`percent` 为 `round_money(subtotal × value / 100)`
- **一张券只能用于一个订单**：下单（`place_order`）成功时被这个订单占用（`used_by` = 订单号）；这个订单被取消时释放（`used_by` 恢复为 `None`）

## 7. 订单

- 订单号是 `"O"` 加 4 位数字，从 `O0001` 开始递增，取消的订单不回收号码
- 状态：`draft`（草稿）→ `placed`（已下单）→ `paid`（已付款）→ `shipped`（已发货）→ `delivered`（已送达）；`draft`、`placed`、`paid` 可以取消 → `cancelled`
- 每次状态变化（包括创建时的 `draft`）都在订单的 `events` 里追加 `{"at": 事件时间, "status": 新状态}`
- 以下方法的 `order_id` 不存在 → `NotFoundError`；状态不允许 → `StateError`

方法：

- `create_order(customer, items=None, coupon=None) -> str`：创建草稿，返回订单号
  - `customer`：字符串，去掉首尾空白后不能为空，保存去掉空白后的值
  - `items`：`None` 或格式同 `quote` 的列表（这里**允许空列表**）；同样合并重复的 `sku`，`sku` 必须存在且已上架
  - `coupon`：`None` 或优惠券代码（字符串）。创建时只保存规范化后的代码，下单时才检查是否可用
- `add_item(order_id, sku, qty) -> dict`：只能在 `draft` 状态；`qty` 规则同 `quote`；`sku` 必须存在且已上架；订单里已经有这个 `sku` 就把数量加上去，否则追加到末尾。返回 `get_order` 的结果
- `remove_item(order_id, sku) -> dict`：只能在 `draft` 状态；订单里没有这个 `sku` → `NotFoundError`
- `set_coupon(order_id, coupon) -> dict`：只能在 `draft` 状态；`coupon` 为 `None` 表示去掉优惠券
- `place_order(order_id) -> dict`：下单，只能在 `draft` 状态
  - 订单里没有商品 → `ValidationError`
  - 按当前价格和规则计算报价（同 `quote`，包括优惠券检查和下架检查）
  - 每一行的数量都不能超过该商品的 `available` → 否则 `StockError`
  - 全部检查通过后：每行预留库存（`reserved` 加上数量）、占用优惠券、保存这次的报价作为订单的 `pricing`（价格快照），状态变为 `placed`
- `pay(order_id, amount) -> dict`：只能在 `placed` 状态；`amount` 按 `parse_money` 解析，并且必须**正好等于** `pricing` 里的 `total`，否则 `ValidationError`。记录付款金额，状态变为 `paid`
- `ship(order_id) -> dict`：只能在 `paid` 状态。每一行：`on_hand` 和 `reserved` 都减去数量，并记一条库存流水（见第 4 节）。状态变为 `shipped`
- `deliver(order_id) -> dict`：只能在 `shipped` 状态，状态变为 `delivered`
- `cancel(order_id, reason) -> dict`：`reason` 是字符串，去掉首尾空白后不能为空。只能在 `draft`、`placed`、`paid` 状态
  - `placed`、`paid`：释放预留（`reserved` 减去各行数量），释放优惠券
  - `paid`：记录退款，金额等于付款金额
  - 保存取消原因（去掉首尾空白），状态变为 `cancelled`
- `get_order(order_id) -> dict`：

```python
{
    "id": "O0001",
    "customer": "张三",
    "status": "placed",
    "items": [{"sku": "A-1", "qty": 3}],   # 按加入顺序
    "coupon": "SAVE10",                    # 或 None
    "pricing": {...},                      # 下单时 quote 的结果；草稿状态为 None
    "paid": "26.49",                       # 付款金额；没付款为 None
    "refund": None,                        # 退款金额；没有退款为 None
    "cancel_reason": None,
    "events": [{"at": "2026-03-01T09:30:00", "status": "draft"}, ...],
}
```

- `list_orders(status=None, customer=None) -> list[dict]`：元素同 `get_order`，按订单号升序。`status` 不是合法状态 → `ValidationError`；`customer` 按去掉首尾空白后的值精确匹配

`add_item`、`remove_item`、`set_coupon`、`place_order`、`pay`、`ship`、`deliver`、`cancel` 都返回操作后的 `get_order` 结果。

## 8. 报表

"已发货订单"指状态为 `shipped` 或 `delivered` 的订单；它的**发货日期**是状态变为 `shipped` 的那条事件的日期（`at` 的前 10 个字符）。报表里的金额都来自订单的 `pricing` 快照。

- `sales_report(start, end) -> dict`：统计发货日期在 `[start, end]`（含两端）内的已发货订单
  - `start`、`end` 是 `"YYYY-MM-DD"` 格式（正好 10 个字符）的合法日期，`start` 晚于 `end` → `ValidationError`
  - 返回：

```python
{
    "orders": 2,               # 订单数
    "units": 7,                # 商品件数之和
    "subtotal": "100.00",      # 各订单 subtotal 之和
    "coupon_discount": "5.00", # 之和
    "tax": "12.35",            # 之和
    "revenue": "107.35",       # 各订单 total 之和
    "by_category": [           # 按类别汇总各行，net 降序，相同时按 category 升序
        {"category": "food", "units": 4, "net": "60.00"},
    ],
}
```

  `by_category` 里的 `net` 是各行 `net`（优惠券分摊之前）之和，类别取下单时快照里的类别。
- `top_products(limit=5, start=None, end=None) -> list[dict]`：已发货订单里各商品的件数，元素为 `{"sku": str, "units": int}`，按 `units` 降序、相同时按 `sku` 升序，取前 `limit` 个。`limit` 是 `int`（不能是 `bool`）且 `>= 1`；`start`、`end` 可以只给一个，给了就按发货日期过滤（含端点），格式要求同上
- `inventory_value() -> str`：所有商品（包括下架的）`on_hand × 当前价格` 之和

## 9. 持久化

- `save(path)`：把全部状态写进一个 UTF-8 的 JSON 文件。先写到同目录下的临时文件，再替换目标文件
- `Shop.load(path, clock=None) -> Shop`：类方法，读取 `save` 写出的文件，恢复全部状态：商品、库存、预留、补货线、库存流水、阶梯价、类别折扣、税率、优惠券（包括占用情况）、订单（包括价格快照、付款、退款、事件）以及下一个订单号。恢复后所有方法的行为和保存前完全一致。文件不存在 → `NotFoundError`

## 10. 代码组织（建议）

按职责拆成多个模块，例如：`errors.py`、`money.py`、`catalog.py`、`inventory.py`、`pricing.py`、`coupons.py`、`orders.py`、`reports.py`、`storage.py`，由 `shop.py` 里的 `Shop` 组合起来，在 `__init__.py` 里导出。
