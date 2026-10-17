# large_spec_shop

由 Coding-agent 在评测中完成（模型 `deepseek-v4-flash`，评测 `20261008-163337-deepseek-v4-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

按照 `docs/SPEC.md` 的需求文档，从零实现 `shopkit` 包：商品、库存、定价、优惠券、订单、报表和持久化。

接口、返回值格式、金额计算和错误类型都要严格符合文档。请为各项功能编写 pytest 测试，并确保全部通过。

## 结果

- 隐藏测试复验：**通过**（98 passed in 0.30s）
- 调用模型 33 次，工具调用 42 次（其中出错 0 次），运行命令 8 条，耗时 312 秒
- token：输入 1,223,273（命中缓存 1,210,240），输出 48,291

## agent 新建或修改的文件

- `_smoke.py`（新建）
- `conftest.py`（新建）
- `shopkit/__init__.py`（新建）
- `shopkit/_util.py`（新建）
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
- `tests/conftest.py`（新建）
- `tests/test_catalog.py`（新建）
- `tests/test_coupons.py`（新建）
- `tests/test_inventory.py`（新建）
- `tests/test_money.py`（新建）
- `tests/test_orders.py`（新建）
- `tests/test_pricing.py`（新建）
- `tests/test_reports.py`（新建）
- `tests/test_storage.py`（新建）

## agent 的总结

已按照 `docs/SPEC.md` 从零实现了 `shopkit` 包，并编写了 pytest 测试，全部 149 个测试通过。

## 实现内容

**包结构（`shopkit/`，仅用标准库）**
- `errors.py`：`ShopError` 及 `ValidationError` / `NotFoundError` / `StockError` / `StateError` / `CouponError` 异常体系。
- `money.py`：`parse_money`（拒绝 bool/float、非有限数、负数、超两位小数，返回两位小数 `Decimal`）、`round_money`（`ROUND_HALF_UP`）、`format_money`。
- `catalog.py`：商品增改查、上下架、列表（sku 排序/类别/仅上架）。
- `inventory.py`：`receive` / `adjust` / `stock` / `set_reorder_level` / `low_stock` / `stock_log`，含流水记录。
- `pricing.py`：阶梯价、类别折扣、税率、报价计算（单价→行金额→折扣→净额→小计→优惠券分摊→税→总额）。
- `coupons.py`：固定/百分比券、最低消费、过期判断（到期当天可用）、占用状态。
- `orders.py`：草稿→下单→付款→发货→送达及取消流程，状态机、事件、价格快照、库存预留与释放、优惠券占用与释放、退款。
- `reports.py`：`sales_report`、`top_products`、`inventory_value`。
- `storage.py`：`save`（先写同目录临时文件再 `os.replace`）、`Shop.load` 全量恢复。
- `shop.py` / `__init__.py`：`Shop` 组合各模块并导出。

**关键约定**
- 内部一律 `Decimal`，对外金额为两位小数字符串。
- 所有"当前时间/今天"都走 `clock()`，事件时间用 `isoformat(timespec="seconds")`。
- 严格检查顺序：参数 → 查找对象 → 业务条件；失败时先校验再修改，保证原子性。

**测试（`tests/`）**：覆盖 money、catalog、inventory、pricing、coupons、orders、reports、storage，共 149 个用例，包含规范里的报价示例（`26.49`）、原子性（库存不足下单不改变状态）、价格快照、优惠券一次性使用与释放、存档往返一致性等。

另外根目录加了 `conftest.py`，确保 `pytest` 与 `python -m pytest` 都能正确导入包。

```
149 passed
```

## 运行过的命令

```
python --version && python -c "import pytest; print(pytest.__version__)"
python -c "
python _smoke.py
python -m pytest -q 2>&1
python -m pytest -q 2>&1
del _smoke.py && pytest -q 2>&1
pytest -q 2>&1
python -m compileall -q shopkit && pytest -q 2>&1
```

