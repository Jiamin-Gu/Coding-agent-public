# js_bug_task_queue

由 Coding-agent 在评测中完成（模型 `deepseek-v4-flash`，评测 `20261011-211649-deepseek-v4-flash`）。代码从评测轨迹重放得到，并用隐藏测试复验。

## 任务

taskQueue.mjs 里的 `TaskQueue`（并发受限的异步任务队列）在生产环境里出了几个问题，用户反馈：

- 设置了并发数 2，实际同时跑了 3 个任务
- 任务没有按加入的顺序开始执行
- 有时 `await queue.onIdle()` 永远不返回
- 某个任务同步抛出异常后，整个队列卡住，后面的任务再也不执行

请按文件开头文档注释里的规则修复，对外接口不要变。这是 ES 模块（Node.js），可以用 Node 自带的 `node:test` 写测试验证。

## 结果

- 隐藏测试复验：**通过**（ℹ duration_ms 2341.4151）
- 调用模型 7 次，工具调用 6 次（其中出错 0 次），运行命令 1 条，耗时 27 秒
- token：输入 28,326（命中缓存 24,064），输出 3,416

## agent 新建或修改的文件

- `taskQueue.mjs`（修改）
- `taskQueue.test.mjs`（新建）

## agent 的总结

所有 9 个测试通过。修复完成。

## 改动说明（`taskQueue.mjs`）

问题都出在 `_next()` 和 `onIdle()` 上，按文件开头文档注释的规则逐条修复：

1. **并发超限（并发 2 跑了 3 个）**
   原判断 `if (this.running > this.concurrency)` 允许在 `running == concurrency` 时再启动一个。改为 `while (this.running < this.concurrency && ...)`，用循环把待运行槽位一次填满，既不会超限，也能在任务完成后补位。

2. **顺序错乱**
   `this.queue.pop()` 是 LIFO（后进先出）。改为 `this.queue.shift()`，严格 FIFO。

3. **`onIdle()` 永不返回**
   原来只 push 到 `idleWaiters` 却从不调用。新增 `_checkIdle()`：当 `running === 0 && queue.length === 0` 时 resolve 并清空所有等待者；`onIdle()` 在调用时已空闲则直接返回 `Promise.resolve()`。

4. **同步抛异常导致队列卡死**
   原来直接 `item.fn().then(...)`，`fn()` 同步抛出会跳过 `.finally`，`running` 永不递减。改为 `Promise.resolve().then(() => item.fn())`，把同步异常转成 reject，`.finally` 一定会执行并继续调度。顺带也正确处理了 `fn` 返回**普通值**（非 Promise）的情况（文档要求支持）。

对外接口（`add` / `onIdle` / `size` / `pending` / 构造函数签名）保持不变。

## 新增测试
`taskQueue.test.mjs`（Node 自带 `node:test`），覆盖：并发上限、执行顺序、`onIdle` 两类场景、同步抛异常/被 reject 的 Promise 不影响其他任务、返回普通值、`size`/`pending`、参数校验。运行 `node --test taskQueue.test.mjs` 全部通过。

## 运行过的命令

```
node --test taskQueue.test.mjs
```

