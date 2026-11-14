// Prompt text is persisted only after an explicit user action, in a separate local browser key.
import {
  DEFAULT_SETTINGS, PROMPT_HISTORY_LIMIT, PROMPT_HISTORY_MAX_STORAGE_CHARS, PROMPT_HISTORY_VERSION,
  buildHistoryEntry, buildPromptHistoryEntry, parsePromptHistory, pushHistory, sanitizeHistory, sanitizeSettings,
} from './lib.js';

const SETTINGS_KEY = 'tritobol.settings.v1';
const HISTORY_KEY = 'tritobol.history.v1';
const PROMPT_HISTORY_KEY = 'tritobol.prompt-history.v1';

function read(key) { try { return JSON.parse(globalThis.localStorage?.getItem(key) ?? 'null'); } catch { return null; } }
function write(key, value) { try { globalThis.localStorage?.setItem(key, JSON.stringify(value)); return true; } catch { return false; } }
function remove(key) { try { globalThis.localStorage?.removeItem(key); } catch { /* storage unavailable */ } }

function loadPromptHistory() {
  try {
    const raw = globalThis.localStorage?.getItem(PROMPT_HISTORY_KEY) ?? null;
    return parsePromptHistory(raw);
  } catch {
    return { ok: false, entries: [], error: 'Browser storage is unavailable. Saved prompts cannot be loaded or saved here.' };
  }
}

const loadedPromptHistory = loadPromptHistory();
const listeners = new Set();
export const state = {
  tokenizers: [], settings: sanitizeSettings(read(SETTINGS_KEY)), history: sanitizeHistory(read(HISTORY_KEY)),
  promptHistory: loadedPromptHistory.entries, promptHistoryError: loadedPromptHistory.ok ? null : loadedPromptHistory.error,
  promptHistoryMessage: '', currentPromptHistoryId: null,
  result: null, sourceText: null, sourceName: null, busy: false,
};
export const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };
export const notify = (what) => listeners.forEach((fn) => fn(what));

export function saveSettings(settings) { state.settings = sanitizeSettings(settings); write(SETTINGS_KEY, state.settings); notify('settings'); }
export function resetSettings() { state.settings = { ...DEFAULT_SETTINGS }; remove(SETTINGS_KEY); notify('settings'); }
export function clearHistory() { state.history = []; remove(HISTORY_KEY); notify('history'); }
function persistPromptHistory(entries) {
  const serialized = JSON.stringify({ version: PROMPT_HISTORY_VERSION, entries });
  if (serialized.length > PROMPT_HISTORY_MAX_STORAGE_CHARS) {
    return { ok: false, error: 'This history is too large for browser storage. Delete older entries and try again.' };
  }
  try {
    globalThis.localStorage.setItem(PROMPT_HISTORY_KEY, serialized);
    return { ok: true };
  } catch {
    return { ok: false, error: 'Could not save to this browser (storage may be full or disabled). Nothing was saved; delete older entries or clear history and try again.' };
  }
}

export function savePromptToHistory() {
  if (state.promptHistoryError) {
    return { ok: false, error: `${state.promptHistoryError} Clear history before saving.` };
  }
  let entry;
  try {
    const id = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    entry = buildPromptHistoryEntry(state.result, state.sourceText, state.sourceName, new Date().toISOString(), id);
  } catch (error) {
    return { ok: false, error: error instanceof RangeError ? error.message : 'The current result cannot be saved to history.' };
  }
  const entries = [entry, ...state.promptHistory].slice(0, PROMPT_HISTORY_LIMIT);
  const saved = persistPromptHistory(entries);
  if (!saved.ok) return saved;
  state.promptHistory = entries;
  state.promptHistoryMessage = 'Saved on this browser. It is not synced to other devices.';
  state.currentPromptHistoryId = entry.id;
  notify('promptHistory');
  return { ok: true, entry };
}

export function deletePromptFromHistory(id) {
  if (state.promptHistoryError) return { ok: false, error: state.promptHistoryError };
  const entries = state.promptHistory.filter((entry) => entry.id !== id);
  if (entries.length === state.promptHistory.length) return { ok: true };
  const saved = persistPromptHistory(entries);
  if (!saved.ok) return saved;
  state.promptHistory = entries;
  state.promptHistoryMessage = 'Saved prompt deleted from this browser.';
  if (state.currentPromptHistoryId === id) state.currentPromptHistoryId = null;
  notify('promptHistory');
  return { ok: true };
}

export function clearPromptHistory() {
  try {
    globalThis.localStorage.removeItem(PROMPT_HISTORY_KEY);
  } catch {
    return { ok: false, error: 'Could not clear saved prompts from this browser. Browser storage may be disabled.' };
  }
  state.promptHistory = [];
  state.promptHistoryError = null;
  state.promptHistoryMessage = 'Saved prompt history cleared from this browser.';
  state.currentPromptHistoryId = null;
  notify('promptHistory');
  return { ok: true };
}

export function setResult(result, sourceText, sourceName) {
  state.result = result; state.sourceText = sourceText; state.sourceName = sourceName;
  state.history = pushHistory(state.history, buildHistoryEntry(result, new Date().toISOString()));
  write(HISTORY_KEY, state.history);
  state.currentPromptHistoryId = null;
  state.promptHistoryMessage = '';
  notify('result');
}
