/**
 * 组装入口：创建 store、注入 localStorage 适配器、绑定视图与键盘。
 * 见 docs/architecture.md §3、§8.4。
 */

import { createStore } from "./app/store.js";
import { hydrateHistory, setStorageAvailable } from "./app/actions.js";
import { createHistoryStore } from "./storage/history-store.js";
import { createCalculatorView } from "./ui/calculator-view.js";
import { createHistoryView } from "./ui/history-view.js";
import { createKeyboard } from "./ui/keyboard.js";

/** @returns {Storage | null} */
function getLocalStorage() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    // 隐私模式或策略禁止访问。
    return null;
  }
}

const historyStore = createHistoryStore(getLocalStorage());
const store = createStore({ historyStore });

const loaded = historyStore.load();
store.dispatch(hydrateHistory(loaded.entries));
if (!loaded.available) {
  store.dispatch(setStorageAvailable(false));
}

const historyView = createHistoryView({ store });
createCalculatorView({ store });
createKeyboard({ store, historyView });
