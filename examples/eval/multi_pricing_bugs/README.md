# multi_pricing_bugs

由 Coding-agent 在评测中完成（模型 `deepseek-flash`，评测 `20261002-024621-deepseek-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

用户投诉结算金额不对：

- 买 3 根香蕉（买一送一活动），结果只收了 1 根的钱
- 有用户说税额差了一分钱
- 我们规定按打折后的商品金额计税，"满 99 免运费"也按打折后的金额判断，但现在好像不是这样

请排查 pricing 包，修复所有计算问题：以各个函数文档字符串里写的规则为准（包括 checkout 里写明的舍入规则）。`checkout` 的返回格式不要变，`tests/` 里的现有测试要继续通过。

## 结果

- 隐藏测试复验：**通过**（8 passed in 0.04s）
- 调用模型 10 次，工具调用 18 次（其中出错 0 次），运行命令 5 条，耗时 32 秒
- token：输入 65,974（命中缓存 60,928），输出 6,728

## agent 新建或修改的文件

- `pricing/checkout.py`（修改）
- `pricing/promotions.py`（修改）
- `pricing/shipping.py`（修改）
- `pricing/tax.py`（修改）

agent 自检时写过、最后又用命令删除的临时文件（不包含在 code/ 里）：
- `_sanity.py`

## agent 的总结

已排查并修复 `pricing` 包中所有计算问题，现有测试全部通过。

## 修复内容

**1. 买一送一多送了一件（`pricing/promotions.py`）**
- 原代码 `qty // 2 + qty % 2` 把不足两件的部分也算成免费，导致买 3 件免 2 件。
- 改为 `qty // 2`，即每满两件免一件；买 3 件付 2 件的钱。✅

**2. 税额差一分（`pricing/tax.py`）**
- 原代码 `round(float(amount * rate), 2)` 走的是浮点数 + 银行家舍入，与文档要求的"四舍五入到分"不符。
- 改为 Decimal 的 `quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`。✅

**3. 运费计算两处问题（`pricing/shipping.py`、`pricing/checkout.py`）**
- 免运费门槛用错金额：`checkout` 原来把原价小计 `sub` 传给 `shipping_fee`，现改为传打折后金额 `merch`（符合"满 99 免运费按打折后金额判断"）。
- 超重部分舍入错误："不足 1kg 按 1kg 计算"应为向上取整，原代码用 `int(extra)` 是截断。现用 `ROUND_CEILING`，并把重量改用 Decimal 避免浮点误差。✅

**4. 计税基数（`pricing/checkout.py`）**
- 原代码 `tax_for(sub, region)` 按原价计税，改为按打折后金额 `merch` 计税（符合"按打折后的商品金额计税"）。

## 保持不变
- `checkout` 的返回字典结构与键名未变。
- 舍入规则严格遵守文档：`total = merch(完整精度) + tax(单独四舍五入) + shipping`，最后统一 `_cents` 到分。
- `tests/test_existing.py` 两个测试均通过。

验证示例：买 3 根香蕉 => 优惠 1.25、实付 2 根钱；折扣后金额从 101.97 降到 92.97 时恢复收 8 元运费；3.2kg 按 4kg 计收超重费；税额 0.015 按四舍五入进为 0.02。

## 运行过的命令

```
python -m pytest tests/ -v
python -c "from decimal import Decimal; from pricing.checkout import checkout; from pricing.promotions import buy_one_get_one; from pricing.tax import
python -c "
python _sanity.py
del _sanity.py && python -m pytest tests/ -q
```

