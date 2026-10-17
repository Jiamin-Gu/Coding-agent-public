# large_spec_shop

由 Coding-agent 在评测中完成（模型 `deepseek-v4-flashteam-always`，评测 `20261011-113509-deepseek-v4-flashteam-always`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

按照 `docs/SPEC.md` 的需求文档，从零实现 `shopkit` 包：商品、库存、定价、优惠券、订单、报表和持久化。

接口、返回值格式、金额计算和错误类型都要严格符合文档。请为各项功能编写 pytest 测试，并确保全部通过。

## 结果

- 隐藏测试复验：**通过**（98 passed in 0.26s）
- 调用模型 154 次，工具调用 211 次（其中出错 4 次），运行命令 68 条，耗时 1189 秒
- token：输入 5,229,702（命中缓存 2,734,464），输出 195,619

## agent 新建或修改的文件

- `shopkit/__init__.py`（新建）
- `shopkit/catalog.py`（新建）
- `shopkit/coupons.py`（新建）
- `shopkit/errors.py`（新建）
- `shopkit/inventory.py`（新建）
- `shopkit/money.py`（新建）
- `shopkit/orders.py`（新建）
- `shopkit/pricing.py`（新建）
- `shopkit/reports.py`（新建）
- `shopkit/shop.py`（新建）
- `shopkit/storage.py`（新建）
- `tests/acceptance/test_catalog.py`（新建）
- `tests/acceptance/test_coupons.py`（新建）
- `tests/acceptance/test_errors.py`（新建）
- `tests/acceptance/test_inventory.py`（新建）
- `tests/acceptance/test_money.py`（新建）
- `tests/acceptance/test_orders.py`（新建）
- `tests/acceptance/test_pricing.py`（新建）
- `tests/acceptance/test_reports.py`（新建）
- `tests/acceptance/test_storage.py`（新建）

## 团队分工（团队模式）

主 agent 拆分的任务（每个任务由一个子 agent 完成，只能写自己负责的文件）：

- **tester-core** [done]：tests/acceptance/test_errors.py, tests/acceptance/test_money.py, tests/acceptance/test_catalog.py, tests/acceptance/test_inventory.py
- **tester-pricing** [done]：tests/acceptance/test_coupons.py, tests/acceptance/test_pricing.py
- **tester-orders** [done]：tests/acceptance/test_orders.py, tests/acceptance/test_reports.py, tests/acceptance/test_storage.py
- **catalog** [done]：shopkit/catalog.py
- **coupons** [done]：shopkit/coupons.py
- **inventory** [done]：shopkit/inventory.py
- **pricing** [done]：shopkit/pricing.py
- **orders** [done]：shopkit/orders.py
- **reports** [done]：shopkit/reports.py
- **storage** [done]：shopkit/storage.py
- **security** [done]：

接口契约：

- **errors**（lead）：shopkit/errors.py（已实现，直接导入使用）：
- ShopError(Exception)：所有业务异常基类
- ValidationError(ShopError)：参数类型或取值不合法
- NotFoundError(ShopError)：商品、订单不存在；从订单里删除订单中没有的商品；读取不存在的存档文件
- StockError(ShopError)：可用库存不足；库存调整后在手数量小于已预留数量
- StateError(ShopError)：订单当前状态不允许这个操作
- CouponError(ShopError)：优惠券不可用：不存在、已被使用、已过期、未达到最低消费
- **money**（lead）：shopkit/money.py（已实现，直接导入使用）：
- parse_money(value) -> Decimal：接受 str/int/Decimal；bool、float、其他类型 → ValidationError；str 先 strip 再解析；必须 is_finite()、>=0、小数位 <=2（'1.234'、'1.230' 都拒绝）；返回 quantize 到 0.01 的 Decimal
- round_money(d: Decimal) -> Decimal：ROUND_HALF_UP 到两位小数
- format_money(d: Decimal) -> str：先 round 再两位小数字符串，如 '3.00'、'-3.50'
所有公开/内部金额一律 Decimal；对外输出一律 format_money 的字符串。
- **state**（lead）：Shop（shopkit/shop.py，已实现，勿改）的属性与方法：
- self._clock：无参函数，返回不带时区的 datetime；构造 Shop(clock=None) 时默认 datetime.now
- self._now() -> str：self._clock().isoformat(timespec="seconds")
- self._products: dict[sku(str) -> product]；product = {"sku":str,"name":str,"price":Decimal(两位),"category":str(小写),"active":bool}
- self._stock: dict[sku -> {"on_hand":int,"reserved":int,"reorder_level":int,"log":[{"at":str,"change":int,"reason":str}]}]
- self._tiers: dict[sku -> {min_qty(int): unit_price(Decimal)}]
- self._discounts: dict[category(小写) -> percent(int)]，0 表示无折扣
- self._tax_rates: dict[category(小写) -> Decimal(百分比)]，未设置视为 0
- self._coupons: dict[code -> {"code":str,"kind":"fixed"|"percent","value":Decimal(fixed)或int(percent),"min_subtotal":Decimal(两位),"expires":str|None,"used_by":订单号|None}]
- self._orders: dict[order_id -> order dict]（见 orders 契约）
- self._next_no: int，下一个订单号（从 1 起）
通用约定：所有接收 sku/code/category/order_id/customer 等应在 spec 中是字符串的参数，非 str 类型 → ValidationError（参数类型校验优先）；字符串参数的空白规范化见各契约。
类别规范化：strip + 转小写，规范化后非空；所有接收 category 的参数都规范化后保存/比较。
优惠券代码规范化：strip + 转大写（固定格式校验只在 add_coupon 时做）。
检查顺序：参数 ValidationError → 对象 NotFoundError → 业务条件（StateError/StockError/CouponError/ValidationError(下架、金额不匹配等)）。
原子性：任何方法抛异常时系统状态不能有任何改变。
- **catalog**（lead）：shopkit/catalog.py 的 CatalogMixin（通过 Shop 调用）：
- add_product(sku, name, price, category, active=True) -> dict：sku 必须 str 且完全匹配正则 [A-Z0-9-]{1,20}，已存在 → ValidationError；name str strip 后非空，保存 strip 后的值；price 用 parse_money 且 >0；category 规范化后非空；active 必须 bool。必须同时初始化 self._stock[sku] = {"on_hand":0,"reserved":0,"reorder_level":0,"log":[]}。返回值同 get_product。
- get_product(sku) -> dict：{"sku":str,"name":str,"price":"12.00","category":str,"active":bool}（price 是字符串）；不存在 → NotFoundError
- update_price(sku, price) -> dict：价格规则同 add_product；不影响已下单订单的价格快照；返回更新后的商品
- set_active(sku, active) -> dict：active 必须 bool；返回更新后的商品
- list_products(category=None, active_only=False) -> list[dict]：按 sku 升序；category 给出时规范化后过滤；active_only=True 只返回上架商品
- 辅助：_get_product(sku) -> dict（不存在 → NotFoundError）；_normalize_category(value) -> str（非 str 或 strip+lower 后为空 → ValidationError）
以上方法内部金额用 Decimal；返回 dict 可返回拷贝（防止外部篡改内部状态）。
- **inventory**（lead）：shopkit/inventory.py 的 InventoryMixin（通过 Shop 调用）：
- receive(sku, qty) -> dict：qty 必须 int 且不能是 bool、>=1；不存在 → NotFoundError；on_hand += qty；记流水 {"at":self._now(),"change":qty,"reason":"receive"}；返回 stock 结果
- adjust(sku, delta, reason) -> dict：delta 必须 int 非 bool 且 !=0；reason str strip 后非空（保存 strip 后的值）；调整后 on_hand < reserved（含负数）→ StockError；记流水 reason 为 strip 后的原因
- stock(sku) -> dict：{"on_hand":int,"reserved":int,"available":int}（available=on_hand-reserved）
- set_reorder_level(sku, level) -> dict：level int 非 bool、>=0
- low_stock() -> list[dict]：所有 reorder_level>0 且 available<=reorder_level 的商品（含下架），元素 {"sku":str,"available":int,"reorder_level":int}，按 sku 升序
- stock_log(sku) -> list[dict]：按发生顺序返回 {"at":str,"change":int,"reason":str} 列表
- 供 OrderMixin 使用：_reserve(sku,qty)：reserved+=qty；_release(sku,qty)：reserved-=qty；_consume(sku,qty)：on_hand-=qty 且 reserved-=qty（不记流水，流水由订单模块记）；_available(sku)->int
- 校验顺序：参数 VE → sku 不存在 NotFoundError → 业务条件；所有方法都不能让 on_hand < reserved
- **coupons**（lead）：shopkit/coupons.py 的 CouponMixin（通过 Shop 调用）：
- add_coupon(code, kind, value, min_subtotal="0", expires=None) -> dict：code 规范化后须完全匹配 [A-Z0-9]{3,16} 且不存在（重复 → ValidationError）；kind ∈ {"fixed","percent"}；fixed 的 value 用 parse_money 且 >0；percent 的 value 必须 int 非 bool、1~100；min_subtotal 用 parse_money；expires 为 None 或正好 10 字符的合法 YYYY-MM-DD（用 date.fromisoformat 校验，非法 → ValidationError）。返回值同 get_coupon
- get_coupon(code) -> dict：{"code":str,"kind":str,"value":"5.00"(fixed 字符串)|15(percent 保持 int),"min_subtotal":"0.00","expires":"2026-12-31"|None,"used_by":订单号|None}；不存在 → NotFoundError
- 辅助（供 PricingMixin/OrderMixin 用 self 调用）：
  - _normalize_code(v) -> str：非 str → ValidationError；返回 strip+upper
  - _is_expired(coupon) -> bool：expires 非 None 且 self._clock().date().isoformat() > expires（到期当天可用）
  - _check_coupon_available(code, subtotal: Decimal) -> dict：先 _normalize_code；不存在 / used_by 非 None / _is_expired / subtotal < min_subtotal → CouponError；通过则返回内部 coupon dict
  - _coupon_discount(coupon, subtotal: Decimal) -> Decimal：fixed → min(value, subtotal)；percent → round_money(subtotal*value/100)
- **pricing**（lead）：shopkit/pricing.py 的 PricingMixin（通过 Shop 调用）：
- set_tier_price(sku, min_qty, unit_price)：min_qty int 非 bool、>=2；unit_price parse_money 且 >0；sku 不存在 → NotFoundError；同 sku 同 min_qty 覆盖
- clear_tier_prices(sku)：sku 不存在 → NotFoundError；删除该 sku 全部阶梯价
- set_category_discount(category, percent)：percent int 非 bool、0~90（0 表示取消）；类别规范化后保存
- set_tax_rate(category, rate)：rate 用 parse_money（非负、最多两位小数）且 <=30；未设置过的类别税率为 0
- quote(items, coupon=None) -> dict：
  - items 必须非空 list；元素必须 dict 且键恰为 {"sku","qty"}、sku 为 str、qty 为 int 非 bool 且 >=1，否则 ValidationError；空列表 → ValidationError
  - 同 sku 合并数量，行位置取第一次出现的位置
  - sku 不存在 → NotFoundError；商品已下架 → ValidationError
  - coupon 为 None 或 str（非 None 非 str → ValidationError）；规范化后用 self._check_coupon_available(code, subtotal) 检查可用性
  - 计算（全部 Decimal，输出 format_money 字符串）：unit_price（有阶梯且 qty>=某 min_qty 时取 min_qty 最大的阶梯价，否则商品当前价）→ line_total=unit_price*qty → discount=round_money(line_total*折扣%/100) → net=line_total-discount → subtotal=Σnet → coupon_discount=self._coupon_discount(...)（无券为 0）→ 每行 coupon_share（除最后一行 round_money(coupon_discount*net/subtotal)，最后一行 = coupon_discount-其他行之和；无券全 0.00）→ 每行 tax=round_money((net-coupon_share)*税率%/100) → total=subtotal-coupon_discount+tax
  - 返回 {"lines":[{"sku","category","qty","unit_price","line_total","discount","net","coupon_share","tax"}],"subtotal":str,"coupon":code|None,"coupon_discount":str,"tax":str,"total":str}
  - 不检查库存、无副作用
- **orders**（lead）：shopkit/orders.py 的 OrderMixin（通过 Shop 调用）：
内部 order dict（get_order 的返回即此结构）：{"id":str,"customer":str,"status":str,"items":[{"sku":str,"qty":int}]（按加入顺序，同 sku 合并）,"coupon":str|None（规范化后的代码）,"pricing":dict|None（place 时 quote 的完整结果；draft 为 None）,"paid":str|None,"refund":str|None,"cancel_reason":str|None,"events":[{"at":str,"status":str}]}
订单号：f"O{self._next_no:04d}"，创建后 self._next_no += 1（不回收）。
合法状态：draft、placed、paid、shipped、delivered、cancelled。
- create_order(customer, items=None, coupon=None) -> str：customer str strip 后非空；items None 或同 quote 的格式（允许空列表；合并重复 sku；sku 必须存在且上架）；coupon None 或 str（非 str 非 None → VE），只存规范化代码；创建时追加事件 {"at":self._now(),"status":"draft"}
- add_item(order_id, sku, qty) -> dict：只在 draft；qty 规则同 quote；sku 必须存在且上架；已有则 qty 相加，否则追加到末尾；返回 get_order
- remove_item(order_id, sku) -> dict：只在 draft；订单里没有该 sku → NotFoundError
- set_coupon(order_id, coupon) -> dict：只在 draft；None 表示去掉优惠券；str 存规范化代码
- place_order(order_id) -> dict：只在 draft；无商品 → ValidationError；先 self.quote(items, coupon)（含优惠券可用性与下架检查）；逐行 qty <= self._available(sku) 否则 StockError；全部通过后：每行 self._reserve(sku,qty)、优惠券 used_by=order_id（若有）、pricing=quote 结果、追加 placed 事件
- pay(order_id, amount) -> dict：只在 placed；amount 用 parse_money 且必须正好等于 pricing['total']（否则 ValidationError）；paid=format_money(amount)；追加 paid 事件
- ship(order_id) -> dict：只在 paid；每行 self._consume(sku,qty) 并记流水 {"at":self._now(),"change":-qty,"reason":f"ship {order_id}"}；追加 shipped 事件（防御性：任一行的 on_hand < qty 应先抛 StockError，保证原子性）
- deliver(order_id) -> dict：只在 shipped；追加 delivered 事件
- cancel(order_id, reason) -> dict：reason str strip 后非空（保存 strip 值）；只在 draft/placed/paid；placed/paid 时每行 self._release(sku,qty)、若优惠券 used_by==order_id 则置 None；paid 时 refund=paid（字符串）；cancel_reason 保存；追加 cancelled 事件
- get_order(order_id) -> dict：不存在 → NotFoundError；返回副本
- list_orders(status=None, customer=None) -> list[dict]：status 非 None 且不在合法状态 → ValidationError；customer 为 strip 后的值精确匹配；按订单号升序（字符串序）
所有返回 dict 的方法返回操作后的 get_order 结果。任何失败路径都不得留下部分修改。
- **reports**（lead）：shopkit/reports.py 的 ReportMixin（通过 Shop 调用）：
"已发货订单" = status ∈ {shipped, delivered}；发货日期 = 该订单 events 中 status=='shipped' 的事件 at[:10]。金额一律来自 pricing 快照（字符串 → Decimal 再求和 → format_money）。
- sales_report(start, end) -> dict：start/end 必须 str、正好 10 字符、合法 YYYY-MM-DD（否则 ValidationError）；start > end → ValidationError。统计发货日期在 [start,end]（含）的已发货订单：{"orders":int,"units":int,"subtotal":str,"coupon_discount":str,"tax":str,"revenue":str,"by_category":[{"category":str,"units":int,"net":str}]}
  - units = 各订单 pricing.lines 的 qty 之和；subtotal/coupon_discount/tax = pricing 对应字段之和；revenue = pricing.total 之和
  - by_category 按 pricing.lines 的 category 汇总 qty 与 net（优惠券分摊之前的 net），按 net 降序、相同时 category 升序
- top_products(limit=5, start=None, end=None) -> list[dict]：limit int 非 bool、>=1；start/end 可只给一个，给了必须合法日期字符串（仅格式校验，start>end 不报错）；统计已发货订单各 sku 的件数（可按发货日期过滤），按 units 降序、相同时 sku 升序，取前 limit：{"sku":str,"units":int}
- inventory_value() -> str：所有商品（含下架）on_hand × 当前价格 之和
- **storage**（lead）：shopkit/storage.py 的 StorageMixin（通过 Shop 调用）：
- save(path)：把全部状态写成 UTF-8 JSON；先写同目录下的临时文件（tempfile 或 path+'.tmp'），再 os.replace 替换目标；任何失败都不能破坏原文件
- @classmethod load(cls, path, clock=None) -> Shop：文件不存在 → NotFoundError；恢复全部状态（商品、库存、预留、补货线、库存流水、阶梯价、类别折扣、税率、优惠券含 used_by、订单含 pricing/paid/refund/events、下一个订单号），之后行为与保存前完全一致
JSON 键名约定：{"version":1,"products":{sku:{...price 为字符串}},"stock":{sku:{"on_hand","reserved","reorder_level","log"}},"tiers":{sku:{str(min_qty):价格字符串}},"discounts":{category:int},"tax_rates":{category:字符串},"coupons":{code:{...value(fixed 为字符串)/min_subtotal 字符串/expires/used_by}},"orders":{order_id:order dict},"next_no":int}
恢复时 Decimal 用 Decimal(str)；tiers 的键转回 int。

黑板上的决策和留言：

- [decision] tester-core → all：tester-core 验收测试已就绪（tests/acceptance/test_errors.py、test_money.py、test_catalog.py、test_inventory.py，共 139 用例，全部可 collect；errors+money 当前 47 passed，catalog/inventory 依赖实现，允许暂时失败）。几点假设/约定，供实现方对齐：
1) 验证 add_product 初始化库存时，测试走公开 API shop.stock(sku)，期望 {"on_hand":0,"reserved":0,"available":0}，因此 catalog 与 inventory 需同时满足契约。
2) test_inventory 用契约里注明的内部方法 shop._reserve/_release 构造 reserved>0 场景（adjust 后 on_hand<reserved → StockError；reserve/release 不记流水）。
3) 钉住全局检查顺序：update_price(nonexistent, "abc") 必须 ValidationError（参数先于 NotFoundError）；receive(nonexistent, 0)/adjust(nonexistent, 0, "x") 同理必须 ValidationError。
4) parse_money 拒绝 "1.230"（小数位<=2，含尾随零）与 bool/float；format_money 先 round_money(ROUND_HALF_UP)。
- [decision] tester-orders → all：tester-orders 验收测试已就绪并全部可 collect（tests/acceptance/test_orders.py 27、test_reports.py 14、test_storage.py 10，共 51）。实现方请注意以下断言点：

1) get_order 副本：仅断言顶层可变（改 order["status"] 后 get_order 不变），未强制深拷贝。
2) create_order 只规范化保存 coupon 代码、不检查存在性（未测未知代码报错）；下单 place_order 时才触发 CouponError（min_subtotal 未达标场景已覆盖）。
3) 报表金额全部取自 pricing 快照的字符串；by_category 的 net 用优惠券分摊之前的 net（test_sales_report_sums_tax_and_coupon 固定 food 税率 10%、fixed 券 5 元：subtotal 10.00 / coupon_discount 5.00 / tax 0.50 / revenue 5.50 / category net 10.00）。
4) save 成功后同目录不得残留临时文件（test_save_leaves_no_temp_files 断言目录里只剩目标文件）。
5) Shop.load(path, clock=...) 必须用传入 clock 产生事件时间。
6) JSON 约定：version==1、products.price 为字符串、fixed 券 value 为字符串、percent 券 value 为 int。
- [decision] tester-pricing → all：tester-pricing 验收测试已就绪并全部可 collect（tests/acceptance/test_coupons.py 22 函数/60 用例，tests/acceptance/test_pricing.py 25 函数/63 用例）。当前失败均为实现未完成（NotImplementedError），无 collect/import 错误。实现方请对齐以下断言点：

1) add_coupon 返回格式：fixed 的 value 为 "5.00" 字符串，percent 的 value 保持 int（15）；code 规范化 strip+upper；min_subtotal 默认 "0.00"；expires 默认 None；used_by 默认 None。
2) expires 校验：None 合法；非 str（如 20261231）→ ValidationError；必须正好 10 字符且 date.fromisoformat 合法。
3) _check_coupon_available(code, subtotal)：不存在/used_by 非 None/_is_expired/subtotal<min_subtotal → CouponError；subtotal>=min_subtotal 含等号通过；返回内部 coupon dict。
4) _is_expired：expires 非 None 且 clock().date().isoformat() > expires（到期当天可用）。测试用 FixedClock=2026-01-15。
5) _coupon_discount：fixed=min(value,subtotal)；percent=round_money(subtotal*value/100)，HALF_UP（15%*0.10=0.02）。
6) quote 元素键必须恰为 {sku,qty}（多键/缺键 → VE）；items 空列表/非 list → VE；coupon 非 None 非 str → VE（不是 CouponError）。
7) quote 无副作用：不占用券（used_by 保持 None）、不预留库存（_stock[sku].reserved==0）。
8) coupon_share 最后一行补差（3 行各 net 1.00、fixed 券 1.00 → 0.33/0.33/0.34）；spec 5.3 示例用 类别折扣10%+税率9%+percent券10%，total=26.49。
9) 优惠券可用性也通过 quote 验证（未达最低消费/已占用/过期 → CouponError；到期当天可用）；占用场景直接置 shop._coupons[code]["used_by"]（不依赖 orders 模块）。
- [decision] coupons → all：coupons 完成。shopkit/coupons.py 实现 CouponMixin：add_coupon/get_coupon/_normalize_code/_is_expired/_check_coupon_available/_coupon_discount。
内部 coupon dict: {"code":str,"kind":"fixed"|"percent","value":Decimal(fixed)或int(percent),"min_subtotal":Decimal,"expires":str|None,"used_by":None}。
_check_coupon_available 通过时返回内部 coupon dict（PricingMixin 可直接传给 _coupon_discount）。_coupon_discount 接受内部 coupon dict（用 coupon["kind"]/["value"]）。get_coupon 每次返回新 dict，外部改动不影响内部状态。
验证：python -m pytest tests/acceptance/test_coupons.py -q → 60 passed。
- [decision] catalog → lead：catalog 完成。shopkit/catalog.py 实现 CatalogMixin：add_product/get_product/update_price/set_active/list_products/_get_product/_normalize_category。
内部 product dict：{"sku":str,"name":str(strip后),"price":Decimal(两位),"category":str(小写strip),"active":bool}；对外 get_product/list_products 返回的是新 dict，price 为 format_money 字符串，外部改动不影响内部。
add_product 校验顺序：sku 类型→sku 正则[ A-Z0-9-]{1,20}→name→price(parse_money>0)→category→active→重复校验；成功后 self._stock[sku]={"on_hand":0,"reserved":0,"reorder_level":0,"log":[]}。
update_price/set_active 均先做参数校验（ValidationError）再查 sku（NotFoundError），符合钉住的检查顺序。
_get_product 内部对非 str 抛 ValidationError、不存在抛 NotFoundError。
验证：python -m pytest tests/acceptance/test_catalog.py tests/acceptance/test_money.py tests/acceptance/test_errors.py -q → 97 passed, 1 failed。唯一失败是 test_add_product_initializes_zero_stock，因为它调用 shop.stock()，而 shopkit/inventory.py 仍是 stub（NotImplementedError），不属于本任务。已用脚本确认 self._stock[sku] 初始化为 {"on_hand":0,"reserved":0,"reorder_level":0,"log":[]}，等 inventory 实现后该用例会自动通过。
- [decision] pricing → all：pricing 完成。shopkit/pricing.py 实现 PricingMixin：set_tier_price/clear_tier_prices/set_category_discount/set_tax_rate/quote。验证：python -m pytest tests/acceptance/test_pricing.py tests/acceptance/test_coupons.py -q → 123 passed。

实现要点（供 orders/reports/storage 参考）：
1) set_tier_price 先校验 min_qty(int非bool,>=2) 与 unit_price(parse_money,>0)，再 _get_product(sku)（参数 VE 优先于 NotFound）；同 sku 同 min_qty 覆盖。
2) quote 检查顺序：①items 结构校验（非空 list、元素恰为 {sku,qty}、sku str、qty int非bool>=1）②coupon 类型（None 或 str，否则 VE）③合并同 sku（保留首次位置）④逐行 _get_product(NotFound)，下架→VE ⑤计算 ⑥若有券用 self._check_coupon_available(规范化代码, subtotal)（CouponError）。
3) 计算：unit_price 取 min_qty 最大的匹配阶梯，否则商品现价；discount=round_money(line_total*折扣%/100)；net=line_total-discount；subtotal=Σnet；coupon_share 除最后一行按比例 round_money(cd*net/subtotal)、最后一行补差；tax=round_money((net-share)*税率%/100)；total=subtotal-cd+Σtax。
4) 内部规则用 self._tiers/_discounts/_tax_rates 存储（-discount/-tax_rates 的 key 为规范化小写类别）。quote 无副作用：不占用优惠券、不改库存。
5) 未设置类别税率视为 0。金额内部 Decimal，输出 format_money 字符串。
- [decision] inventory → lead：inventory 完成。shopkit/inventory.py 实现 InventoryMixin：receive/adjust/stock/set_reorder_level/low_stock/stock_log + 内部 _reserve/_release/_consume/_available。

给 OrderMixin 的接口约定（已实现）：
- _available(sku) -> int（on_hand - reserved）
- _reserve(sku, qty)：reserved += qty，不记流水
- _release(sku, qty)：reserved -= qty，不记流水
- _consume(sku, qty)：on_hand -= qty 且 reserved -= qty，不记流水（流水由 orders 在 ship 时记 {"at","change":-qty,"reason":f"ship {id}"}）
- 这些内部方法在 sku 不存在时抛 NotFoundError（sku 非 str 抛 ValidationError）。

新增内部辅助（其他 mixin 可复用，注意勿重名）：_get_stock(sku) -> 内部库存 dict（非 str→ValidationError，不存在→NotFoundError，按 self._stock 判定）；_stock_view(entry) -> {"on_hand","reserved","available"}。
校验顺序严格：参数 VE → sku 存在 NotFoundError → 业务 StockError；异常路径不改变状态。
验证：python -m pytest tests/acceptance/test_inventory.py -q → 41 passed；连同 test_catalog.py 92 passed。
- [decision] orders → all：orders 完成。shopkit/orders.py 实现 OrderMixin：create_order/add_item/remove_item/set_coupon/place_order/pay/ship/deliver/cancel/get_order/list_orders。验证：python -m pytest tests/acceptance/test_orders.py -q → 27 passed。

关键实现点（供 reports/storage 参考）：
1) 内部 order dict 结构与契约一致；get_order/list_orders 返回 copy.deepcopy，外部改动不影响内部。
2) 检查顺序：参数 VE → _get_order(NotFoundError) → 状态(StateError) → 对象/业务。create_order 中 items 结构校验(允许空列表) → 合并同 sku(保留首次位置) → _get_product(NotFound) → 下架(VE)；coupon 仅规范化保存、不查存在性。
3) place_order：先 self.quote(items, coupon)（含券可用性/下架），再逐行 qty<=_available 否则 StockError，全部通过后才 _reserve + 券 used_by=order_id + pricing 快照 + placed 事件（任一失败无副作用）。
4) ship：先防御性检查每行 on_hand>=qty，再逐行 _consume 并记流水 {"at":_now(),"change":-qty,"reason":f"ship {order_id}"}。
5) pay 用 parse_money 后与 Decimal(pricing["total"]) 精确比较；cancel 在 placed/paid 释放预留与券（used_by==order_id 才清），paid 时 refund=paid 字符串。
6) list_orders 按订单号字符串升序；status 非合法状态 → VE。
- [decision] reports → all：reports 完成。shopkit/reports.py 实现 ReportMixin（sales_report/top_products/inventory_value）。验证：python -m pytest tests/acceptance -q → 313 passed。

实现要点（供 storage/lead 参考）：
1) _parse_report_date：非 str → VE；长度必须 10；date.fromisoformat 校验非法 → VE。
2) 发货日期 = events 中 status=='shipped' 的事件 at[:10]；已发货订单 = status ∈ {shipped, delivered}，无 shipped 事件的跳过（防御）。
3) sales_report：start>end → VE；统计发货日期在 [start,end] 含端点；金额用 Decimal(字符串) 精确求和再 format_money；units 与 by_category 取 pricing.lines 的 qty 与快照 net（优惠券分摊前）。
4) by_category 排序：先按 category 升序，再稳定按 net(Decimal) 降序（等价于 net 降序、同 net 时 category 升序）。
5) top_products：limit 必须 int 非 bool 且 >=1；start/end 可只给一个，仅格式校验（start>end 不报错）；按 units 降序、同 units 时 sku 升序，取前 limit。排序用 (-units, sku) 元组 key。
6) inventory_value：遍历全部商品（含下架），Decimal 价格 × on_hand 求和，format_money 输出。
- [decision] storage → all：storage 完成。shopkit/storage.py 实现 StorageMixin.save/load。验证：python -m pytest tests/acceptance/test_storage.py -q → 10 passed；整套 tests/acceptance → 313 passed。

要点：
1) save：用 tempfile.mkstemp(dir=目标目录, prefix=".shopkit-", suffix=".tmp") 写 UTF-8 JSON(ensure_ascii=False)，再 os.replace 原子替换；任何异常都删除临时文件并原样抛出，原文件不受影响。成功后目录不残留临时文件。
2) JSON 键：version=1、products.price 字符串、stock(含 log)、tiers{sku:{str(min_qty):价格字符串}}、discounts{cat:int}、tax_rates{cat:字符串}、coupons{fixed value 字符串/percent value int、min_subtotal 字符串}、orders(整体 deepcopy)、next_no。orders 的 pricing/events 本就是纯字符串/int/None，直接按 JSON 存取。
3) load：cls(clock=clock) 构造后重建 _products/_stock/_tiers/_discounts/_tax_rates/_coupons/_orders/_next_no；Decimal 一律 Decimal(str(...))，tiers 键转 int，percent 券 value 保持 int。文件不存在(FileNotFoundError) → NotFoundError。
- [note] tester-core → all：tester-core 回归结果：python -m pytest tests/acceptance -q --tb=short → 313 passed in 1.01s（tests/acceptance 共 313 用例，含 errors 14/money 21/catalog 26/inventory 24 及其余模块测试）。无失败、无错误、无警告。我负责的 S2-S6 全绿。无需返工。
- [note] tester-orders → lead：tester-orders 复核完成：python -m pytest tests/acceptance -q → 313 passed in 0.69s，无失败/错误。我负责的 test_orders.py(27)/test_reports.py(14)/test_storage.py(10) 全部通过。无需上报失败项。各模块实现与 spec/契约在覆盖范围内一致。
- [note] tester-pricing → all：tester-pricing 回归结果：python -m pytest tests/acceptance -q --tb=short → 313 passed，0 failed / 0 error / 0 skip（0.55s）。我负责的 tests/acceptance/test_coupons.py + test_pricing.py 单独跑 → 123 passed。S7-S11 全部通过，无失败用例需要上报，无需返工。
- [question] security → lead：[security][低] shopkit/money.py:45 — 超大金额输入抛非 ShopError 异常，违反 S2/S3“取值不合法 → ValidationError”。

复现：parse_money('1e400') 或 parse_money('9'*40) → decimal.InvalidOperation（quantize 到 0.01 时系数超过上下文精度 28 位）。可达路径：任何接收金额的公开 API，如 Shop().add_product('A-1','a','9'*40,'food')、set_tax_rate、pay、add_coupon(min_subtotal/value) 都会向上泄漏 decimal.InvalidOperation 而不是 ValidationError。参数已通过 is_finite()/>=0/小数位 检查，但 magnitudes 未受限。

为什么算问题：调用方按契约只捕获 ShopError 系列，会漏接未处理异常，且错误类型与文档不符。非内存/DoS 类，影响面小。

修复：parse_money 里对 quantize 加保护，例如
    try:
        return d.quantize(_TWO_PLACES)
    except ArithmeticError:  # decimal.InvalidOperation 是其子类
        raise ValidationError(f"金额超出可表示范围：{value!r}") from None
（同样建议在解析后限制位数/量级。）
- [question] security → lead：[security][低] shopkit/orders.py:114-131(add_item) 与 133-144(remove_item) — 校验顺序颠倒，参数 VE 未优先于业务条件。

契约/S2 明确“参数类型校验优先：非 str 的 sku → ValidationError”，但这俩方法在检查 sku 类型之前先做了 `_get_order`(NotFound) 和 `_require_status`(StateError)。复现（已实测）：
- 已 placed 的订单上调用 add_item(oid, 123, 1) → StateError（应为 ValidationError）
- 已 placed 的订单上调用 remove_item(oid, 123) → StateError（应为 ValidationError）
draft 订单时不明显（因为 _get_product 会抛 VE），中招场景正是“非 draft 订单 + sku 类型非法”。

影响：仅异常类型与文档不符，无状态被修改、非可利用漏洞；且现有 313 用例未覆盖该组合。

修复：在 `order = self._get_order(order_id)` / `_require_status` 之前先做
    if not isinstance(sku, str): raise ValidationError(...)
（remove_item 里把第 138-139 行的 isinstance 检查提到方法开头；add_item 里在 `_validate_qty` 后、取订单前补一次 sku 类型检查或调整顺序。）
- [question] security → lead：[security][低] 多处“先改状态、后取 _now()”导致 clock 抛异常时状态被部分修改，违反 S2 绝对原子性（shopkit/orders.py:97-98 与 110；shopkit/inventory.py:44-45、68-71；orders ship/deliver/cancel 的 events 追加同理）。

复现（已实测，clock 为可注入的公开参数，测试里就用 FixedClock）：
- Shop(clock=会抛异常的) .create_order('c') → 抛 RuntimeError，但 self._next_no 已从 1 变成 2，且自增后没有生成订单（订单号被吞）。
- receive：先 `entry["on_hand"] += qty` 再 append 用 self._now() 的流水；clock 抛异常时 on_hand 已 +5，log 仍为 []，库存与流水不一致。

影响：只有 clock 抛异常时可达（datetime.now 不会），属边界情况；不会产生可被外部触发的资金/库存漏洞，故评低。

修复：在所有会改状态的方法里，先把所有 self._now() 时间戳算好（放在任何写操作之前），或把写操作与事件追加包在“先算后写”的两阶段里；create_order 里把 `_next_no += 1` 移到订单 dict 构造成功之后。
- [note] security → lead：[security] 只读审查 shopkit/ 全部实现（catalog/inventory/coupons/pricing/orders/reports/storage + money/shop/errors）结论，含中低风险硬化建议与“未发现问题”项：

已确认安全/正确（无需改）：
- 金额路径：全局无 float，parse_money/round_money/Decimal 运算，无 float()；无 eval/exec/pickle/yaml/subprocess/os.system/shell=True/SQL/日志泄漏密钥/弱随机（grep 全库仅命中 money.py 文档字符串）。
- temp 文件安全：storage.save 用 tempfile.mkstemp(dir=目标目录, prefix='.shopkit-', suffix='.tmp')（默认 0600），同目录写、os.replace 原子替换、异常清理临时文件。实测：序列化失败时原文件字节不变且目录无残留；成功 save 后目录只剩目标文件。
- 原子性（正常路径）：place_order 先 quote + 逐行可用库存检查，全部通过才 _reserve/占券/写快照；save 失败不破坏原文件；create_order 失败不消耗订单号（next_no 保持 1）。均已实测。
- 无 float 参与计算、quote 无副作用（不占券、不预留）、get_order/list_orders 返回 deepcopy。
- JSON 恢复完整性：save→load 实测恢复 products(name/price/category/active)、stock(on_hand/reserved/reorder_level/log)、tiers(键转 int)、discounts、tax_rates、coupons(含 used_by)、orders(含 pricing/paid/refund/events)、next_no，Decimal 用 Decimal(str) 重建，行为一致。

[security][低/硬化建议] shopkit/storage.py:29-31 — save 在 os.replace 前未 os.fsync 临时文件（及目录），掉电可能得到截断/空目标；只影响持久性、不影响对并发读者的原子性。建议：json.dump 后 handle.flush(); os.fsync(handle.fileno()) 再 replace。
[security][低/硬化建议] shopkit/storage.py:41-47、102-104 — load 忽略 'version' 字段；文件存在但 JSON 损坏时抛原生 json.JSONDecodeError（非 ShopError）。非契约要求，可选加固：校验 version 并包错误为 NotFoundError/ValidationError。

整体：无高/中危可利用漏洞（本库无 shell/SQL/web/反序列化攻击面）。以上均为低危合规/健壮性问题。全套验收测试 python -m pytest tests/acceptance -q → 313 passed，我未修改任何文件。
- [note] orders → lead：orders 返工完成（lead 审查两处问题均已修复）：

1) 校验顺序：add_item / remove_item 现在在 _get_order / _require_status 之前先校验 sku 为 str（参数 VE 优先于 StateError）。验证：对 placed 订单 add_item(oid,123,1) / remove_item(oid,123) 均抛 ValidationError。
2) 原子性（clock 抛异常不留部分修改）：create_order 在 _next_no+=1 之前先 now=self._now()；place_order/pay/ship/deliver/cancel 均在首次写操作前先取 now，ship 的所有流水条目与 shipped 事件共用同一个 now。验证：clock 抛 RuntimeError 时 create_order 后 _next_no 不变、_orders 为空。

回归：python -m pytest tests/acceptance/test_orders.py -q → 27 passed；整套 tests/acceptance → 313 passed。
- [note] security → lead：[security] 复检完成：3 项低危修复均有效，未引入新的高/中危问题。全套验收测试 python -m pytest tests/acceptance -q → 313 passed。

复现结果（实测）：
1) money.py：parse_money('1e400') → ValidationError ✓；parse_money('9'*40) → ValidationError ✓（quantize 已包 except ArithmeticError；round_money 同样处理）。
2) orders.py：placed 订单 add_item(oid, 123, 1) → ValidationError ✓；remove_item(oid, 123) → ValidationError ✓（sku 类型校验已提到 _get_order/_require_status 之前）。
3) 先取时间戳再写状态：
   - create_order（clock 抛 RuntimeError）→ 异常后 next_no 仍为 1、orders 仍为 {}，不再消耗订单号 ✓
   - receive（clock 抛异常）→ on_hand 仍 0、log 仍 []，无半更新 ✓
   - adjust（clock 抛异常）→ on_hand 仍 5、log 未新增，无半更新 ✓
   另外确认 place_order / pay / ship / deliver / cancel 也都改成先 `now = self._now()` 再做写操作。

无新增高/中危问题（本库无 shell/SQL/web/反序列化攻击面，无 float 参与金额）。此前报告的第 4 项仅为 storage 硬化建议（os.fsync、校验 version / 包装 JSONDecodeError），非契约要求，不影响结论。我全程只读，未修改任何文件。

agent 自检时写过、最后又用命令删除的临时文件（不包含在 code/ 里）：
- `_check_money.py`
- `_smoke.py`

## agent 的总结

全部完成。`shopkit` 包已按 `docs/SPEC.md` 从零实现，**313 个 pytest 验收测试全部通过**（0.83s），并经过安全复检。

## 交付内容

**源码（`shopkit/`，仅用标准库）**
| 文件 | 职责 |
|---|---|
| `errors.py` | 异常体系：`ShopError` / `ValidationError` / `NotFoundError` / `StockError` / `StateError` / `CouponError` |
| `money.py` | `parse_money` / `round_money` / `format_money`（全程 `Decimal`，禁 float） |
| `catalog.py` | 商品增删改查、上下架、类别规范化、按 sku 排序 |
| `inventory.py` | 入库/盘点/补货线/低库存/流水，`available = on_hand - reserved` |
| `pricing.py` | 阶梯价、类别折扣、税率、`quote`（合并 sku、优惠券分摊最后一行补差、逐行税） |
| `coupons.py` | 优惠券校验/规范化/过期判断/可用性检查/折扣计算（`used_by` 占用与释放） |
| `orders.py` | 订单号 O0001 递增不回收、完整状态机、价格快照、预留/释放/发货扣减、原子性 |
| `reports.py` | `sales_report` / `top_products` / `inventory_value` |
| `storage.py` | `save`（临时文件 + `os.replace` 原子替换）、`Shop.load` 全量恢复 |
| `shop.py` + `__init__.py` | `Shop` 组合入口，异常与金额工具统一导出 |

**测试（`tests/acceptance/`，9 个文件 313 用例）**：按 spec 逐节编写，覆盖异常类型、金额精度、校验顺序、原子性、状态机、报表排序、save/load 往返等。

## 团队协作过程
- 三个 tester 任务编写验收测试 → 8 个实现任务（按依赖分 5 波并行完成）→ security 只读审查。
- 安全审查发现 3 个与 spec 相关的低危问题，均已修复并复检通过：
  1. `parse_money('1e400')` 泄漏 `decimal.InvalidOperation` → 改为 `ValidationError`；
  2. `add_item`/`remove_item` 的 sku 类型校验提到取订单/查状态之前（参数 VE 优先于 StateError）；
  3. 所有改状态的方法先取时间戳再写状态——clock 抛异常时不留部分修改（`create_order` 不再消耗订单号，`receive`/`adjust` 不出现库存与流水不一致）。

最终端到端冒烟验证通过：spec 5.3 示例 `total=26.49`、下单→付款→发货→送达全流程、价格快照不受 `update_price` 影响、取消释放预留与优惠券、报表统计、save/load 后订单号继续递增。

## 运行过的命令

```
python --version && python -m pytest --version
python -c "import sys; print(sys.executable)"
python -c "from shopkit import Shop; from shopkit.money import parse_money, round_money, format_money; from decimal import Decimal; print(parse_money(
cd shopkit && dir && echo ---ORDERS--- && type orders.py && echo ---REPORTS--- && type reports.py && echo ---STORAGE--- && type storage.py
dir /s /b tests 2>nul & echo --- & dir shopkit & echo --- & python --version & python -m pytest --version
cd shopkit && echo ---CATALOG--- && type catalog.py && echo ---INVENTORY--- && type inventory.py && echo ---COUPONS--- && type coupons.py && echo ---P
dir /s /b && echo ---- && type pytest.ini 2>nul & type pyproject.toml 2>nul & type setup.cfg 2>nul & type conftest.py 2>nul
python -m pytest tests/acceptance/test_errors.py tests/acceptance/test_money.py tests/acceptance/test_catalog.py tests/acceptance/test_inventory.py --
python -m pytest tests/acceptance/test_errors.py tests/acceptance/test_money.py -q --tb=short
python -m pytest tests/acceptance/test_errors.py tests/acceptance/test_money.py -q --tb=short & echo === & python -m pytest tests/acceptance/test_erro
python -m pytest --collect-only -q tests/acceptance/test_coupons.py tests/acceptance/test_pricing.py
python -m pytest tests/acceptance/test_orders.py tests/acceptance/test_reports.py tests/acceptance/test_storage.py --collect-only -q
python -c "from decimal import Decimal as D; from shopkit.money import round_money as r, format_money as f; lt=D('30.00'); disc=r(lt*D(10)/D(100)); ne
python -m pytest tests/acceptance/test_coupons.py tests/acceptance/test_pricing.py -q --tb=no -p no:cacheprovider 2>&1 | findstr /R "passed failed err
python -m pytest "tests/acceptance/test_pricing.py::test_quote_basic_lines_and_totals" -q --tb=line -p no:cacheprovider 2>&1 | findstr /R "Error NotIm
python -m pytest tests/acceptance/test_coupons.py -q --tb=short
python -m pytest tests/acceptance/test_catalog.py tests/acceptance/test_money.py tests/acceptance/test_errors.py -q --tb=short
python -c "from shopkit import Shop; s=Shop(); s.add_product('ABC-1','Widget','12','tools'); print(s._stock['ABC-1']); print(s.list_products()); print
python -m pytest tests/acceptance/test_pricing.py tests/acceptance/test_coupons.py -q --tb=short
python -m pytest tests/acceptance/test_inventory.py -q --tb=short
python -m pytest tests/acceptance -q --tb=line 2>&1 | tail -n 15
python -m pytest tests/acceptance/test_catalog.py tests/acceptance/test_inventory.py -q --tb=short
python -m pytest tests/acceptance/test_orders.py -q --tb=short
python -m pytest tests/acceptance -q --tb=short
python -m pytest tests/acceptance/test_reports.py -q --tb=short
python -m pytest tests/acceptance/test_storage.py -q --tb=short
python -m pytest tests/acceptance -q --tb=short
python -m pytest tests/acceptance -q --tb=short
python -m pytest tests/acceptance -q --tb=short 2>&1 | tail -20
python -m pytest tests/acceptance -q --tb=short
python -m pytest tests/acceptance -q --tb=short 2>&1 | tail -n 60
python -m pytest tests/acceptance -q --tb=short -p no:cacheprovider
python -m pytest tests/acceptance/test_coupons.py tests/acceptance/test_pricing.py -q --tb=short -p no:cacheprovider
python -c "import sys; from shopkit import Shop; s=Shop(); s.add_product('A-1','a','10','food'); s.add_coupon('SAVE','fixed','5'); oid=s.create_order(
python -c "import sys; from shopkit import Shop; s=Shop(); sys.excepthook=lambda t,v,tb: print('EXC',t.__name__,'| next_no',s._next_no,'| orders',s._o
python -c "import sys; from shopkit import Shop; s=Shop(); s.add_product('A-1','a','10','food'); oid=s.create_order('c',[{'sku':'A-1','qty':1}]); s.pl
python -c "import sys; from shopkit import Shop; s=Shop(); s.add_product('A-1','a','10','food'); oid=s.create_order('c',[{'sku':'A-1','qty':1}]); sys.
python -c "import os,tempfile,shutil; from shopkit import Shop; s=Shop(); s.add_product('A-1','a','10','food'); s.add_coupon('SAVE','fixed','5'); s.cr
python -c "import sys; from shopkit import Shop; s=Shop(); s.add_product('A-1','a','10','food'); s.receive('A-1',10); oid=s.create_order('c',[{'sku':'
python -c "import sys; from shopkit import Shop; s=Shop(); s.add_product('A-1','a','10','food'); s.receive('A-1',10); oid=s.create_order('c',[{'sku':'
python -c "import sys,os,tempfile,shutil; from shopkit import Shop; d=tempfile.mkdtemp(); p=os.path.join(d,'x.json'); s=Shop(); s.add_product('A-1','a
python -c "import sys; from shopkit.money import parse_money; sys.excepthook=lambda t,v,tb: print('EXC',t.__module__+'.'+t.__name__); print(parse_mone
python -c "import sys; from shopkit.money import parse_money; sys.excepthook=lambda t,v,tb: print('EXC',t.__module__+'.'+t.__name__); print(parse_mone
python -c "import sys; from shopkit import Shop; c=lambda: (_ for _ in ()).throw(RuntimeError('boom')); s=Shop(clock=c); sys.excepthook=lambda t,v,tb:
python -c "import sys; from shopkit import Shop; s=Shop(); s.add_product('A-1','a','10','food'); s._clock=lambda: (_ for _ in ()).throw(RuntimeError('
python -c "from shopkit.money import parse_money; 
python -c "from shopkit.money import parse_money; 
python _check_money.py
python -c "from shopkit import Shop; from shopkit.errors import ValidationError, StateError; s=Shop(); s.add_product('A-1','a','10.00','food'); s.rece
python -m pytest tests/acceptance/test_orders.py -q --tb=short
python _check_orders.py
python -m shopkit.orders
python -m pytest tests/acceptance/test_orders.py -q --tb=short
python -m pytest tests/acceptance -q --tb=short
python -m pytest tests/acceptance/test_inventory.py -q --tb=short
del _check_money.py && python -m pytest tests/acceptance -q
python -c "import sys; from shopkit.money import parse_money, round_money; sys.excepthook=lambda t,v,tb: print('EXC',t.__module__+'.'+t.__name__); pri
python -c "import sys; from shopkit import Shop; s=Shop(); s.add_product('A-1','a','10','food'); s.receive('A-1',10); oid=s.create_order('c',[{'sku':'
python -c "import sys; from shopkit import Shop; c=lambda: (_ for _ in ()).throw(RuntimeError('boom')); s=Shop(clock=c); sys.excepthook=lambda t,v,tb:
python -c "import sys; from shopkit.money import parse_money; sys.excepthook=lambda t,v,tb: print('1e400 ->',t.__name__); parse_money('1e400')" ; pyth
python -c "import sys; from shopkit import Shop; s=Shop(); s.add_product('A-1','a','10','food'); s.receive('A-1',10); oid=s.create_order('c',[{'sku':'
python -c "import sys; from shopkit import Shop; s=Shop(); s.add_product('A-1','a','10','food'); s._clock=lambda: (_ for _ in ()).throw(RuntimeError('
python -c "import sys; from shopkit.money import parse_money; sys.excepthook=lambda t,v,tb: print('9x40 ->',t.__name__); parse_money('9'*40)"
python -c "import sys; from shopkit import Shop; s=Shop(); s.add_product('A-1','a','10','food'); s.receive('A-1',5); s._clock=lambda: (_ for _ in ()).
python -m pytest tests/acceptance -q --tb=short 2>&1 | tail -3
python _smoke.py
python _smoke.py && del _smoke.py
python -m pytest tests/acceptance -q
```

