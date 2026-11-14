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
let copiedText = '';

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
  server = spawn(PYTHON, ['-m', 'tritobol_app', '--no-browser', '--port', String(port)], { cwd: tmp, env: { ...process.env, PYTHONPATH: ROOT, PYTHONIOENCODING: 'utf-8' }, stdio: 'ignore' });
  baseUrl = `http://127.0.0.1:${port}`;
  await until(async () => { try { return (await fetch(`${baseUrl}/api/health`)).ok; } catch { return false; } }, 20000).catch(() => null);
  for (let i = 0; i < 80; i++) { try { if ((await fetch(`${baseUrl}/api/health`)).ok) break; } catch { /* retry */ } await sleep(250); }
  const html = await (await fetch(`${baseUrl}/`)).text();
  dom = new JSDOM(html, { url: `${baseUrl}/`, pretendToBeVisual: true });
  const w = dom.window;
  Object.assign(globalThis, { window: w, document: w.document, location: w.location, localStorage: w.localStorage, Event: w.Event, KeyboardEvent: w.KeyboardEvent });
  Object.defineProperty(globalThis, 'navigator', { value: { clipboard: { writeText: async (text) => { copiedText = text; } } }, configurable: true });
  globalThis.TRITOBOL_BASE_URL = baseUrl;
  const realFetch = globalThis.fetch;
  globalThis.fetch = (...a) => { fetchCalls.push(String(a[0])); return realFetch(...a); };
  w.HTMLElement.prototype.scrollIntoView = () => {};
  w.URL.createObjectURL = () => 'blob:test'; w.URL.revokeObjectURL = () => {};
  await import('../tritobol_app/static/js/app.js');
  await until(() => $('opt-tokenizer').options.length > 0);
});
after(async () => {
  if (server && server.exitCode === null) {
    const exited = new Promise((resolve) => server.once('exit', resolve));
    server.kill();
    await exited;
  }
  fs.rmSync(tmp, { recursive: true, force: true });
  dom?.window.close();
});

const DOC = 'Please review the release notes.\n\nPlease review the release notes.\n\n==========\n\nVersion 2.0 removes /v1/export.   Migrate.\nVersion 2.0 removes /v1/export.\nFinal instruction: answer in three bullets.\n';

test('boot: dashboard shows the real engine and no fake statistics', async () => {
  assert.match($('dash-engine').textContent, /DeepSeek V4\.1 Flash.*ready.*129,280/);
  assert.match($('dash-hero-stat').textContent, /No run yet/);
  assert.match($('dash-session').textContent, /Run an optimization/);
  assert.equal($('view-dashboard').hidden, false);
});

test('navigation switches views and marks the current page', async () => {
  for (const r of ['optimize', 'analytics', 'privacy', 'settings', 'dashboard']) {
    await go(r);
    assert.equal($(`view-${r}`).hidden, false, r);
    assert.equal(dom.window.document.querySelector(`[data-route="${r}"]`).getAttribute('aria-current'), 'page');
    assert.equal([...dom.window.document.querySelectorAll('[data-view]')].filter((v) => !v.hidden).length, 1);
  }
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

test('settings persist, validate, reset; automatic run history stores numbers only', async () => {
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
  assert.equal(localStorage.getItem('tritobol.history.v1'), null);
});

test('prompt text is saved only by explicit opt-in and can be reviewed, opened, copied, deleted, and cleared locally', async () => {
  const promptKey = 'tritobol.prompt-history.v1';
  localStorage.removeItem(promptKey);
  await optimizeNow(DOC);
  assert.equal(localStorage.getItem(promptKey), null); // a successful run never stores prompt text automatically
  const callsBeforeSave = fetchCalls.length;
  $('btn-save-history').click();
  assert.equal($('history-save-confirmation').hidden, false);
  assert.match($('history-save-confirmation').textContent, /not encrypted by Tritobol/);
  assert.match($('history-save-confirmation').textContent, /not synced/);
  assert.equal($('history-save-confirm').disabled, true);
  $('history-save-consent').checked = true;
  $('history-save-consent').dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  $('history-save-confirm').click();
  let saved = JSON.parse(localStorage.getItem(promptKey));
  assert.equal(saved.version, 1);
  assert.equal(saved.entries.length, 1);
  assert.equal(saved.entries[0].original_text, DOC);
  assert.equal(saved.entries[0].optimized_text, $('panel-compare').querySelectorAll('pre')[1].textContent);
  assert.equal(fetchCalls.length, callsBeforeSave); // saving uses browser storage, not a server/API request
  assert.match($('history-save-status').textContent, /not synced to other devices/);

  await go('prompt-history');
  assert.match($('prompt-history-list').textContent, /Original prompt/);
  assert.equal($('prompt-history-list').querySelectorAll('.prompt-history-card').length, 1);
  const review = $('prompt-history-list').querySelector('details');
  assert.match(review.textContent, /Original prompt/);
  assert.match(review.textContent, /Optimized result/);
  $('prompt-history-list').querySelector('button').click(); // open original in optimizer
  assert.equal($('input-text').value, DOC);
  assert.equal($('results').hidden, true);

  await go('prompt-history');
  copiedText = '';
  $('prompt-history-list').querySelectorAll('button')[1].click(); // copy optimized
  await until(() => copiedText.length > 0);
  assert.equal(copiedText, saved.entries[0].optimized_text);
  dom.window.confirm = () => true;
  $('prompt-history-list').querySelectorAll('button')[2].click(); // delete one
  assert.equal(JSON.parse(localStorage.getItem(promptKey)).entries.length, 0);

  await optimizeNow(DOC);
  $('btn-save-history').click();
  $('history-save-consent').checked = true;
  $('history-save-consent').dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  $('history-save-confirm').click();
  assert.equal(JSON.parse(localStorage.getItem(promptKey)).entries.length, 1);
  await go('prompt-history');
  $('btn-clear-prompt-history').click();
  assert.equal(localStorage.getItem(promptKey), null);
  assert.match($('prompt-history-list').textContent, /No prompts saved yet/);
  await go('optimize');
  $('btn-save-history').click();
  assert.equal($('history-save-confirmation').hidden, false); // a cleared result can be explicitly saved again
  $('history-save-cancel').click();
});

test('prompt history reports browser storage quota errors without claiming a save', async () => {
  const promptKey = 'tritobol.prompt-history.v1';
  localStorage.removeItem(promptKey);
  await optimizeNow(DOC);
  const storagePrototype = Object.getPrototypeOf(localStorage);
  const originalSetItem = storagePrototype.setItem;
  Object.defineProperty(storagePrototype, 'setItem', {
    configurable: true,
    writable: true,
    value(key, value) {
      if (key === promptKey) throw new DOMException('quota exceeded', 'QuotaExceededError');
      return originalSetItem.call(this, key, value);
    },
  });
  try {
    $('btn-save-history').click();
    $('history-save-consent').checked = true;
    $('history-save-consent').dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    $('history-save-confirm').click();
    assert.match($('history-save-status').textContent, /storage may be full or disabled/);
    assert.equal(localStorage.getItem(promptKey), null);
    assert.equal($('btn-save-history').disabled, false);
  } finally {
    Object.defineProperty(storagePrototype, 'setItem', { configurable: true, writable: true, value: originalSetItem });
  }
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
