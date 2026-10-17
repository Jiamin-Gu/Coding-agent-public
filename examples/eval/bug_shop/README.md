# bug_shop

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

用户反馈购物车的金额算错了：

- 买了 3 件单价 30 元的商品，小计却显示 30 元
- 使用优惠码 SAVE10（应该打九折）后，金额变成了负数
- 订单刚好 100 元时，满 100 减 20 的优惠码 FULL100 没有生效
- 输入不存在的优惠码时程序直接崩溃，应该抛出 ValueError

请找到并修复 shop 包里的问题。

## 结果

- 隐藏测试复验：**通过**（5 passed in 0.02s）
- 调用模型 9 次，工具调用 12 次（其中出错 0 次），运行命令 3 条，耗时 9 秒
- token：输入 23,009（命中缓存 19,712），输出 1,568

## agent 新建或修改的文件

- `shop/cart.py`（修改）
- `shop/discount.py`（修改）

agent 自检时写过、最后又用命令删除的临时文件（不包含在 code/ 里）：
- `_check.py`

## agent 的总结

已修复 `shop` 包中的 4 个问题，并验证通过：

**1. 小计未乘数量** — `shop/cart.py`
```python
# 原：sum(price for name, price, qty in self.items)
sum(price * qty for name, price, qty in self.items)
```
3 件 × 30 元 = 90 元。

**2. 打九折变成负数** — `shop/discount.py`
百分比优惠码的 `value=10` 表示 10%，原来写成 `amount * (1 - value)`（即 ×(-9)）。改为 `amount * (1 - value / 100)`，90 元打九折 = 81 元。

**3. 满 100 减 20 在刚好 100 元时不生效** — `shop/discount.py`
`if amount > threshold` 改为 `if amount >= threshold`（"满 100" 包含 100）。

**4. 未知优惠码崩溃** — `shop/discount.py`
原来用 `COUPONS[code]` 直接取，会抛 `KeyError`。现在先校验，不存在时抛出 `ValueError`。

验证结果：小计 90、SAVE10 → 81.0、满 100 → 80.0、未知码抛 `ValueError`，全部符合预期。

## 运行过的命令

```
python -c "from shop.cart import Cart; c=Cart(); c.add('a',30,3); print('subtotal', c.subtotal()); print('SAVE10', c.total('SAVE10')); c2=Cart(); c2.a
python _check.py
del _check.py
```

