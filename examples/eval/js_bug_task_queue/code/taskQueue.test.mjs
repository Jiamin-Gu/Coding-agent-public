import test from "node:test";
import assert from "node:assert/strict";
import { TaskQueue } from "./taskQueue.mjs";

const tick = () => new Promise((r) => setTimeout(r, 0));

test("并发数不超过 concurrency", async () => {
  const queue = new TaskQueue(2);
  let active = 0;
  let maxActive = 0;

  const tasks = Array.from({ length: 6 }, (_, i) =>
    queue.add(async () => {
      active++;
      maxActive = Math.max(maxActive, active);
      await tick();
      await tick();
      active--;
      return i;
    })
  );

  const results = await Promise.all(tasks);
  assert.equal(maxActive, 2, `最大并发应为 2，实际为 ${maxActive}`);
  assert.deepEqual(results, [0, 1, 2, 3, 4, 5]);
});

test("任务按加入顺序开始执行", async () => {
  const queue = new TaskQueue(1);
  const started = [];

  const tasks = Array.from({ length: 5 }, (_, i) =>
    queue.add(async () => {
      started.push(i);
      await tick();
    })
  );

  await Promise.all(tasks);
  assert.deepEqual(started, [0, 1, 2, 3, 4]);
});

test("onIdle 在空闲时立即 resolve", async () => {
  const queue = new TaskQueue(2);
  let resolved = false;
  queue.onIdle().then(() => {
    resolved = true;
  });
  await tick();
  assert.equal(resolved, true);
});

test("onIdle 在队列清空后 resolve，且不会永久挂起", async () => {
  const queue = new TaskQueue(2);
  const tasks = Array.from({ length: 5 }, () =>
    queue.add(async () => {
      await tick();
    })
  );

  await queue.onIdle();
  // onIdle resolve 时不应还有等待或运行中的任务
  assert.equal(queue.size, 0);
  assert.equal(queue.pending, 0);
  await Promise.all(tasks);
});

test("同步抛异常只 reject 该任务，不影响后续任务", async () => {
  const queue = new TaskQueue(2);

  const failing = queue.add(() => {
    throw new Error("boom");
  });
  const after1 = queue.add(() => 1);
  const after2 = queue.add(async () => 2);

  await assert.rejects(failing, /boom/);
  assert.equal(await after1, 1);
  assert.equal(await after2, 2);
});

test("返回被 reject 的 Promise 也只影响自身", async () => {
  const queue = new TaskQueue(2);
  const bad = queue.add(() => Promise.reject(new Error("nope")));
  const good = queue.add(() => Promise.resolve("ok"));

  await assert.rejects(bad, /nope/);
  assert.equal(await good, "ok");
});

test("支持返回普通值", async () => {
  const queue = new TaskQueue(1);
  assert.equal(await queue.add(() => 42), 42);
});

test("size / pending 反映等待与运行中的数量", async () => {
  const queue = new TaskQueue(2);
  const tasks = Array.from({ length: 4 }, () =>
    queue.add(async () => {
      await tick();
      await tick();
    })
  );

  await tick();
  assert.equal(queue.pending, 2);
  assert.equal(queue.size, 2);

  await Promise.all(tasks);
  assert.equal(queue.pending, 0);
  assert.equal(queue.size, 0);
});

test("构造参数校验", () => {
  assert.throws(() => new TaskQueue(0), TypeError);
  assert.throws(() => new TaskQueue(1.5), TypeError);
  assert.throws(() => new TaskQueue(-1), TypeError);
});
