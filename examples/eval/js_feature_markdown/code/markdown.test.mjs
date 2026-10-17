import test from "node:test";
import assert from "node:assert/strict";
import { render } from "./markdown.mjs";

test("空输入或只有空白返回空字符串", () => {
  assert.equal(render(""), "");
  assert.equal(render("   "), "");
  assert.equal(render("\n \t\n\r\n  "), "");
});

test("SPEC 里的完整示例", () => {
  const source = [
    "# 标题",
    "",
    "第一行",
    "第二行 **加粗** 和 `a<b`",
    "",
    "- 一项 [官网](https://example.com)",
    "- 二项 [点我](javascript:alert)",
  ].join("\n");

  const expected = [
    "<h1>标题</h1>",
    "<p>第一行 第二行 <strong>加粗</strong> 和 <code>a&lt;b</code></p>",
    '<ul><li>一项 <a href="https://example.com">官网</a></li><li>二项 点我</li></ul>',
  ].join("\n");

  assert.equal(render(source), expected);
});

test("把所有特殊字符转义", () => {
  assert.equal(render("<&>\"'"), "<p>&lt;&amp;&gt;&quot;&#39;</p>");
  assert.equal(
    render("<script>alert('x')</script>"),
    "<p>&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;</p>"
  );
});

test("段落：各行去首尾空白后用单个空格连接", () => {
  assert.equal(render("  a  \n  b  "), "<p>a b</p>");
  assert.equal(render("a\nb\nc"), "<p>a b c</p>");
});

test("空行分隔段落，多个空行也只分隔一次", () => {
  assert.equal(render("a\n\n\n\nb"), "<p>a</p>\n<p>b</p>");
  assert.equal(render("\n\na\n\n"), "<p>a</p>");
});

test("\\r\\n 统一成 \\n", () => {
  assert.equal(render("# a\r\n\r\nb"), "<h1>a</h1>\n<p>b</p>");
});

test("标题：1~3 个 # 加一个空格", () => {
  assert.equal(render("# a"), "<h1>a</h1>");
  assert.equal(render("## b"), "<h2>b</h2>");
  assert.equal(render("### c"), "<h3>c</h3>");
  assert.equal(render("# a\n## b\n### c"), "<h1>a</h1>\n<h2>b</h2>\n<h3>c</h3>");
});

test("标题内容去首尾空白并做行内格式", () => {
  assert.equal(render("#   spaced  "), "<h1>spaced</h1>");
  assert.equal(render("# **粗**"), "<h1><strong>粗</strong></h1>");
});

test("四个及以上 # 或 # 后无空格按段落处理", () => {
  assert.equal(render("#### d"), "<p>#### d</p>");
  assert.equal(render("#d"), "<p>#d</p>");
  assert.equal(render("##x"), "<p>##x</p>");
});

test("列表：连续的 - 行组成一个列表", () => {
  assert.equal(render("- a\n- b"), "<ul><li>a</li><li>b</li></ul>");
  assert.equal(
    render("- 一项 **粗**"),
    "<ul><li>一项 <strong>粗</strong></li></ul>"
  );
});

test("列表遇到非列表行即结束", () => {
  assert.equal(render("- a\ntext"), "<ul><li>a</li></ul>\n<p>text</p>");
  assert.equal(render("- a\n# t"), "<ul><li>a</li></ul>\n<h1>t</h1>");
  assert.equal(
    render("- a\n- b\n\n- c"),
    "<ul><li>a</li><li>b</li></ul>\n<ul><li>c</li></ul>"
  );
});

test("段落遇到标题或列表开始行即结束", () => {
  assert.equal(render("text\n# h"), "<p>text</p>\n<h1>h</h1>");
  assert.equal(render("text\n- item"), "<p>text</p>\n<ul><li>item</li></ul>");
});

test("代码块：基本与转义", () => {
  assert.equal(render("```\nfoo\n```"), "<pre><code>foo</code></pre>");
  assert.equal(
    render("```\n<b>&\n```"),
    "<pre><code>&lt;b&gt;&amp;</code></pre>"
  );
});

test("代码块：块内不做行内格式", () => {
  assert.equal(
    render("```\n**a** [x](https://e.com)\n```"),
    "<pre><code>**a** [x](https://e.com)</code></pre>"
  );
});

test("代码块：合法语言名输出 class", () => {
  assert.equal(
    render("```js\nconst x = 1 < 2;\n```"),
    '<pre><code class="language-js">const x = 1 &lt; 2;</code></pre>'
  );
  assert.equal(
    render("```c++_1-2\nx\n```"),
    '<pre><code class="language-c++_1-2">x</code></pre>'
  );
});

test("代码块：非法语言名忽略", () => {
  assert.equal(
    render("```js bad\nx\n```"),
    "<pre><code>x</code></pre>"
  );
  assert.equal(render("```j$s\nx\n```"), "<pre><code>x</code></pre>");
});

test("代码块：没有结束行时延续到文本末尾", () => {
  assert.equal(render("```\nfoo\nbar"), "<pre><code>foo\nbar</code></pre>");
});

test("代码块：结束行允许首尾空白", () => {
  assert.equal(render("```\nfoo\n  ```  "), "<pre><code>foo</code></pre>");
});

test("行内代码：内容只转义，不再解析其他格式", () => {
  assert.equal(render("`a<b&c`"), "<p><code>a&lt;b&amp;c</code></p>");
  assert.equal(render("`**a**`"), "<p><code>**a**</code></p>");
  assert.equal(
    render("`[x](https://e.com)`"),
    "<p><code>[x](https://e.com)</code></p>"
  );
});

test("行内代码：没有配对的反引号按普通字符", () => {
  assert.equal(render("a ` b"), "<p>a ` b</p>");
});

test("链接：允许的协议", () => {
  assert.equal(
    render("[官网](https://example.com)"),
    '<p><a href="https://example.com">官网</a></p>'
  );
  assert.equal(render("[x](http://a.com)"), '<p><a href="http://a.com">x</a></p>');
  assert.equal(
    render("[mail](mailto:a@b.com)"),
    '<p><a href="mailto:a@b.com">mail</a></p>'
  );
});

test("链接：协议不区分大小写", () => {
  assert.equal(
    render("[x](HTTP://A.com)"),
    '<p><a href="HTTP://A.com">x</a></p>'
  );
  assert.equal(
    render("[x](MailTo:a@b.com)"),
    '<p><a href="MailTo:a@b.com">x</a></p>'
  );
});

test("链接：危险或相对地址只输出文字", () => {
  assert.equal(render("[点我](javascript:alert)"), "<p>点我</p>");
  assert.equal(render("[x](data:text/html,<h1>)"), "<p>x</p>");
  assert.equal(render("[x](/relative/path)"), "<p>x</p>");
  assert.equal(render("[x](ftp://a.com)"), "<p>x</p>");
});

test("链接：文字部分可以做加粗斜体，文字也转义", () => {
  assert.equal(
    render("[**粗**](https://e.com)"),
    '<p><a href="https://e.com"><strong>粗</strong></a></p>'
  );
  assert.equal(
    render("[<b>](https://e.com)"),
    '<p><a href="https://e.com">&lt;b&gt;</a></p>'
  );
});

test("链接：地址里的引号等会被转义，无法注入属性", () => {
  assert.equal(
    render('[x](https://e.com/?a="b)'),
    '<p><a href="https://e.com/?a=&quot;b">x</a></p>'
  );
});

test("加粗与斜体", () => {
  assert.equal(render("**加粗**"), "<p><strong>加粗</strong></p>");
  assert.equal(render("*斜体*"), "<p><em>斜体</em></p>");
  assert.equal(
    render("**a** *b*"),
    "<p><strong>a</strong> <em>b</em></p>"
  );
});

test("加粗、斜体非贪婪且至少一个字符", () => {
  assert.equal(
    render("**a**b**c**"),
    "<p><strong>a</strong>b<strong>c</strong></p>"
  );
  assert.equal(render("**"), "<p>**</p>");
  assert.equal(render("*"), "<p>*</p>");
  assert.equal(render("a * b"), "<p>a * b</p>");
});

test("用户无法注入 HTML 或可执行链接", () => {
  const out = render('<img src=x onerror="alert(1)">');
  assert.equal(out, "<p>&lt;img src=x onerror=&quot;alert(1)&quot;&gt;</p>");
  assert.ok(!out.includes("<img"));
  assert.ok(!render("[x](javascript:alert(1))").includes("<a "));
});
