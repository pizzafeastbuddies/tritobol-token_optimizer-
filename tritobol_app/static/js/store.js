// Application state. Browser storage holds settings, numeric run history, and prompts the user explicitly saved.
import {
  DEFAULT_SETTINGS, buildHistoryEntry, mergeImport, persistImport, pushHistory, samePrompt, sanitizeHistory, sanitizePrompts, sanitizeSettings,
  PROMPT_HISTORY_LIMIT,
} from './lib.js';

const SETTINGS_KEY = 'tritobol.settings.v1';
const HISTORY_KEY = 'tritobol.history.v1';
const PROMPTS_KEY = 'tritobol.prompts.v1';
const THEME_KEY = 'tritobol.theme.v1';

function read(key) { try { return JSON.parse(globalThis.localStorage?.getItem(key) ?? 'null'); } catch { return null; } }
function writeJson(key, value) {
  try {
    if (!globalThis.localStorage) return { ok: false, error: 'This browser cannot store history. Existing history was kept.' };
    globalThis.localStorage.setItem(key, JSON.stringify(value));
    return { ok: true };
  } catch (err) {
    const quota = err && (err.name === 'QuotaExceededError' || err.name === 'NS_ERROR_DOM_QUOTA_REACHED' || err.code === 22);
    return { ok: false, error: quota ? 'This browser ran out of local storage. Existing history was kept.' : 'The browser refused to store history. Existing history was kept.' };
  }
}
function write(key, value) { return writeJson(key, value).ok; }
function remove(key) { try { globalThis.localStorage?.removeItem(key); } catch { /* storage unavailable */ } }

const listeners = new Set();
export const state = {
  tokenizers: [], settings: sanitizeSettings(read(SETTINGS_KEY)), history: sanitizeHistory(read(HISTORY_KEY)),
  prompts: sanitizePrompts(read(PROMPTS_KEY)),
  result: null, sourceText: null, sourceName: null, busy: false,
};
export const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };
export const notify = (what) => listeners.forEach((fn) => fn(what));

export function currentTheme() {
  const v = read(THEME_KEY);
  if (v === 'light' || v === 'dark' || v === 'system') return v;
  if (v === 'midnight' || v === 'ember') return 'dark';
  return 'system';
}

function systemIsDark() {
  return !!globalThis.matchMedia?.('(prefers-color-scheme: dark)')?.matches;
}

export function resolvedTheme(choice = currentTheme()) {
  if (choice === 'light' || choice === 'dark') return choice;
  return systemIsDark() ? 'dark' : 'light';
}

function paintThemeToggles() {
  const dark = resolvedTheme() === 'dark';
  globalThis.document?.querySelectorAll('.theme-toggle').forEach((btn) => {
    btn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
    btn.setAttribute('aria-pressed', dark ? 'true' : 'false');
  });
}

export function saveTheme(name) {
  const theme = name === 'light' || name === 'dark' || name === 'system' ? name : 'system';
  write(THEME_KEY, theme);
  const root = globalThis.document?.documentElement;
  if (root) {
    root.dataset.theme = resolvedTheme(theme);
    root.dataset.themeChoice = theme;
    root.style.colorScheme = root.dataset.theme;
  }
  paintThemeToggles();
  return theme;
}

export function bindThemeToggles() {
  globalThis.document?.querySelectorAll('.theme-toggle').forEach((btn) => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', () => { saveTheme(resolvedTheme() === 'dark' ? 'light' : 'dark'); });
  });
  paintThemeToggles();
}

export function watchSystemTheme() {
  const mq = globalThis.matchMedia?.('(prefers-color-scheme: dark)');
  if (!mq?.addEventListener) return;
  mq.addEventListener('change', () => { if (currentTheme() === 'system') saveTheme('system'); });
}

export function saveSettings(settings) { state.settings = sanitizeSettings(settings); write(SETTINGS_KEY, state.settings); notify('settings'); }
export function resetSettings() { state.settings = { ...DEFAULT_SETTINGS }; remove(SETTINGS_KEY); notify('settings'); }
export function clearHistory() {
  state.history = []; state.prompts = [];
  remove(HISTORY_KEY); remove(PROMPTS_KEY);
  notify('history');
}
export function setResult(result, sourceText, sourceName) {
  state.result = result; state.sourceText = sourceText; state.sourceName = sourceName;
  state.history = pushHistory(state.history, buildHistoryEntry(result, new Date().toISOString(), sourceName));
  write(HISTORY_KEY, state.history);
  notify('result');
}

export function savePromptRecord(record) {
  if (state.prompts.some((p) => samePrompt(p, record))) {
    return { ok: false, error: 'This prompt is already in local history. Nothing was added.' };
  }
  if (state.prompts.length >= PROMPT_HISTORY_LIMIT) {
    return { ok: false, error: `Local history already has ${PROMPT_HISTORY_LIMIT} saved prompts. Erase one before saving another. Nothing was added.` };
  }
  const next = pushHistory(state.prompts, record, PROMPT_HISTORY_LIMIT);
  const stored = writeJson(PROMPTS_KEY, next);
  if (!stored.ok) return stored;
  state.prompts = next;
  notify('prompts');
  return { ok: true };
}

export function removeHistoryEntry(kind, id) {
  if (kind === 'prompt') {
    const next = state.prompts.filter((e) => e.id !== id);
    const stored = writeJson(PROMPTS_KEY, next);
    if (!stored.ok) return stored;
    state.prompts = next;
  } else {
    const next = state.history.filter((e) => e.id !== id);
    const stored = writeJson(HISTORY_KEY, next);
    if (!stored.ok) return stored;
    state.history = next;
  }
  notify('history');
  return { ok: true };
}

export function applyImport(plan) {
  const prevStats = state.history.slice();
  const prevPrompts = state.prompts.slice();
  const merged = mergeImport(state.history, state.prompts, plan);
  const persisted = persistImport(merged, (stats, prompts) => {
    const a = writeJson(HISTORY_KEY, stats);
    if (!a.ok) return a;
    const b = writeJson(PROMPTS_KEY, prompts);
    if (!b.ok) { writeJson(HISTORY_KEY, prevStats); return b; }
    return { ok: true };
  });
  if (!persisted.ok || persisted.unchanged) return persisted;
  state.history = merged.stats;
  state.prompts = merged.prompts;
  notify('history');
  return persisted;
}
