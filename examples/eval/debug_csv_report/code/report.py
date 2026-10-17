import csv
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
    # utf-8-sig 会在读取时自动去掉可能存在的 UTF-8 BOM
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # 跳过表头
        for row in reader:
            if not row:  # 空行（csv.reader 对空行返回空列表）
                continue
            date, region, amount, notes = row
            # 去掉金额中的千位分隔符后再转换为数值
            totals[(date[:7], region)] += float(amount.replace(",", ""))
    return [f"{m} {r} {v:.2f}" for (m, r), v in sorted(totals.items())]


if __name__ == "__main__":
    print("\n".join(summarize(sys.argv[1])))
