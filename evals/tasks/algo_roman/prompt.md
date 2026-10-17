在 roman.py 中实现两个函数：

- `to_roman(n: int) -> str`：把 1 到 3999 的整数转成罗马数字（例如 1994 → "MCMXCIV"）
- `from_roman(s: str) -> int`：把罗马数字转回整数

超出范围的数字、不规范或不合法的罗马数字（例如 "IIII"、"VX"、"IC"、空字符串、小写字母）都要抛出 ValueError。
