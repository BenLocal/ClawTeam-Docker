import { test } from "node:test";
import assert from "node:assert/strict";

import { createStore } from "../src/app/store.js";
import * as a from "../src/app/actions.js";
import { historyEntry } from "./helpers.js";

/**
 * @param {{saveResult?: boolean, clearResult?: boolean}} [options]
 */
function createFakeHistoryStore(options = {}) {
  const saveResult = options.saveResult ?? true;
  const clearResult = options.clearResult ?? true;
  const calls = { save: /** @type {unknown[][]} */ ([]), clear: 0, load: 0 };
  return {
    calls,
    save(entries) {
      calls.save.push(entries);
      return saveResult;
    },
    clear() {
      calls.clear += 1;
      return clearResult;
    },
    load() {
      calls.load += 1;
      return { entries: [], available: true };
    },
  };
}

test("store: 普通输入不触发持久化", () => {
  const historyStore = createFakeHistoryStore();
  const store = createStore({ historyStore });

  store.dispatch(a.digit("2"));
  store.dispatch(a.operator("+"));
  store.dispatch(a.digit("3"));

  assert.equal(historyStore.calls.save.length, 0);
  assert.equal(historyStore.calls.clear, 0);
});

test("store: 求值成功后保存历史；重复求值不重复保存", () => {
  const historyStore = createFakeHistoryStore();
  const store = createStore({ historyStore });

  store.dispatch(a.digit("2"));
  store.dispatch(a.operator("+"));
  store.dispatch(a.digit("3"));
  store.dispatch(a.evaluate({ id: "e1", createdAt: "2026-10-26T10:00:00.000Z" }));

  assert.equal(historyStore.calls.save.length, 1);
  assert.equal(historyStore.calls.save[0].length, 1);
  assert.equal(historyStore.calls.save[0][0].result, "5");

  store.dispatch(a.evaluate());
  assert.equal(historyStore.calls.save.length, 1);
});

test("store: AC 不清历史，也不写存储", () => {
  const historyStore = createFakeHistoryStore();
  const store = createStore({ historyStore });

  store.dispatch(a.hydrateHistory([historyEntry("h1", "1 + 1", "2")]));
  assert.equal(historyStore.calls.save.length, 0, "hydrate 不应回写");

  store.dispatch(a.clearAll());
  assert.equal(historyStore.calls.save.length, 0);
  assert.equal(historyStore.calls.clear, 0);
});

test("store: clearHistory 调用适配器的 clear()", () => {
  const historyStore = createFakeHistoryStore();
  const store = createStore({ historyStore });

  store.dispatch(a.hydrateHistory([historyEntry("h1", "1 + 1", "2")]));
  store.dispatch(a.clearHistory());

  assert.equal(historyStore.calls.clear, 1);
  assert.deepEqual(store.getState().history, []);
});

test("store: 保存失败时标记 storageAvailable=false 并保留内存历史", () => {
  const historyStore = createFakeHistoryStore({ saveResult: false });
  const store = createStore({ historyStore });

  store.dispatch(a.digit("2"));
  store.dispatch(a.operator("+"));
  store.dispatch(a.digit("3"));
  store.dispatch(a.evaluate({ id: "e1", createdAt: "2026-10-26T10:00:00.000Z" }));

  const state = store.getState();
  assert.equal(state.storageAvailable, false);
  assert.equal(state.history.length, 1);
});

test("store: 清空失败时同样降级", () => {
  const historyStore = createFakeHistoryStore({ clearResult: false });
  const store = createStore({ historyStore });

  store.dispatch(a.hydrateHistory([historyEntry("h1", "1 + 1", "2")]));
  store.dispatch(a.clearHistory());

  assert.equal(store.getState().storageAvailable, false);
  assert.deepEqual(store.getState().history, []);
});

test("store: 订阅者可感知变化，单个订阅者异常不影响其他订阅者", () => {
  const store = createStore();
  /** @type {string[]} */
  const seen = [];

  store.subscribe(() => {
    throw new Error("listener failure");
  });
  const unsubscribe = store.subscribe((state) => {
    seen.push(state.phase);
  });

  store.dispatch(a.digit("1"));
  assert.deepEqual(seen, ["editing"]);

  unsubscribe();
  store.dispatch(a.digit("2"));
  assert.deepEqual(seen, ["editing"]);
});

test("store: 无变化的派发不通知订阅者", () => {
  const store = createStore();
  let notifications = 0;
  store.subscribe(() => {
    notifications += 1;
  });

  store.dispatch({ type: "unknown" });
  assert.equal(notifications, 0);

  store.dispatch(a.clearAll());
  assert.equal(notifications, 0);
});
