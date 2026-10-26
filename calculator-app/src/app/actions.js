/**
 * 动作类型常量与构造器（architecture.md §8.2）。
 * UI 与键盘只派发动作，不直接修改状态。
 */

export const ACTIONS = Object.freeze({
  DIGIT: "digit",
  DECIMAL: "decimal",
  OPERATOR: "operator",
  PERCENT: "percent",
  PAREN: "paren",
  TOGGLE_SIGN: "toggleSign",
  EVALUATE: "evaluate",
  CLEAR_ALL: "clearAll",
  DELETE_BACK: "deleteBack",
  LOAD_HISTORY: "loadHistory",
  CLEAR_HISTORY: "clearHistory",
  HYDRATE_HISTORY: "hydrateHistory",
  SET_STORAGE_AVAILABLE: "setStorageAvailable",
});

export const digit = (value) => ({ type: ACTIONS.DIGIT, value });
export const decimal = () => ({ type: ACTIONS.DECIMAL });
export const operator = (value) => ({ type: ACTIONS.OPERATOR, value });
export const percent = () => ({ type: ACTIONS.PERCENT });
export const paren = (value) => ({ type: ACTIONS.PAREN, value });
export const toggleSign = () => ({ type: ACTIONS.TOGGLE_SIGN });
/** @param {{id?: string, createdAt?: string}} [meta] */
export const evaluate = (meta) => ({ type: ACTIONS.EVALUATE, ...meta });
export const clearAll = () => ({ type: ACTIONS.CLEAR_ALL });
export const deleteBack = () => ({ type: ACTIONS.DELETE_BACK });
export const loadHistory = (id) => ({ type: ACTIONS.LOAD_HISTORY, id });
export const clearHistory = () => ({ type: ACTIONS.CLEAR_HISTORY });
export const hydrateHistory = (entries) => ({
  type: ACTIONS.HYDRATE_HISTORY,
  entries,
});
export const setStorageAvailable = (value) => ({
  type: ACTIONS.SET_STORAGE_AVAILABLE,
  value,
});
