// Application state. Statistic history never includes prompt text.
// Prompt text is stored only after the user confirms a save, in a separate browser key.
import { DEFAULT_SETTINGS, HISTORY_LIMIT, PROMPT_HISTORY_LIMIT, buildHistoryEntry, pushHistory, sanitizeHistory, sanitizePrompts, sanitizeSettings } from './lib.js';

const SETTINGS_KEY = 'tritobol.settings.v1';
const HISTORY_KEY = 'tritobol.history.v1';
const PROMPTS_KEY = 'tritobol.prompts.v1';
const THEME_KEY = 'tritobol.theme.v1';

function read(key) { try { return JSON.parse(globalThis.localStorage?.getItem(key) ?? 'null'); } catch { return null; } }
function write(key, value) { try { globalThis.localStorage?.setItem(key, JSON.stringify(value)); return true; } catch { return false; } }
function remove(key) { try { globalThis.localStorage?.removeItem(key); } catch { /* storage unavailable */ } }

const listeners = new Set();
export const state = {
  tokenizers: [], settings: sanitizeSettings(read(SETTINGS_KEY)), history: sanitizeHistory(read(HISTORY_KEY)),
  prompts: sanitizePrompts(read(PROMPTS_KEY)),
  result: null, sourceText: null, sourceName: null, busy: false,
};
export const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };
export const notify = (what) => listeners.forEach((fn) => fn(what));

export function saveSettings(settings) { state.settings = sanitizeSettings(settings); write(SETTINGS_KEY, state.settings); notify('settings'); }
export function resetSettings() { state.settings = { ...DEFAULT_SETTINGS }; remove(SETTINGS_KEY); notify('settings'); }
export function clearHistory() { state.history = []; remove(HISTORY_KEY); notify('history'); }
export function setResult(result, sourceText, sourceName) {
  state.result = result; state.sourceText = sourceText; state.sourceName = sourceName;
  const entry = sanitizeHistory([buildHistoryEntry(result, new Date().toISOString())])[0];
  if (entry) {
    state.history = pushHistory(state.history, entry);
    write(HISTORY_KEY, state.history);
  }
  notify('result');
}

export function saveLocalPrompt() {
  const result = state.result;
  if (!result || typeof state.sourceText !== 'string' || typeof result.text !== 'string') {
    return { ok: false, error: 'Run an optimization before saving a prompt.' };
  }
  const previous = state.prompts;
  const entry = sanitizePrompts([{
    at: new Date().toISOString(),
    tokenizer: result.tokenizer?.label || '',
    task_type: result.options?.task_type,
    truncated: !!result.stats?.truncated,
    source_name: state.sourceName || '',
    original_tokens: result.stats?.original_tokens,
    optimized_tokens: result.stats?.optimized_tokens,
    saved_percent: result.stats?.saved_percent,
    original_text: state.sourceText,
    optimized_text: result.text,
  }])[0];
  if (!entry) return { ok: false, error: 'That prompt could not be saved. Existing history was kept.' };
  state.prompts = [entry, ...previous.filter((item) => item.id !== entry.id)].slice(0, PROMPT_HISTORY_LIMIT);
  if (!write(PROMPTS_KEY, state.prompts)) {
    state.prompts = previous;
    return { ok: false, error: 'The browser could not store that prompt. Existing history was kept.' };
  }
  notify('prompts');
  return { ok: true };
}

export function removeHistoryEntry(kind, id) {
  const prompts = kind === 'prompt';
  const previous = prompts ? state.prompts : state.history;
  if (!previous.some((entry) => entry.id === id)) {
    return { ok: false, error: 'That entry is no longer in this browser. Nothing else was removed.' };
  }
  const next = previous.filter((entry) => entry.id !== id);
  if (prompts) state.prompts = next;
  else state.history = next;
  if (!write(prompts ? PROMPTS_KEY : HISTORY_KEY, next)) {
    if (prompts) state.prompts = previous;
    else state.history = previous;
    return { ok: false, error: 'The browser could not update history. Nothing was removed.' };
  }
  notify('history');
  return { ok: true };
}

export function applyImport(plan) {
  if (!plan || plan.blocked) return { ok: false, error: 'Import was blocked. Existing history was kept.' };
  const previousHistory = state.history;
  const previousPrompts = state.prompts;
  const statsNew = Array.isArray(plan.statsNew) ? plan.statsNew : [];
  const promptsNew = Array.isArray(plan.promptsNew) ? plan.promptsNew : [];
  state.history = [...statsNew, ...state.history].slice(0, HISTORY_LIMIT);
  state.prompts = [...promptsNew, ...state.prompts].slice(0, PROMPT_HISTORY_LIMIT);
  if (!write(HISTORY_KEY, state.history) || !write(PROMPTS_KEY, state.prompts)) {
    state.history = previousHistory;
    state.prompts = previousPrompts;
    write(HISTORY_KEY, previousHistory);
    write(PROMPTS_KEY, previousPrompts);
    return { ok: false, error: 'The browser could not store that import. Existing history was kept.' };
  }
  notify('history');
  return { ok: true, unchanged: statsNew.length + promptsNew.length === 0, addedStats: statsNew.length, addedPrompts: promptsNew.length };
}

function systemTheme() {
  try {
    return globalThis.matchMedia?.('(prefers-color-scheme: dark)')?.matches ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export function currentTheme() {
  const stored = read(THEME_KEY);
  return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system';
}

function appliedTheme(preference = currentTheme()) {
  return preference === 'system' ? systemTheme() : preference;
}

export function saveTheme(theme) {
  const preference = theme === 'light' || theme === 'dark' || theme === 'system' ? theme : 'system';
  write(THEME_KEY, preference);
  const applied = appliedTheme(preference);
  const root = globalThis.document?.documentElement;
  if (root) root.dataset.theme = applied;
  const label = applied === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
  globalThis.document?.querySelectorAll('.theme-toggle').forEach((button) => button.setAttribute('aria-label', label));
  const select = globalThis.document?.getElementById('set-theme');
  if (select && select.value !== preference) select.value = preference;
  return preference;
}

export function watchSystemTheme() {
  let media;
  try { media = globalThis.matchMedia?.('(prefers-color-scheme: dark)'); } catch { media = null; }
  if (!media) return;
  const onChange = () => { if (currentTheme() === 'system') saveTheme('system'); };
  if (media.addEventListener) media.addEventListener('change', onChange);
  else if (media.addListener) media.addListener(onChange);
}

export function bindThemeToggles() {
  globalThis.document?.querySelectorAll('.theme-toggle').forEach((button) => {
    button.addEventListener('click', () => saveTheme(appliedTheme() === 'dark' ? 'light' : 'dark'));
  });
  const select = globalThis.document?.getElementById('set-theme');
  select?.addEventListener('change', () => saveTheme(select.value));
}
