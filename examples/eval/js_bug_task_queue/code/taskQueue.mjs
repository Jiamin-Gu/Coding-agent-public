/**
 * 并发受限的异步任务队列。
 *
 *   const queue = new TaskQueue(2);
 *   const result = await queue.add(() => fetchSomething());
 *
 * 规则：
 * - add(fn) 返回一个 Promise：fn() 的结果（可以是普通值，也可以是 Promise）作为它的值；
 *   fn 抛出异常或返回被 reject 的 Promise 时，这个 Promise 被 reject，但不影响队列里的其他任务。
 * - 同时运行的任务数不超过 concurrency；任务按加入的顺序开始执行。
 * - onIdle() 返回一个 Promise：队列里没有等待的任务、也没有运行中的任务时 resolve；
 *   调用时已经空闲则立即 resolve。
 * - size：等待中（还没开始）的任务数；pending：正在运行的任务数。
 */
export class TaskQueue {
  constructor(concurrency = 1) {
    if (!Number.isInteger(concurrency) || concurrency < 1) {
      throw new TypeError("concurrency 必须是正整数");
    }
    this.concurrency = concurrency;
    this.queue = [];
    this.running = 0;
    this.idleWaiters = [];
  }

  get size() {
    return this.queue.length;
  }

  get pending() {
    return this.running;
  }

  add(fn) {
    return new Promise((resolve, reject) => {
      this.queue.push({ fn, resolve, reject });
      this._next();
    });
  }

  _next() {
    while (this.running < this.concurrency && this.queue.length > 0) {
      const item = this.queue.shift();
      this.running++;
      // 用 Promise.resolve().then(...) 包一层：既能把同步抛出的异常转成 reject，
      // 也能正确处理 fn 返回普通值（非 Promise）的情况。
      Promise.resolve()
        .then(() => item.fn())
        .then(item.resolve, item.reject)
        .finally(() => {
          this.running--;
          this._next();
        });
    }
    this._checkIdle();
  }

  _checkIdle() {
    if (this.running === 0 && this.queue.length === 0 && this.idleWaiters.length > 0) {
      const waiters = this.idleWaiters;
      this.idleWaiters = [];
      for (const resolve of waiters) resolve();
    }
  }

  onIdle() {
    if (this.running === 0 && this.queue.length === 0) {
      return Promise.resolve();
    }
    return new Promise((resolve) => this.idleWaiters.push(resolve));
  }
}
