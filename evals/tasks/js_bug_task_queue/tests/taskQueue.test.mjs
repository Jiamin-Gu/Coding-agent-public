import assert from "node:assert/strict";
import { test } from "node:test";
import { TaskQueue } from "../taskQueue.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function withTimeout(promise, ms, what) {
  return Promise.race([promise, sleep(ms).then(() => { throw new Error(`${what} 超时（${ms}ms）`); })]);
}

test("同时运行的任务数不超过并发数，并且确实并行", async () => {
  const q = new TaskQueue(2);
  let running = 0;
  let max = 0;
  const task = () => async () => {
    running++;
    max = Math.max(max, running);
    await sleep(20);
    running--;
  };
  await withTimeout(Promise.all(Array.from({ length: 6 }, () => q.add(task()))), 2000, "任务");
  assert.equal(max, 2);
});

test("任务按加入顺序开始", async () => {
  const q = new TaskQueue(1);
  const started = [];
  const jobs = [1, 2, 3, 4, 5].map((n) => q.add(async () => { started.push(n); await sleep(5); }));
  await withTimeout(Promise.all(jobs), 2000, "任务");
  assert.deepEqual(started, [1, 2, 3, 4, 5]);
});

test("并发数 3 时也按顺序开始", async () => {
  const q = new TaskQueue(3);
  const started = [];
  const jobs = Array.from({ length: 8 }, (_, i) => q.add(async () => { started.push(i); await sleep(10); }));
  await withTimeout(Promise.all(jobs), 2000, "任务");
  assert.deepEqual(started, [0, 1, 2, 3, 4, 5, 6, 7]);
});

test("返回任务的结果，普通值也可以", async () => {
  const q = new TaskQueue(2);
  assert.equal(await q.add(async () => "a"), "a");
  assert.equal(await withTimeout(q.add(() => 42), 1000, "同步任务"), 42);
});

test("一个任务失败不影响其他任务", async () => {
  const q = new TaskQueue(2);
  const results = await withTimeout(Promise.allSettled([
    q.add(async () => 1),
    q.add(async () => { throw new Error("坏了"); }),
    q.add(async () => 3),
  ]), 2000, "任务");
  assert.equal(results[0].value, 1);
  assert.equal(results[1].status, "rejected");
  assert.equal(results[1].reason.message, "坏了");
  assert.equal(results[2].value, 3);
});

test("同步抛异常的任务被 reject，队列继续工作", async () => {
  const q = new TaskQueue(1);
  await assert.rejects(withTimeout(q.add(() => { throw new Error("同步错误"); }), 1000, "任务"), /同步错误/);
  assert.equal(await withTimeout(q.add(async () => "继续"), 1000, "后续任务"), "继续");
  await sleep(0);  // 结果交给调用方和内部计数减一谁先谁后是实现细节，等一轮再检查
  assert.equal(q.pending, 0);
});

test("onIdle：空闲时立即返回，忙时等全部完成", async () => {
  const q = new TaskQueue(2);
  await withTimeout(q.onIdle(), 200, "空闲时的 onIdle");
  let done = 0;
  for (let i = 0; i < 5; i++) q.add(async () => { await sleep(10); done++; });
  await withTimeout(q.onIdle(), 2000, "onIdle");
  assert.equal(done, 5);
  assert.equal(q.size, 0);
  assert.equal(q.pending, 0);
});

test("onIdle 在有任务失败时也会返回", async () => {
  const q = new TaskQueue(2);
  q.add(async () => { throw new Error("x"); }).catch(() => {});
  q.add(() => { throw new Error("y"); }).catch(() => {});
  await withTimeout(q.onIdle(), 1000, "onIdle");
});

test("size 和 pending", async () => {
  const q = new TaskQueue(1);
  const gate = [];
  const jobs = [0, 1, 2].map(() => q.add(() => new Promise((r) => gate.push(r))));
  await sleep(0);
  assert.equal(q.pending, 1);
  assert.equal(q.size, 2);
  while (gate.length < 3) { gate.forEach((r) => r()); await sleep(5); }
  gate.forEach((r) => r());
  await withTimeout(Promise.all(jobs), 1000, "任务");
  assert.equal(q.pending, 0);
});

test("并发数必须是正整数", () => {
  assert.throws(() => new TaskQueue(0), TypeError);
  assert.throws(() => new TaskQueue(1.5), TypeError);
});
