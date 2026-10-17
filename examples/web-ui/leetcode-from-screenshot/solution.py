class Solution:
    def lengthOfLongestSubstring(self, s: str) -> int:
        # 滑动窗口：窗口 [left, right] 内始终无重复字符
        last_seen = {}  # 字符 -> 最近一次出现的下标
        left = 0
        best = 0
        for right, ch in enumerate(s):
            # 若该字符在窗口内出现过，收缩左边界到上次出现的后一位
            if ch in last_seen and last_seen[ch] >= left:
                left = last_seen[ch] + 1
            last_seen[ch] = right
            best = max(best, right - left + 1)
        return best


if __name__ == "__main__":
    sol = Solution()
    tests = [
        ("abcabcbb", 3),
        ("bbbbb", 1),
        ("pwwkew", 3),
        ("", 0),          # 边界：空串
        (" ", 1),         # 边界：单个空格
        ("dvdf", 3),      # 经典易错用例
        ("abba", 2),      # 左边界不能被回退
    ]
    for s, expected in tests:
        got = sol.lengthOfLongestSubstring(s)
        status = "PASS" if got == expected else "FAIL"
        print(f"[{status}] s={s!r} -> {got} (expected {expected})")
        assert got == expected, f"s={s!r}: got {got}, expected {expected}"
    print("All tests passed.")
