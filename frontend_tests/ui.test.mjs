// UI workflow tests: the real browser modules run in jsdom and talk to a real Tritobol Flask process (no mocked backend).
import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PYTHON = process.env.TRITOBOL_PYTHON || 'python';
let server, baseUrl, dom, tmp;
let fetchCalls = [];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (id) => dom.window.document.getElementById(id);
const sha = (p) => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
async function until(fn, ms = 20000) { const t = Date.now(); while (Date.now() - t < ms) { const v = fn(); if (v) return v; await sleep(25); } throw new Error('timed out waiting for condition'); }
function freePort() { return new Promise((res) => { const s = net.createServer().listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function typeInto(id, value) { const el = $(id); el.value = value; el.dispatchEvent(new dom.window.Event('input', { bubbles: true })); }
function go(route) { dom.window.location.hash = `#/${route}`; return sleep(30); }
async function pickFile(inputId, file) {
  const el = $(inputId);
  Object.defineProperty(el, 'files', { value: [file], configurable: true });
  el.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
}
async function optimizeNow(text, budget = '') {
  await go('optimize');
  typeInto('input-text', text); typeInto('opt-budget', budget);
  $('results').hidden = true; $('result-tiles').replaceChildren();
  $('btn-optimize').click();
  await until(() => $('result-tiles').children.length === 4);
}
const tiles = () => [...$('result-tiles').children].map((t) => t.querySelector('.value').textContent);

before(async () => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'tritobol-ui-'));
  const port = await freePort();
  server = spawn(PYTHON, ['-m', 'tritobol_app', '--no-browser', '--port', String(port)], { cwd: tmp, env: { ...process.env, PYTHONPATH: ROOT, PYTHONIOENCODING: 'utf-8', TRITOBOL_DB: path.join(tmp, 'tritobol.sqlite') }, stdio: 'ignore' });
  baseUrl = `http://127.0.0.1:${port}`;
  await until(async () => { try { return (await fetch(`${baseUrl}/api/health`)).ok; } catch { return false; } }, 20000).catch(() => null);
  for (let i = 0; i < 80; i++) { try { if ((await fetch(`${baseUrl}/api/health`)).ok) break; } catch { /* retry */ } await sleep(250); }
  const html = await (await fetch(`${baseUrl}/`)).text();
  dom = new JSDOM(html, { url: `${baseUrl}/`, pretendToBeVisual: true });
  const w = dom.window;
  Object.assign(globalThis, { window: w, document: w.document, location: w.location, localStorage: w.localStorage, sessionStorage: w.sessionStorage, Event: w.Event, KeyboardEvent: w.KeyboardEvent });
  Object.defineProperty(globalThis, 'navigator', { value: { clipboard: { writeText: async () => {} } }, configurable: true });
  globalThis.TRITOBOL_BASE_URL = baseUrl;
  const realFetch = globalThis.fetch;
  const jar = new Map();
  globalThis.fetch = async (url, opts = {}) => {
    fetchCalls.push(String(url));
    const headers = new Headers(opts.headers || {});
    if ([...jar.keys()].length) headers.set('cookie', [...jar].map(([k, v]) => `${k}=${v}`).join('; '));
    const res = await realFetch(url, { ...opts, headers, credentials: 'include' });
    const setCookies = typeof res.headers.getSetCookie === 'function' ? res.headers.getSetCookie() : [];
    for (const cookie of setCookies) {
      const pair = String(cookie).split(';', 1)[0];
      const eq = pair.indexOf('=');
      if (eq > 0) jar.set(pair.slice(0, eq).trim(), pair.slice(eq + 1).trim());
    }
    return res;
  };
  w.HTMLElement.prototype.scrollIntoView = () => {};
  w.URL.createObjectURL = () => 'blob:test'; w.URL.revokeObjectURL = () => {};
  await import('../tritobol_app/static/js/app.js');
  await until(() => $('opt-tokenizer').options.length > 0 && document.documentElement.dataset.session === 'out');
  await go('signup');
  typeInto('signup-name', 'Workspace User');
  typeInto('signup-email', 'workspace@example.com');
  typeInto('signup-password', 'Longerphrase1');
  typeInto('signup-confirm', 'Longerphrase1');
  $('signup-submit').click();
  await until(() => (dom.window.location.hash || '').includes('signin') || /already/i.test($('signup-status')?.textContent || ''));
  if (!(dom.window.location.hash || '').includes('signin')) await go('signin');
  await until(() => $('signin-password'));
  typeInto('signin-email', 'workspace@example.com');
  $('signin-password').value = 'Longerphrase1';
  $('signin-submit').click();
  await until(() => $('view-dashboard').hidden === false);
});
after(async () => {
  server?.kill();
  dom?.window.close();
  for (let i = 0; i < 10; i++) {
    try { fs.rmSync(tmp, { recursive: true, force: true }); return; } catch { await sleep(200); }
  }
});

const DOC = 'Please review the release notes.\n\nPlease review the release notes.\n\n==========\n\nVersion 2.0 removes /v1/export.   Migrate.\nVersion 2.0 removes /v1/export.\nFinal instruction: answer in three bullets.\n';

test('boot: dashboard shows the real engine and no fake statistics', async () => {
  assert.match($('dash-engine').textContent, /DeepSeek V4\.1 Flash.*ready.*129,280/);
  assert.match($('dash-hero-stat').textContent, /No run yet/);
  assert.match($('dash-session').textContent, /Run an optimization/);
  assert.equal($('view-dashboard').hidden, false);
});

test('navigation switches views and marks the current page', async () => {
  for (const r of ['optimize', 'analytics', 'settings', 'dashboard']) {
    await go(r);
    assert.equal($(`view-${r}`).hidden, false, r);
    assert.equal(dom.window.document.querySelector(`[data-route="${r}"]`).getAttribute('aria-current'), 'page');
    assert.equal([...dom.window.document.querySelectorAll('[data-view]')].filter((v) => !v.hidden).length, 1);
  }
  await go('privacy');
  assert.equal($('view-privacy').hidden, false);
  assert.equal(dom.window.document.querySelector('[data-route="privacy"]'), null);
  assert.equal([...dom.window.document.querySelectorAll('[data-view]')].filter((v) => !v.hidden).length, 1);
});

test('tokenizer list contains only the tokenizer that really exists', async () => {
  assert.deepEqual([...$('opt-tokenizer').options].map((o) => o.textContent), ['DeepSeek V4.1 Flash (bundled)']);
  assert.match($('tok-status').textContent, /Active: DeepSeek V4\.1 Flash/);
});

test('editor: counts, clear, and empty-input validation without a backend call', async () => {
  await go('optimize');
  typeInto('input-text', 'héllo 🎃');
  assert.equal($('char-count').textContent, '7 characters');
  fetchCalls = [];
  typeInto('input-text', '   ');
  $('btn-optimize').click();
  await sleep(50);
  assert.match($('input-error').textContent, /Enter or load some text/);
  assert.equal(fetchCalls.filter((u) => u.endsWith('/api/optimize')).length, 0);
  typeInto('input-text', 'something'); $('btn-clear').click();
  assert.equal($('input-text').value, ''); assert.equal($('char-count').textContent, '0 characters');
});

test('budget validation blocks bad values before any request', async () => {
  await go('optimize');
  typeInto('input-text', 'hello world');
  for (const bad of ['abc', '0', '-3', '1.5']) {
    typeInto('opt-budget', bad); fetchCalls = [];
    $('btn-optimize').click(); await sleep(40);
    assert.equal($('budget-error').hidden, false, bad);
    assert.equal(fetchCalls.filter((u) => u.endsWith('/api/optimize')).length, 0, bad);
  }
  typeInto('opt-budget', ''); assert.equal($('budget-error').hidden, true);
});

test('optimize: real results, statistics consistent, original text untouched', async () => {
  await optimizeNow(DOC);
  const [orig, opt, saved, pct] = tiles();
  const n = (s) => Number(s.replace(/,/g, ''));
  assert.ok(n(orig) > n(opt));
  assert.equal(n(saved), n(orig) - n(opt));
  assert.equal(pct, `${((n(saved) / n(orig)) * 100).toFixed(1)}%`);
  assert.equal($('input-text').value, DOC); // never modified
  const panes = $('panel-compare').querySelectorAll('pre');
  assert.equal(panes[0].textContent, DOC);
  assert.notEqual(panes[1].textContent, DOC);
  assert.match($('result-banner').textContent, /No token budget set/);
  assert.match($('run-status').textContent, /Done in/);
  // ground truth straight from the backend
  const token = dom.window.document.querySelector('meta[name="tritobol-token"]').content;
  const truth = await (await fetch(`${baseUrl}/api/optimize`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Tritobol-Token': token }, body: JSON.stringify({ text: DOC }) })).json();
  assert.equal(panes[1].textContent, truth.result.text);
  assert.equal(n(opt), truth.result.stats.optimized_tokens);
});

test('diff tab shows removed and kept lines and tabs work by keyboard', async () => {
  $('tab-diff').click();
  assert.equal($('panel-diff').hidden, false); assert.equal($('panel-compare').hidden, true);
  assert.ok($('panel-diff').querySelectorAll('.drow.removed, .drow.changed').length > 0);
  assert.ok($('panel-diff').querySelectorAll('.drow.equal').length > 0 || $('panel-diff').querySelectorAll('.drow.changed').length > 0);
  $('tab-compare').dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  assert.equal($('tab-diff').getAttribute('aria-selected'), 'true');
  $('tab-details').click();
  assert.match($('panel-details').textContent, /What the cleanup removed/);
});

test('truncation warning is prominent and honest', async () => {
  await optimizeNow(Array.from({ length: 300 }, (_, i) => `word${i}`).join(' '), '20');
  const banner = $('result-banner');
  assert.match(banner.textContent, /Older content was removed/);
  assert.match(banner.textContent, /not a summary/);
  assert.match(banner.textContent, /Verified by re-counting: the output is \d+ tokens \(budget 20\)/);
  assert.ok(banner.querySelector('.banner-warn'));
});

test('a budget smaller than one character shows the engine limit on the budget field', async () => {
  await go('optimize'); $('results').hidden = true;
  typeInto('input-text', '🎃'); typeInto('opt-budget', '1');
  $('btn-optimize').click();
  await until(() => !$('budget-error').hidden);
  assert.match($('budget-error').textContent, /too small/);
  assert.equal($('btn-optimize').disabled, false); // controls recover after an error
});

test('credential-looking values produce a visible warning', async () => {
  $('opt-sensitive').value = 'skip';
  await optimizeNow("Config line:\napi_key = 'sk-abcdefghijklmnop123456'\nand some more text.");
  assert.match($('result-banner').textContent, /credential-looking value\(s\) were found and left in the optimized text/);
});

test('user text is rendered as text, never as HTML', async () => {
  $('opt-sensitive').value = 'skip';
  await optimizeNow('<img src=x onerror="window.__pwned=1"> <script>window.__pwned=2</script> hello hello hello');
  assert.equal(dom.window.__pwned, undefined);
  assert.equal($('panel-compare').querySelector('img'), null);
  assert.match($('panel-compare').textContent, /<img src=x/);
});

test('analytics shows real numbers from the latest run', async () => {
  await go('analytics');
  assert.equal($('analytics-body').hidden, false); assert.equal($('analytics-empty').hidden, true);
  assert.match($('analytics-body').textContent, /Latest run/);
  assert.match($('analytics-body').textContent, /before budget cut/);
  assert.ok($('analytics-body').querySelectorAll('.bar-row').length >= 2);
});

test('file loading: valid UTF-8 loads; invalid files error and keep the text', async () => {
  await go('optimize');
  typeInto('input-text', 'MY DRAFT');
  const bad = [['latin1.txt', Buffer.from('café', 'latin1'), /not valid UTF-8/], ['empty.txt', Buffer.alloc(0), /empty/], ['pic.png', Buffer.from('xx'), /Unsupported/]];
  for (const [name, buf, re] of bad) {
    $('input-error').hidden = true;
    await pickFile('file-input', new File([buf], name));
    await until(() => !$('input-error').hidden);
    assert.match($('input-error').textContent, re, name);
    assert.equal($('input-text').value, 'MY DRAFT', name);
  }
  const src = path.join(tmp, 'source.txt');
  fs.writeFileSync(src, 'Héllo 🎃\n日本語', 'utf8');
  const before = sha(src);
  await pickFile('file-input', new File([fs.readFileSync(src)], 'source.txt'));
  await until(() => $('input-text').value.startsWith('Héllo'));
  assert.equal($('input-text').value, 'Héllo 🎃\n日本語');
  assert.match($('file-info').textContent, /Loaded source\.txt/);
  assert.equal(sha(src), before);
});

test('export: new file, numbered on collision, original never touched', async () => {
  const src = path.join(tmp, 'prompt.txt');
  fs.writeFileSync(src, DOC, 'utf8');
  const before = sha(src);
  await pickFile('file-input', new File([fs.readFileSync(src)], 'prompt.txt'));
  await until(() => $('file-info').textContent.includes('prompt.txt'));
  $('btn-optimize').click();
  await until(() => $('export-name').value === 'prompt.optimized.txt');
  const outDir = path.join(tmp, 'out');
  $('export-dir').value = outDir;
  $('btn-save-copy').click();
  await until(() => /Saved a new file/.test($('export-status').textContent));
  const first = path.join(outDir, 'prompt.optimized.txt');
  assert.ok(fs.existsSync(first));
  const firstHash = sha(first);
  $('btn-save-copy').click();
  await until(() => /numbered name/.test($('export-status').textContent));
  assert.ok(fs.existsSync(path.join(outDir, 'prompt.optimized (1).txt')));
  assert.equal(sha(first), firstHash);
  $('export-name').value = 'prompt.txt'; $('export-dir').value = tmp; $('btn-save-copy').click();
  await until(() => $('export-status').textContent.includes('prompt (1).txt') && !$('btn-save-copy').disabled);
  assert.ok(fs.existsSync(path.join(tmp, 'prompt (1).txt'))); // same name as the original -> numbered copy
  assert.equal(sha(src), before);
});

test('export errors are shown, not swallowed', async () => {
  const blocker = path.join(tmp, 'afile'); fs.writeFileSync(blocker, 'x');
  $('export-dir').value = blocker; $('btn-save-copy').click();
  await until(() => /Export failed/.test($('export-status').textContent));
  assert.ok($('export-status').classList.contains('err-text'));
});

test('privacy page states local processing and detection limits', async () => {
  await go('privacy');
  const t = $('view-privacy').textContent;
  assert.match(t, /127\.0\.0\.1/); assert.match(t, /not complete secret detection/); assert.match(t, /no outbound network requests/);
});

test('settings persist, validate, reset; history stores numbers only', async () => {
  await go('settings');
  $('set-task').value = 'coding'; $('set-sensitive').value = 'mask'; typeInto('set-budget', '77');
  $('btn-save-settings').click();
  assert.match($('set-status').textContent, /saved/);
  assert.equal(JSON.parse(localStorage.getItem('tritobol.settings.v1')).task_type, 'coding');
  assert.equal($('opt-task').value, 'coding'); assert.equal($('opt-budget').value, '77');
  typeInto('set-budget', 'zzz'); $('btn-save-settings').click();
  assert.equal($('set-budget-error').hidden, false);
  const stored = JSON.stringify({ ...localStorage });
  assert.equal(stored.includes('Please review'), false); assert.equal(stored.includes('sk-abcdef'), false);
  $('btn-reset-settings').click();
  assert.equal(localStorage.getItem('tritobol.settings.v1'), null); assert.equal($('opt-task').value, 'auto');
  $('btn-clear-history').click();
  assert.match($('set-status').textContent, /again/);
  assert.notEqual(localStorage.getItem('tritobol.history.v1'), null);
  $('btn-clear-history').click();
  assert.equal(localStorage.getItem('tritobol.history.v1'), null);
});

test('custom tokenizer upload: invalid rejected with a message, nothing added', async () => {
  await go('optimize');
  await pickFile('tok-file', new File([Buffer.from('not json')], 'bad.json'));
  await until(() => /Tokenizer not loaded/.test($('tok-status').textContent));
  assert.equal($('opt-tokenizer').options.length, 1);
});

test('backend unavailable: clear message, text kept, no result shown', async () => {
  await go('optimize'); $('results').hidden = true;
  const good = globalThis.TRITOBOL_BASE_URL;
  globalThis.TRITOBOL_BASE_URL = `http://127.0.0.1:${await freePort()}`; // nothing listens here
  typeInto('input-text', 'text to optimize'); typeInto('opt-budget', '');
  $('btn-optimize').click();
  await until(() => /Cannot reach the Tritobol backend/.test($('run-status').textContent));
  assert.ok($('run-status').classList.contains('err-text'));
  assert.equal($('input-text').value, 'text to optimize'); assert.equal($('results').hidden, true);
  globalThis.TRITOBOL_BASE_URL = good;
});

// ---------------------------------------------------------------------------------------------
// Theme, history management, backup import/export, draft reopening and results page.
// These drive the real modules (store.js, history.js, editor.js, results.js) through the real DOM.
// ---------------------------------------------------------------------------------------------
const STORE = '../tritobol_app/static/js/store.js';
const THEME_KEY = 'tritobol.theme.v1';
const mkStat = (n, extra = {}) => ({ at: `2026-01-${String(10 + n).padStart(2, '0')}T12:00:00.000Z`, tokenizer: 'Test tokenizer', original_tokens: 100 + n, optimized_tokens: 60 + n, saved_tokens: 40, saved_percent: 40, truncated: false, budget: null, task_type: 'auto', ...extra });
const readBlob = (blob) => (typeof blob.text === 'function' ? blob.text() : new Promise((resolve, reject) => { const r = new dom.window.FileReader(); r.onload = () => resolve(String(r.result)); r.onerror = reject; r.readAsText(blob); }));
async function wipeHistory() {
  const store = await import(STORE);
  store.clearHistory();
  for (const p of [...store.state.prompts]) store.removeHistoryEntry('prompt', p.id);
  return store;
}
async function importFile(text, name = 'backup.json') {
  $('history-preview').hidden = true;
  await pickFile('history-file', new File([text], name));
  await until(() => $('history-status').textContent && /Review the preview|not|could not|Existing history was kept/.test($('history-status').textContent));
  await sleep(20);
}

test('theme: preference persists, applies to the page, and follows the system only in system mode', async () => {
  const store = await import(STORE);
  const root = document.documentElement;
  let systemDark = false;
  const listeners = new Set();
  globalThis.matchMedia = () => ({ get matches() { return systemDark; }, addEventListener: (_t, fn) => listeners.add(fn), removeEventListener: (_t, fn) => listeners.delete(fn) });
  try {
    localStorage.removeItem(THEME_KEY);
    assert.equal(store.currentTheme(), 'system', 'default is system');
    localStorage.setItem(THEME_KEY, JSON.stringify('purple'));
    assert.equal(store.currentTheme(), 'system', 'unknown stored value falls back');
    localStorage.setItem(THEME_KEY, '{not json');
    assert.equal(store.currentTheme(), 'system', 'corrupt stored value falls back');

    assert.equal(store.saveTheme('dark'), 'dark');
    assert.equal(root.dataset.theme, 'dark');
    assert.equal(JSON.parse(localStorage.getItem(THEME_KEY)), 'dark');
    assert.equal(store.currentTheme(), 'dark');
    for (const b of document.querySelectorAll('.theme-toggle')) assert.equal(b.getAttribute('aria-label'), 'Switch to light theme');
    assert.equal($('set-theme').value, 'dark');

    assert.equal(store.saveTheme('bogus'), 'system', 'invalid value is stored as system');
    assert.equal(root.dataset.theme, 'light', 'system with a light OS applies light');
    for (const b of document.querySelectorAll('.theme-toggle')) assert.equal(b.getAttribute('aria-label'), 'Switch to dark theme');

    store.watchSystemTheme();
    assert.equal(listeners.size, 1, 'a system-change listener is registered');
    systemDark = true; listeners.forEach((fn) => fn());
    assert.equal(root.dataset.theme, 'dark', 'system mode follows the OS');
    store.saveTheme('light');
    systemDark = false; listeners.forEach((fn) => fn()); systemDark = true; listeners.forEach((fn) => fn());
    assert.equal(root.dataset.theme, 'light', 'an explicit choice is not overridden by the OS');

    // Controls wired at boot by bindThemeToggles
    const toggle = document.querySelector('.theme-toggle');
    store.saveTheme('light');
    toggle.click(); assert.equal(root.dataset.theme, 'dark'); assert.equal(JSON.parse(localStorage.getItem(THEME_KEY)), 'dark');
    toggle.click(); assert.equal(root.dataset.theme, 'light'); assert.equal(JSON.parse(localStorage.getItem(THEME_KEY)), 'light');
    $('set-theme').value = 'dark'; $('set-theme').dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    assert.equal(root.dataset.theme, 'dark'); assert.equal(store.currentTheme(), 'dark');
    $('set-theme').value = 'system'; $('set-theme').dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    assert.equal(store.currentTheme(), 'system');
  } finally {
    delete globalThis.matchMedia;
    store.saveTheme('system');
  }
});

test('history: runs and confirmed prompts are stored, filtered, reopened and removed', async () => {
  const store = await wipeHistory();
  await optimizeNow(DOC);
  await optimizeNow(Array.from({ length: 300 }, (_, i) => `word${i}`).join(' '), '20');
  assert.equal(store.state.history.length, 2);
  assert.equal(store.state.history.filter((e) => e.truncated).length, 1, 'exactly one run hit the budget');

  // Saving a prompt needs the explicit confirmation box.
  $('save-prompt-ack').checked = false;
  $('btn-save-prompt').click();
  assert.match($('save-prompt-status').textContent, /Tick the box/);
  assert.equal(store.state.prompts.length, 0);
  await optimizeNow(DOC);
  $('save-prompt-ack').checked = true;
  $('btn-save-prompt').click();
  assert.match($('save-prompt-status').textContent, /Prompt saved in this browser/);
  assert.equal(store.state.prompts.length, 1);
  assert.ok(localStorage.getItem('tritobol.prompts.v1').includes('Please review the release notes'));
  assert.equal(localStorage.getItem('tritobol.history.v1').includes('Please review'), false, 'statistics never contain prompt text');

  await go('history');
  assert.equal($('history-empty').hidden, true);
  assert.equal($('history-list').hidden, false);
  assert.match($('history-usage').textContent, /3 of 10 statistic runs and 1 of 50 saved prompts/);
  const items = () => [...$('history-list').querySelectorAll('article.history-item')];
  assert.equal(items().length, 4, '3 statistic rows + 1 saved prompt');

  // Filters
  typeInto('history-search', 'no-such-text-anywhere');
  assert.equal(items().length, 0);
  assert.match($('history-list').textContent, /No saved prompts match/);
  assert.match($('history-list').textContent, /No statistic records match/);
  typeInto('history-search', 'release notes');
  assert.equal(items().length, 1, 'the search also looks inside saved prompt text');
  typeInto('history-search', '');
  $('history-truncated').value = 'yes'; $('history-truncated').dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  assert.equal(items().length, 1, 'only the budget-cut run');
  $('history-truncated').value = 'no'; $('history-truncated').dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  assert.equal(items().length, 3);
  $('history-truncated').value = 'any'; $('history-truncated').dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  typeInto('history-from', '2999-01-01');
  assert.equal(items().length, 0, 'date filter excludes everything before the start date');
  typeInto('history-from', ''); typeInto('history-to', '2000-01-01');
  assert.equal(items().length, 0, 'date filter excludes everything after the end date');
  typeInto('history-to', '');
  assert.equal(items().length, 4);

  // Reopen puts the original text back in the optimizer
  typeInto('input-text', 'something else');
  const reopen = [...$('history-list').querySelectorAll('button')].find((b) => b.textContent === 'Reopen');
  reopen.click();
  assert.equal($('input-text').value, DOC);
  assert.ok(dom.window.location.hash.includes('optimize'));

  // Remove deletes exactly one entry and persists it
  await go('history');
  const statsBefore = store.state.history.length;
  const promptsBefore = store.state.prompts.length;
  const removeButtons = () => [...$('history-list').querySelectorAll('button')].filter((b) => b.textContent === 'Remove');
  removeButtons().at(-1).click();
  assert.equal(store.state.history.length, statsBefore - 1);
  assert.equal(store.state.prompts.length, promptsBefore);
  assert.equal(JSON.parse(localStorage.getItem('tritobol.history.v1')).length, statsBefore - 1);
  assert.match($('history-status').textContent, /removed/);
  const unknown = store.removeHistoryEntry('stat', 'does-not-exist');
  assert.equal(unknown.ok, false); assert.equal(store.state.history.length, statsBefore - 1, 'unknown id removes nothing');
  removeButtons()[0].click();
  assert.equal(store.state.prompts.length, 0, 'the prompt Remove button removes the saved prompt');
});

test('loadDraft fills the optimizer, shows the source name and resets errors', async () => {
  const { loadDraft } = await import('../tritobol_app/static/js/editor.js');
  await go('history');
  loadDraft('hello draft', 'notes.txt');
  assert.equal($('input-text').value, 'hello draft');
  assert.equal($('file-info').hidden, false);
  assert.match($('file-info').textContent, /notes\.txt.*never modified/);
  assert.ok(dom.window.location.hash.includes('optimize'));
  loadDraft('plain draft');
  assert.equal($('file-info').hidden, true);
  loadDraft(12345);
  assert.equal($('input-text').value, '', 'non-string input is treated as empty, not "12345"');
});

test('history backup: export contains what was chosen, import previews first, skips duplicates, rejects bad files', async () => {
  const store = await wipeHistory();
  await optimizeNow(DOC);
  $('save-prompt-ack').checked = true; $('btn-save-prompt').click();
  await optimizeNow(Array.from({ length: 300 }, (_, i) => `word${i}`).join(' '), '20');
  const stats = store.state.history.map((e) => e.id);
  const prompts = store.state.prompts.map((e) => e.id);
  assert.equal(stats.length, 2); assert.equal(prompts.length, 1);

  // Export (anchor clicks are captured instead of navigating)
  await go('history');
  let blob = null; let name = null;
  const realCreate = globalThis.URL.createObjectURL; const realClick = dom.window.HTMLAnchorElement.prototype.click;
  globalThis.URL.createObjectURL = (b) => { blob = b; return 'blob:test'; };
  dom.window.HTMLAnchorElement.prototype.click = function () { name = this.getAttribute('download'); };
  let json;
  try { $('btn-history-export').click(); json = await readBlob(blob); } finally { globalThis.URL.createObjectURL = realCreate; dom.window.HTMLAnchorElement.prototype.click = realClick; }
  assert.match(name, /^tritobol-history-\d{4}-\d{2}-\d{2}\.json$/);
  assert.match($('history-status').textContent, /Backup download started/);
  const backup = JSON.parse(json);
  assert.equal(backup.format, 'tritobol-history'); assert.equal(backup.version, 1);
  assert.equal(backup.statistics.length, 2); assert.equal(backup.prompts.length, 1);
  assert.equal(JSON.stringify(backup.statistics).includes('Please review'), false, 'statistics carry no prompt text');
  assert.equal(backup.prompts[0].original_text, DOC);

  // Preview does not write anything
  store.clearHistory();
  store.removeHistoryEntry('prompt', prompts[0]);
  assert.equal(store.state.history.length, 0); assert.equal(store.state.prompts.length, 0);
  await importFile(json);
  assert.equal($('history-preview').hidden, false);
  assert.match($('history-preview').textContent, /2 new statistic record\(s\) and 1 new saved prompt\(s\)/);
  assert.equal($('btn-import-confirm').hidden, false);
  assert.equal(store.state.history.length, 0, 'nothing is written before confirmation');
  assert.equal(store.state.prompts.length, 0);

  // Cancel keeps everything
  $('btn-import-cancel').click();
  assert.equal($('history-preview').hidden, true);
  assert.match($('history-status').textContent, /cancelled/);
  assert.equal(store.state.history.length, 0);

  // Confirm restores exactly the exported records
  await importFile(json);
  $('btn-import-confirm').click();
  assert.match($('history-status').textContent, /Imported 2 statistic record\(s\) and 1 saved prompt\(s\)/);
  assert.deepEqual(store.state.history.map((e) => e.id).sort(), [...stats].sort());
  assert.deepEqual(store.state.prompts.map((e) => e.id), prompts);
  assert.equal(JSON.parse(localStorage.getItem('tritobol.history.v1')).length, 2, 'import is persisted');
  assert.equal(JSON.parse(localStorage.getItem('tritobol.prompts.v1')).length, 1);

  // Importing the same backup again adds nothing
  await importFile(json);
  assert.match($('history-preview').textContent, /0 new statistic record\(s\) and 0 new saved prompt\(s\)/);
  assert.equal($('btn-import-confirm').hidden, true, 'nothing to confirm');
  $('btn-import-cancel').click();
  assert.equal(store.state.history.length, 2); assert.equal(store.state.prompts.length, 1);

  // Bad files leave history untouched and say why
  const snapshot = JSON.stringify([store.state.history, store.state.prompts]);
  const bad = [
    ['not json at all', /not valid JSON/],
    [JSON.stringify({ hello: 'world' }), /not a Tritobol history backup/],
    [JSON.stringify([1, 2, 3]), /not a Tritobol history backup/],
    [JSON.stringify({ format: 'tritobol-history', version: 2, statistics: [], prompts: [] }), /version is not supported/],
    [JSON.stringify({ format: 'tritobol-history', version: 1, statistics: 'x' }), /missing its history lists/],
  ];
  for (const [text, pattern] of bad) {
    $('history-status').textContent = '';
    await importFile(text);
    assert.match($('history-status').textContent, pattern);
    assert.equal($('history-status').className, 'err-text');
    assert.equal($('history-preview').hidden, true);
    assert.equal(JSON.stringify([store.state.history, store.state.prompts]), snapshot, 'history unchanged by a rejected file');
  }
});

test('history import: incomplete records are skipped and the storage limit is respected', async () => {
  const store = await wipeHistory();
  const many = Array.from({ length: 15 }, (_, i) => mkStat(i));
  const garbage = [{ at: 'x' }, null, { tokenizer: 'x', original_tokens: 'many' }];
  const backup = { format: 'tritobol-history', version: 1, exported_at: '2026-02-01T00:00:00.000Z', statistics: [...many, ...garbage], prompts: [{ original_text: 'only half a prompt' }] };
  await importFile(JSON.stringify(backup));
  assert.equal($('history-preview').hidden, false);
  assert.match($('history-preview').textContent, /10 new statistic record\(s\) and 0 new saved prompt\(s\)/);
  assert.match($('history-preview').textContent, /statistic limit/);
  $('btn-import-confirm').click();
  assert.equal(store.state.history.length, 10, 'HISTORY_LIMIT is never exceeded');
  assert.equal(store.state.prompts.length, 0);
  assert.match($('history-status').textContent, /Imported 10 statistic record/);
  await wipeHistory();
});

test('store: blocked plans and failing browser storage never lose existing history', async () => {
  const store = await wipeHistory();
  const keep = mkStat(1);
  assert.equal(store.applyImport({ blocked: false, statsNew: [keep], promptsNew: [] }).ok, true);
  const before = JSON.stringify(store.state.history);

  assert.equal(store.applyImport(null).ok, false);
  assert.equal(store.applyImport({ blocked: true, statsNew: [mkStat(2)], promptsNew: [] }).ok, false);
  assert.equal(JSON.stringify(store.state.history), before);

  const real = globalThis.localStorage;
  globalThis.localStorage = { getItem: (k) => real.getItem(k), removeItem: (k) => real.removeItem(k), setItem() { throw new Error('QuotaExceededError'); } };
  try {
    const imp = store.applyImport({ blocked: false, statsNew: [mkStat(3)], promptsNew: [] });
    assert.equal(imp.ok, false); assert.match(imp.error, /Existing history was kept/);
    assert.equal(JSON.stringify(store.state.history), before, 'in-memory history rolled back');
    const rm = store.removeHistoryEntry('stat', store.state.history[0].id);
    assert.equal(rm.ok, false); assert.equal(JSON.stringify(store.state.history), before, 'failed removal is rolled back');
    const saved = store.saveLocalPrompt();
    assert.equal(saved.ok, false);
  } finally { globalThis.localStorage = real; }
  assert.equal(JSON.stringify(JSON.parse(real.getItem('tritobol.history.v1'))), before, 'stored copy untouched');

  // applyImport enforces the limits itself, even when handed an oversized plan
  store.clearHistory();
  const big = store.applyImport({ blocked: false, statsNew: Array.from({ length: 15 }, (_, i) => mkStat(i)), promptsNew: [] });
  assert.equal(big.ok, true);
  assert.equal(store.state.history.length, 10, 'HISTORY_LIMIT enforced by applyImport');
  assert.equal(JSON.parse(localStorage.getItem('tritobol.history.v1')).length, 10);
  await wipeHistory();
});

test('results page: empty state without a run, full rendering with a run, text never HTML', async () => {
  const store = await import(STORE);
  const { renderResultsPage } = await import('../tritobol_app/static/js/results.js');
  store.state.result = null; store.state.sourceText = null; store.state.sourceName = null;
  await go('results');
  assert.equal($('view-results').hidden, false);
  assert.equal($('results-empty').hidden, false);
  assert.equal($('results-page').hidden, true);
  assert.equal($('results-page').children.length, 0);

  await optimizeNow('<img src=x onerror="window.__pwned=3"> repeat repeat repeat\n\n<img src=x onerror="window.__pwned=3"> repeat repeat repeat');
  await go('results');
  const page = $('results-page');
  assert.equal($('results-empty').hidden, true); assert.equal(page.hidden, false);
  assert.equal(page.querySelectorAll('.tile').length, 4);
  assert.ok(page.querySelector('.banner'));
  assert.deepEqual([...page.querySelectorAll('h2')].map((x) => x.textContent), ['Compare', 'Diff']);
  assert.equal(page.querySelectorAll('.pane').length, 2);
  assert.ok(page.querySelector('.pane pre').textContent.includes('<img src=x'), 'shown as text');
  assert.equal(page.querySelector('img'), null, 'no element was created from user text');
  assert.equal(globalThis.__pwned, undefined);
  assert.match(page.textContent, /The latest run in this tab/);
  assert.equal(page.querySelector('a.btn').getAttribute('href'), '#/optimize');

  // Re-rendering is idempotent
  renderResultsPage(); renderResultsPage();
  assert.equal(page.querySelectorAll('.tile').length, 4);

  // A budget run shows the honest truncation banner here too
  await optimizeNow(Array.from({ length: 300 }, (_, i) => `word${i}`).join(' '), '20');
  await go('results');
  assert.match(page.textContent, /Older content was removed/);
  assert.ok(page.querySelector('.banner-warn'));
  await wipeHistory();
});
