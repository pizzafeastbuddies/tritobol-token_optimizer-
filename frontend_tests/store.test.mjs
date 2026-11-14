import test from 'node:test';
import assert from 'node:assert/strict';

const HISTORY_KEY = 'tritobol.prompt-history.v1';
const storageDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');

function installStorage({ value = null, failReads = false, failWrites = false } = {}) {
  let stored = value;
  const removed = [];
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem(key) {
        if (failReads && key === HISTORY_KEY) throw new Error('storage blocked');
        return key === HISTORY_KEY ? stored : null;
      },
      setItem(key, next) {
        if (failWrites && key === HISTORY_KEY) throw new Error('quota exceeded');
        if (key === HISTORY_KEY) stored = next;
      },
      removeItem(key) {
        if (failWrites && key === HISTORY_KEY) throw new Error('storage blocked');
        if (key === HISTORY_KEY) stored = null;
        removed.push(key);
      },
    },
  });
  return { removed, get value() { return stored; } };
}

function restoreStorage() {
  if (storageDescriptor) Object.defineProperty(globalThis, 'localStorage', storageDescriptor);
  else delete globalThis.localStorage;
}

test('unavailable browser storage is reported and never treated as saved history', async () => {
  installStorage({ failReads: true, failWrites: true });
  try {
    const store = await import('../tritobol_app/static/js/store.js?unavailable-history-test');
    assert.match(store.state.promptHistoryError, /Browser storage is unavailable/);
    assert.equal(store.savePromptToHistory().ok, false);
    assert.match(store.savePromptToHistory().error, /Clear history before saving/);
    const cleared = store.clearPromptHistory();
    assert.equal(cleared.ok, false);
    assert.match(cleared.error, /could not clear/i);
  } finally {
    restoreStorage();
  }
});

test('unsupported saved-history versions are not overwritten and can be explicitly cleared', async () => {
  const storage = installStorage({ value: JSON.stringify({ version: 99, entries: [] }) });
  try {
    const store = await import('../tritobol_app/static/js/store.js?unsupported-history-test');
    assert.match(store.state.promptHistoryError, /unsupported version or format/);
    assert.equal(store.savePromptToHistory().ok, false);
    const cleared = store.clearPromptHistory();
    assert.equal(cleared.ok, true);
    assert.equal(storage.value, null);
    assert.equal(store.state.promptHistoryError, null);
    assert.deepEqual(store.state.promptHistory, []);
  } finally {
    restoreStorage();
  }
});
