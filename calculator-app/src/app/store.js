/**
 * Store：订阅 / 派发 / 持久化副作用（architecture.md §8.4）。
 * 纯 reducer 在 state.js；存储通过参数注入。
 */

import { createInitialState, reduce } from "./state.js";
import { ACTIONS, setStorageAvailable } from "./actions.js";

/** @param {{historyStore?: object|null, initialState?: import("./state.js").CalcState}} [options] */
export function createStore(options = {}) {
  const historyStore = options.historyStore ?? null;
  let state = options.initialState ?? createInitialState();
  const listeners = new Set();

  function notify(previousState) {
    for (const listener of [...listeners]) {
      try {
        listener(state, previousState);
      } catch {
        // 单个订阅者异常不影响其他订阅者。
      }
    }
  }

  function getState() {
    return state;
  }

  /** @param {{type: string} & Record<string, any>} action */
  function dispatch(action) {
    if (!action || typeof action.type !== "string") {
      return;
    }

    const previousState = state;
    state = reduce(previousState, action);

    let storageFailed = false;
    if (
      historyStore &&
      state.history !== previousState.history &&
      action.type !== ACTIONS.HYDRATE_HISTORY
    ) {
      let saved = false;
      try {
        saved =
          action.type === ACTIONS.CLEAR_HISTORY
            ? historyStore.clear()
            : historyStore.save(state.history);
      } catch {
        saved = false;
      }
      storageFailed = !saved;
    }

    if (storageFailed && state.storageAvailable) {
      state = reduce(state, setStorageAvailable(false));
    }
    if (state !== previousState) {
      notify(previousState);
    }
  }

  /** @param {(state: any, previousState: any) => void} listener */
  function subscribe(listener) {
    if (typeof listener !== "function") {
      return () => {};
    }
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }

  return { getState, dispatch, subscribe };
}
