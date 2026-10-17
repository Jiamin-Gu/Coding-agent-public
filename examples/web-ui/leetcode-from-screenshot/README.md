# 从截图解 LeetCode 题（图片输入）

用 Coding-agent 的网页界面完成（v0.2.2，模型 `deepseek-flash`），测试图片输入功能。

## 过程

1. 在页面里粘贴一张题目截图："无重复字符的最长子串"，包含题目描述、3 个示例和代码模板 `class Solution: def lengthOfLongestSubstring(self, s: str) -> int`
2. 点空状态页的示例"粘贴 LeetCode 题目截图，写出解法并用示例测试"，发送
3. agent 从截图里读出函数签名和 3 个示例，写出滑动窗口解法；除了截图里的 3 个示例，还自己补充了 4 个边界用例（空字符串、单个空格、`"dvdf"`、`"abba"`），7 个用例全部通过
4. 最后给出可以直接提交的代码，并指出关键点：`last_seen[ch] >= left` 这个条件不能省略，否则 `"abba"` 这类用例会让左边界往回退

用时 7 秒，约 9k token。

## 运行

```bash
python solution.py
```
