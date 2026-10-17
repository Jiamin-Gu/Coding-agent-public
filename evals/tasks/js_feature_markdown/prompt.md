按照 `docs/SPEC.md` 实现 `markdown.mjs` 里的 `render`（评论区用的 Markdown 子集渲染器，Node.js ES 模块）。

用户输入不可信，要特别注意转义和链接地址的检查。输出格式要严格符合文档。请用 Node 自带的 `node:test` 写测试并确保通过。
