/**
 * localStorage 适配器（architecture.md §5.7、§10）。
 * 存储对象通过参数注入，便于用内存假对象测试；所有访问均捕获异常。
 */

import {
  MAX_HISTORY_ENTRIES,
  MAX_HISTORY_EXPRESSION_CHARS,
  MAX_HISTORY_RESULT_CHARS,
  MAX_ID_LENGTH,
} from "../core/limits.js";

export const STORAGE_KEY = "calculator.history.v1";
export const HISTORY_VERSION = 1;

/**
 * @typedef {{id:string, expression:string, result:string, createdAt:string}} HistoryEntry
 * @typedef {{getItem: Function, setItem: Function, removeItem: Function}} StorageLike
 */

/** @param {unknown} entry @returns {entry is HistoryEntry} */
export function isValidEntry(entry) {
  if (!entry || typeof entry !== "object") {
    return false;
  }
  const { id, expression, result, createdAt } = /** @type {HistoryEntry} */ (entry);
  if (typeof id !== "string" || id.length === 0 || id.length > MAX_ID_LENGTH) {
    return false;
  }
  if (
    typeof expression !== "string" ||
    expression.length === 0 ||
    expression.length > MAX_HISTORY_EXPRESSION_CHARS
  ) {
    return false;
  }
  if (
    typeof result !== "string" ||
    result.length === 0 ||
    result.length > MAX_HISTORY_RESULT_CHARS
  ) {
    return false;
  }
  return typeof createdAt === "string" && !Number.isNaN(Date.parse(createdAt));
}

function normalizeEntry(entry) {
  const source = /** @type {HistoryEntry} */ (entry);
  return {
    id: source.id,
    expression: source.expression,
    result: source.result,
    createdAt: source.createdAt,
  };
}

/** @param {StorageLike | null} storageLike */
export function createHistoryStore(storageLike) {
  const storage = storageLike ?? null;

  function load() {
    if (!storage) {
      return { entries: [], available: false };
    }

    let raw;
    try {
      raw = storage.getItem(STORAGE_KEY);
    } catch {
      return { entries: [], available: false };
    }
    if (typeof raw !== "string" || raw.length === 0) {
      return { entries: [], available: true };
    }

    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return { entries: [], available: true };
    }
    if (!parsed || typeof parsed !== "object") {
      return { entries: [], available: true };
    }
    if (
      parsed.version !== HISTORY_VERSION ||
      !Array.isArray(parsed.entries)
    ) {
      return { entries: [], available: true };
    }

    const entries = parsed.entries
      .filter(isValidEntry)
      .slice(0, MAX_HISTORY_ENTRIES)
      .map(normalizeEntry);
    return { entries, available: true };
  }

  /** @param {HistoryEntry[]} entries */
  function save(entries) {
    if (!storage) {
      return false;
    }
    try {
      const safeEntries = Array.isArray(entries)
        ? entries.filter(isValidEntry).slice(0, MAX_HISTORY_ENTRIES).map(normalizeEntry)
        : [];
      storage.setItem(
        STORAGE_KEY,
        JSON.stringify({ version: HISTORY_VERSION, entries: safeEntries }),
      );
      return true;
    } catch {
      return false;
    }
  }

  function clear() {
    if (!storage) {
      return false;
    }
    try {
      storage.removeItem(STORAGE_KEY);
      return true;
    } catch {
      return false;
    }
  }

  return { load, save, clear };
}
