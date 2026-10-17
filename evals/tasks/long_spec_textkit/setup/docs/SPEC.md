# textkit 规格说明

在 `textkit.py` 中实现下面 12 个函数。每条规则都要满足，示例必须完全一致。

## 1. slugify(text) -> str

- 转为小写
- 只保留 ASCII 字母和数字；其他所有字符（空格、标点、非 ASCII 字符等）都视为分隔符
- 连续的分隔符合并成一个 `-`，并去掉首尾的 `-`

示例：`slugify("Hello, World!") == "hello-world"`、`slugify("  A--B  ") == "a-b"`、`slugify("C++ & Python 3") == "c-python-3"`、`slugify("你好 world") == "world"`、`slugify("!!!") == ""`

## 2. camel_to_snake(name) -> str

- 驼峰命名转下划线命名，结果全小写
- 大写字母开始一个新单词；连续的大写字母视为一个缩写词，但如果缩写词的最后一个大写字母后面跟着小写字母，这个大写字母属于下一个单词
- 数字跟在它前面的字母后面，不单独拆开

示例：`"parseHTTPResponse"` → `"parse_http_response"`、`"userID"` → `"user_id"`、`"HTMLParser"` → `"html_parser"`、`"getV2Data"` → `"get_v2_data"`、`"simple"` → `"simple"`

## 3. snake_to_camel(name) -> str

- 下划线命名转小驼峰：第一个单词全小写，之后每个单词首字母大写、其余小写
- 开头的下划线原样保留；中间连续的多个下划线视为一个分隔

示例：`"parse_http_response"` → `"parseHttpResponse"`、`"_private_var"` → `"_privateVar"`、`"a__b"` → `"aB"`、`"HELLO_WORLD"` → `"helloWorld"`、`"simple"` → `"simple"`

## 4. truncate_middle(text, max_len) -> str

- 长度不超过 max_len 时原样返回
- 否则保留开头和结尾，中间用一个 `…`（单个字符）连接，结果长度正好等于 max_len
- 开头保留的字符数 = (max_len - 1) 除以 2 向上取整，结尾保留剩下的
- max_len 小于 1 时抛出 ValueError

示例：`truncate_middle("abcdefghij", 5) == "ab…ij"`、`truncate_middle("abcdefghij", 4) == "ab…j"`、`truncate_middle("abc", 3) == "abc"`、`truncate_middle("abcdef", 1) == "…"`

## 5. normalize_whitespace(text) -> str

- 把所有空白字符（空格、制表符、换行、全角空格 `\u3000` 等）组成的连续序列替换成一个空格，并去掉首尾空白

示例：`normalize_whitespace("  a\t\tb\n\nc  ") == "a b c"`、`normalize_whitespace("中文\u3000\u3000空格") == "中文 空格"`

## 6. extract_emails(text) -> list[str]

- 邮箱的本地部分由字母、数字和 `. _ % + -` 组成；`@` 后面是域名：由字母、数字、`-` 组成的若干段，用 `.` 连接，最后一段（顶级域名）至少 2 个字母
- 返回按首次出现顺序排列、去重后的列表，全部转为小写
- 句子末尾的点不属于邮箱

示例：`extract_emails("联系 Bob@Example.com 或 alice.w+tag@mail.co.uk，抄送 bob@example.com。") == ["bob@example.com", "alice.w+tag@mail.co.uk"]`、`extract_emails("写信到 a@b.cn.") == ["a@b.cn"]`、`extract_emails("x@y.c") == []`

## 7. word_count(text) -> int

- 英文单词：由 ASCII 字母、数字和撇号 `'` 组成的连续序列，每个计 1
- 每个中文字符（Unicode 范围 `\u4e00`–`\u9fff`）计 1
- 其他字符不计

示例：`word_count("Hello, 世界! it's 2026") == 5`、`word_count("") == 0`

## 8. levenshtein(a, b) -> int

两个字符串的编辑距离（插入、删除、替换各算 1 次操作）。

示例：`levenshtein("kitten", "sitting") == 3`、`levenshtein("", "abc") == 3`、`levenshtein("flaw", "lawn") == 2`、`levenshtein("same", "same") == 0`

## 9. is_palindrome(text) -> bool

- 忽略大小写，只考虑 ASCII 字母和数字，其他字符全部忽略
- 空字符串（或忽略后为空）返回 True

示例：`is_palindrome("A man, a plan, a canal: Panama") is True`、`is_palindrome("race a car") is False`、`is_palindrome("") is True`

## 10. title_case(text) -> str

先按空白分词（单词之间用单个空格连接，首尾空白去掉），然后对每个单词按以下顺序决定：

1. 原本全大写且长度至少为 2 的单词（如 `NASA`）保持不变
2. 小词 `a an the and but or for nor on at to of in by` 全部小写，但如果它是第一个或最后一个单词，则按第 3 条处理
3. 其他单词首字母大写，其余字母小写

示例：`title_case("the lord of the rings") == "The Lord of the Rings"`、`title_case("NASA and the moon") == "NASA and the Moon"`、`title_case("what is it for") == "What Is It For"`、`title_case("the CEO of IBM") == "The CEO of IBM"`、`title_case("  hello   world ") == "Hello World"`

## 11. wrap(text, width) -> list[str]

- 先按 normalize_whitespace 的规则规范空白，然后贪心换行：每一行尽量放更多单词，单词之间一个空格，每行长度不超过 width
- 长度超过 width 的单词先切成若干段长度为 width 的片段（最后一段可以更短），这些片段当作独立的单词参与换行
- 空字符串（或规范化后为空）返回 `[]`；width 小于 1 时抛出 ValueError

示例：`wrap("the quick brown fox", 10) == ["the quick", "brown fox"]`、`wrap("abcdefghij xy", 4) == ["abcd", "efgh", "ij", "xy"]`、`wrap("a bb ccc", 4) == ["a bb", "ccc"]`

## 12. parse_kv(text) -> dict[str, str]

- 由若干 `key=value` 组成，用分号 `;` 分隔；键和值两端的空白去掉
- 如果值（去掉两端空白后）以双引号开头，则它是带引号的值：一直到配对的下一个双引号为止，引号内可以包含分号和等号，结果去掉外层引号，引号内的空白保留；引号没有闭合时抛出 ValueError
- 空的部分（例如结尾多一个分号、连续的分号）忽略
- 值可以为空：`c=` 得到 `"c": ""`
- 某一部分没有 `=`，或者键为空，抛出 ValueError
- 键重复时，后出现的覆盖前面的

示例：`parse_kv('a=1; b = two ;c=') == {"a": "1", "b": "two", "c": ""}`、`parse_kv('x="a;b=c" ; y=2;') == {"x": "a;b=c", "y": "2"}`、`parse_kv('k=1;k=2') == {"k": "2"}`、`parse_kv('q=" padded "') == {"q": " padded "}`
