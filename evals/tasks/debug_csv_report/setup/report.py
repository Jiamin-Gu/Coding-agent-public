import sys
from collections import defaultdict


def summarize(path):
    """读取销售 CSV（列：date,region,amount,notes），按"月份 + 地区"汇总金额。

    返回按月份、再按地区排序的行，格式为 "YYYY-MM 地区 金额"，金额保留两位小数。
    CSV 格式：
    - 文件可能以 UTF-8 BOM 开头
    - 字段可能用双引号包裹，引号内可以包含逗号、换行，以及用两个双引号 "" 表示的引号
    - 金额可能带千位分隔符（例如 "1,250.00"），可能为负数（退款）
    - 空行忽略
    """
    totals = defaultdict(float)
    with open(path, encoding="utf-8") as f:
        f.readline()  # 跳过表头
        for line in f:
            date, region, amount, notes = line.strip().split(",")
            totals[(date[:7], region)] += float(amount)
    return [f"{m} {r} {v:.2f}" for (m, r), v in sorted(totals.items())]


if __name__ == "__main__":
    print("\n".join(summarize(sys.argv[1])))
