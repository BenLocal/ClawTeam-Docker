import { test } from "node:test";
import assert from "node:assert/strict";

import {
  HISTORY_VERSION,
  STORAGE_KEY,
  createHistoryStore,
  isValidEntry,
} from "../src/storage/history-store.js";
import { historyEntry } from "./helpers.js";

/**
 * @param {Record<string, string>} [initial]
 */
function createMemoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return {
    map,
    getItem(key) {
      return map.has(key) ? map.get(key) : null;
    },
    setItem(key, value) {
      map.set(key, String(value));
    },
    removeItem(key) {
      map.delete(key);
    },
  };
}

test("history-store: 空存储返回空历史且可用", () => {
  const store = createHistoryStore(createMemoryStorage());
  assert.deepEqual(store.load(), { entries: [], available: true });
});

test("history-store: 保存后可重新读取", () => {
  const storage = createMemoryStorage();
  const store = createHistoryStore(storage);
  const entries = [
    historyEntry("h1", "3 + 4 × 2", "11"),
    historyEntry("h2", "0.1 + 0.2", "0.3"),
  ];

  assert.equal(store.save(entries), true);
  const loaded = store.load();
  assert.equal(loaded.available, true);
  assert.deepEqual(loaded.entries, entries);

  const raw = JSON.parse(storage.getItem(STORAGE_KEY));
  assert.equal(raw.version, HISTORY_VERSION);
});

test("history-store: 损坏 JSON 返回空历史但保持可用", () => {
  const storage = createMemoryStorage({ [STORAGE_KEY]: "{not json" });
  const store = createHistoryStore(storage);
  assert.deepEqual(store.load(), { entries: [], available: true });
});

test("history-store: 版本不符或结构非法返回空历史", () => {
  for (const payload of [
    JSON.stringify({ version: 2, entries: [historyEntry("h1", "1 + 1", "2")] }),
    JSON.stringify({ version: 1, entries: {} }),
    JSON.stringify({ version: 1 }),
    JSON.stringify(null),
    JSON.stringify([1, 2, 3]),
  ]) {
    const store = createHistoryStore(createMemoryStorage({ [STORAGE_KEY]: payload }));
    const loaded = store.load();
    assert.deepEqual(loaded.entries, [], payload);
    assert.equal(loaded.available, true);
  }
});

test("history-store: 逐条校验字段，过滤非法条目", () => {
  const entries = [
    historyEntry("ok", "1 + 1", "2"),
    { id: "", expression: "1 + 1", result: "2", createdAt: "2026-10-26T00:00:00.000Z" },
    { id: "bad-date", expression: "1 + 1", result: "2", createdAt: "not-a-date" },
    { id: "long-expression", expression: "1".repeat(129), result: "2", createdAt: "2026-10-26T00:00:00.000Z" },
    { id: "long-result", expression: "1 + 1", result: "2".repeat(33), createdAt: "2026-10-26T00:00:00.000Z" },
    { id: "missing-result", expression: "1 + 1", createdAt: "2026-10-26T00:00:00.000Z" },
  ];
  const payload = JSON.stringify({ version: 1, entries });
  const store = createHistoryStore(createMemoryStorage({ [STORAGE_KEY]: payload }));
  const loaded = store.load();

  assert.deepEqual(loaded.entries, [historyEntry("ok", "1 + 1", "2")]);
  assert.equal(isValidEntry(entries[0]), true);
  assert.equal(isValidEntry(null), false);
});

test("history-store: 上限 50 条（保存与读取均截断）", () => {
  const entries = Array.from({ length: 60 }, (_, index) =>
    historyEntry(`h-${index}`, `1 + ${index}`, String(index + 1)),
  );
  const storage = createMemoryStorage();
  const store = createHistoryStore(storage);

  assert.equal(store.save(entries), true);
  const loaded = store.load();
  assert.equal(loaded.entries.length, 50);
  assert.equal(loaded.entries[0].id, "h-0");
  assert.equal(loaded.entries[49].id, "h-49");

  // 手工写入 60 条也要在读取时截断。
  storage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, entries }));
  assert.equal(store.load().entries.length, 50);
});

test("history-store: 保存时过滤非法条目", () => {
  const storage = createMemoryStorage();
  const store = createHistoryStore(storage);
  const entries = [
    historyEntry("ok", "1 + 1", "2"),
    { id: "", expression: "x", result: "y", createdAt: "2026-10-26T00:00:00.000Z" },
  ];

  assert.equal(store.save(entries), true);
  assert.deepEqual(store.load().entries, [historyEntry("ok", "1 + 1", "2")]);
});

test("history-store: 写入抛错返回 false", () => {
  const broken = {
    getItem() {
      return null;
    },
    setItem() {
      throw new Error("QuotaExceededError");
    },
    removeItem() {},
  };
  const store = createHistoryStore(broken);
  assert.equal(store.save([historyEntry("h1", "1 + 1", "2")]), false);
});

test("history-store: 读取抛错时标记不可用", () => {
  const broken = {
    getItem() {
      throw new Error("SecurityError");
    },
    setItem() {},
    removeItem() {},
  };
  const store = createHistoryStore(broken);
  assert.deepEqual(store.load(), { entries: [], available: false });
});

test("history-store: clear 删除存储键；失败返回 false", () => {
  const storage = createMemoryStorage({
    [STORAGE_KEY]: JSON.stringify({ version: 1, entries: [] }),
  });
  const store = createHistoryStore(storage);
  assert.equal(store.clear(), true);
  assert.equal(storage.getItem(STORAGE_KEY), null);

  const broken = {
    getItem() {
      return null;
    },
    setItem() {},
    removeItem() {
      throw new Error("nope");
    },
  };
  assert.equal(createHistoryStore(broken).clear(), false);
});

test("history-store: 无存储对象时完全降级", () => {
  const store = createHistoryStore(null);
  assert.deepEqual(store.load(), { entries: [], available: false });
  assert.equal(store.save([historyEntry("h1", "1 + 1", "2")]), false);
  assert.equal(store.clear(), false);
});
