def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    """合并所有重叠的区间（端点相接也算重叠），返回按起点升序排序的结果。

    输入不一定有序，且不会修改传入的列表。
    """
    if not intervals:
        return []

    # 复制一份并排序，避免修改传入的列表。
    ordered = sorted(intervals, key=lambda item: item[0])

    merged: list[list[int]] = [list(ordered[0])]
    for start, end in ordered[1:]:
        last = merged[-1]
        if start <= last[1]:
            # 重叠（含端点相接），扩展当前区间的右边界。
            if end > last[1]:
                last[1] = end
        else:
            merged.append([start, end])
    return merged
