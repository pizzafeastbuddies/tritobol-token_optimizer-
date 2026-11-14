// Application state. Browser storage holds settings and numeric history only — never user text.
import { DEFAULT_SETTINGS, buildHistoryEntry, pushHistory, sanitizeHistory, sanitizeSettings } from './lib.js';

const SETTINGS_KEY = 'tritobol.settings.v1';
const HISTORY_KEY = 'tritobol.history.v1';

function read(key) { try { return JSON.parse(globalThis.localStorage?.getItem(key) ?? 'null'); } catch { return null; } }
function write(key, value) { try { globalThis.localStorage?.setItem(key, JSON.stringify(value)); return true; } catch { return false; } }
function remove(key) { try { globalThis.localStorage?.removeItem(key); } catch { /* storage unavailable */ } }

const listeners = new Set();
export const state = {
  tokenizers: [], settings: sanitizeSettings(read(SETTINGS_KEY)), history: sanitizeHistory(read(HISTORY_KEY)),
  result: null, sourceText: null, sourceName: null, busy: false,
};
export const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };
export const notify = (what) => listeners.forEach((fn) => fn(what));

export function saveSettings(settings) { state.settings = sanitizeSettings(settings); write(SETTINGS_KEY, state.settings); notify('settings'); }
export function resetSettings() { state.settings = { ...DEFAULT_SETTINGS }; remove(SETTINGS_KEY); notify('settings'); }
export function clearHistory() { state.history = []; remove(HISTORY_KEY); notify('history'); }
export function setResult(result, sourceText, sourceName) {
  state.result = result; state.sourceText = sourceText; state.sourceName = sourceName;
  state.history = pushHistory(state.history, buildHistoryEntry(result, new Date().toISOString()));
  write(HISTORY_KEY, state.history);
  notify('result');
}
