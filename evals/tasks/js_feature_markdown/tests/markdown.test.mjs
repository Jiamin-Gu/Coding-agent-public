import assert from "node:assert/strict";
import { test } from "node:test";
import { render } from "../markdown.mjs";

test("规格里的示例", () => {
  const src = "# 标题\n\n第一行\n第二行 **加粗** 和 `a<b`\n\n- 一项 [官网](https://example.com)\n- 二项 [点我](javascript:alert)\n";
  assert.equal(render(src), [
    "<h1>标题</h1>",
    "<p>第一行 第二行 <strong>加粗</strong> 和 <code>a&lt;b</code></p>",
    '<ul><li>一项 <a href="https://example.com">官网</a></li><li>二项 点我</li></ul>',
  ].join("\n"));
});

test("空输入", () => {
  assert.equal(render(""), "");
  assert.equal(render("  \n\n \r\n"), "");
});

test("标题级别和不算标题的情况", () => {
  assert.equal(render("## 二级  "), "<h2>二级</h2>");
  assert.equal(render("### 三级"), "<h3>三级</h3>");
  assert.equal(render("#### 四级"), "<p>#### 四级</p>");
  assert.equal(render("#没有空格"), "<p>#没有空格</p>");
});

test("段落：多行用空格连接，空行分隔，CRLF 也可以", () => {
  assert.equal(render("  a  \nb\r\n\r\nc"), "<p>a b</p>\n<p>c</p>");
});

test("标题和列表会结束当前段落", () => {
  assert.equal(render("段落\n# 标题\n- 项\n接着"), "<p>段落</p>\n<h1>标题</h1>\n<ul><li>项</li></ul>\n<p>接着</p>");
});

test("所有用户文字都转义", () => {
  assert.equal(render(`<script>alert("x")</script> & 'q'`),
    "<p>&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#39;q&#39;</p>");
  assert.equal(render("# <img src=x onerror=alert(1)>"), "<h1>&lt;img src=x onerror=alert(1)&gt;</h1>");
  assert.equal(render("- <b>粗</b>"), "<ul><li>&lt;b&gt;粗&lt;/b&gt;</li></ul>");
});

test("代码块：转义、保留原样、语言名", () => {
  assert.equal(render("```js\nif (a < b && c) {\n  **不加粗**\n}\n```"),
    '<pre><code class="language-js">if (a &lt; b &amp;&amp; c) {\n  **不加粗**\n}</code></pre>');
  assert.equal(render("```\nx\n```"), "<pre><code>x</code></pre>");
});

test("代码块的语言名不能注入属性", () => {
  assert.equal(render('```js" onclick="alert(1)\nx\n```'), "<pre><code>x</code></pre>");
});

test("没有结束行的代码块延续到末尾，前面的段落先结束", () => {
  assert.equal(render("说明\n```\na\n\nb"), "<p>说明</p>\n<pre><code>a\n\nb</code></pre>");
});

test("代码块后面的内容照常处理", () => {
  assert.equal(render("```\n# 不是标题\n```\n# 标题"), "<pre><code># 不是标题</code></pre>\n<h1>标题</h1>");
});

test("行内代码里不做格式，只转义", () => {
  assert.equal(render("用 `**a** <i>` 表示"), "<p>用 <code>**a** &lt;i&gt;</code> 表示</p>");
  assert.equal(render("只有一个 ` 反引号"), "<p>只有一个 ` 反引号</p>");
});

test("加粗和斜体", () => {
  assert.equal(render("**粗** *斜* 单个 * 星号"), "<p><strong>粗</strong> <em>斜</em> 单个 * 星号</p>");
  assert.equal(render("a*b"), "<p>a*b</p>");
  assert.equal(render("**a** 和 **b**"), "<p><strong>a</strong> 和 <strong>b</strong></p>");
});

test("链接：只允许 http、https、mailto", () => {
  assert.equal(render("[a](http://x.com/p?q=1)"), '<p><a href="http://x.com/p?q=1">a</a></p>');
  assert.equal(render("[信](MAILTO:me@x.com)"), '<p><a href="MAILTO:me@x.com">信</a></p>');
  assert.equal(render("[x](javascript:alert)"), "<p>x</p>");
  assert.equal(render("[x](JavaScript:alert)"), "<p>x</p>");
  assert.equal(render("[x](data:text/html;base64,PHNjcmlwdD4=)"), "<p>x</p>");
  assert.equal(render("[x](/relative)"), "<p>x</p>");
});

test("链接地址里的引号被转义，不能跳出 href", () => {
  assert.equal(render('[x](https://a.com/"onmouseover="alert)'),
    '<p><a href="https://a.com/&quot;onmouseover=&quot;alert">x</a></p>');
});

test("链接文字可以加粗，链接文字里的 HTML 被转义", () => {
  assert.equal(render("[**重要** <b>](https://x.com)"), '<p><a href="https://x.com"><strong>重要</strong> &lt;b&gt;</a></p>');
});

test("列表项去掉首尾空白，多个列表被段落隔开", () => {
  assert.equal(render("-   a  \n- b\n\n中间\n- c"), "<ul><li>a</li><li>b</li></ul>\n<p>中间</p>\n<ul><li>c</li></ul>");
});
