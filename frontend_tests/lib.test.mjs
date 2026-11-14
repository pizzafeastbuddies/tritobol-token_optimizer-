import test from 'node:test';
import assert from 'node:assert/strict';
import * as L from '../tritobol_app/static/js/lib.js';

const stats = (o) => ({ original_tokens: 100, optimized_tokens: 60, saved_tokens: 40, saved_percent: 40, truncated: false, discarded_tokens: 0, ...o });
const result = (o = {}) => ({ stats: stats(o.stats), budget: { requested: null, enforced: false, verified_within_budget: null, recount_tokens: null, ...o.budget },
  warning: o.warning ?? null, sensitive_findings: o.findings ?? 0, options: { sensitive_data: 'skip', ...o.options }, tokenizer: { label: 'T' } });

test('formatting helpers', () => {
  assert.equal(L.formatInt(1234567), '1,234,567');
  assert.equal(L.formatPercent(61.904), '61.9%');
  assert.equal(L.formatPercent(-3.25), '-3.3%');
  assert.equal(L.formatBytes(500), '500 B');
  assert.equal(L.formatBytes(2048), '2.0 KB');
  assert.equal(L.formatBytes(2 * 1024 * 1024), '2.00 MB');
});

test('codePointLength counts like Python len()', () => {
  assert.equal(L.codePointLength('a🎃é'), 3);
  assert.equal('a🎃é'.length, 4); // the UTF-16 length it replaces
  assert.equal(L.codePointLength(''), 0);
});

test('validateInput', () => {
  assert.equal(L.validateInput('').ok, false);
  assert.equal(L.validateInput('  \n\t').ok, false);
  assert.equal(L.validateInput('hello').ok, true);
  const big = L.validateInput('x', L.MAX_INPUT_BYTES + 1);
  assert.equal(big.ok, false);
  assert.match(big.error, /limit is 2 MB/);
  assert.equal(L.validateInput('x', L.MAX_INPUT_BYTES).ok, true); // exactly at the limit is allowed
  assert.equal(L.validateInput('€'.repeat(700000)).ok, false); // 3-byte chars counted as bytes
});

test('validateBudget accepts only whole numbers >= 1', () => {
  for (const empty of ['', '   ', null, undefined]) assert.deepEqual(L.validateBudget(empty), { ok: true, value: null });
  assert.deepEqual(L.validateBudget('42'), { ok: true, value: 42 });
  assert.deepEqual(L.validateBudget('1,024'), { ok: true, value: 1024 });
  for (const bad of ['abc', '1.5', '1e3', '0', '-5', '--1', '12abc', '1e21', '100000001']) {
    assert.equal(L.validateBudget(bad).ok, false, `should reject ${bad}`);
  }
  assert.match(L.validateBudget('0').error, /1 or more/);
  assert.match(L.validateBudget('x').error, /whole number/);
});

test('savingsSummary tells the truth for positive, zero and negative savings', () => {
  assert.equal(L.savingsSummary(stats()).kind, 'saved');
  assert.match(L.savingsSummary(stats()).headline, /40 tokens saved \(40\.0%\)/);
  const none = L.savingsSummary(stats({ saved_tokens: 0, saved_percent: 0 }));
  assert.equal(none.kind, 'none');
  const neg = L.savingsSummary(stats({ saved_tokens: -5, saved_percent: -5 }));
  assert.equal(neg.kind, 'increase');
  assert.match(neg.headline, /5 tokens longer \(-5\.0%\)/);
});

test('truncationSummary: truncated, within budget, no budget, budget not met', () => {
  const t = L.truncationSummary(result({ stats: { truncated: true, discarded_tokens: 33 }, budget: { requested: 40, enforced: true, verified_within_budget: true, recount_tokens: 40 }, warning: 'engine warning text' }));
  assert.equal(t.level, 'warn');
  assert.ok(t.details.includes('engine warning text'));
  assert.ok(t.details.some((d) => /not a summary/.test(d)));
  assert.ok(t.details.some((d) => /Verified by re-counting/.test(d)));
  assert.equal(L.truncationSummary(result({ budget: { requested: 500, enforced: true, verified_within_budget: true, recount_tokens: 60 } })).level, 'ok');
  assert.equal(L.truncationSummary(result()).level, 'info');
  const bad = L.truncationSummary(result({ stats: { truncated: true }, budget: { requested: 10, enforced: true, verified_within_budget: false, recount_tokens: 12 } }));
  assert.equal(bad.level, 'error');
  assert.match(bad.headline, /not met/);
});

test('sensitiveSummary is never silent when something was found', () => {
  assert.equal(L.sensitiveSummary(result()), null);
  assert.equal(L.sensitiveSummary(result({ findings: 2, options: { sensitive_data: 'off' } })), null);
  const skip = L.sensitiveSummary(result({ findings: 2 }));
  assert.equal(skip.level, 'warn');
  assert.match(skip.headline, /left in the optimized text/);
  assert.ok(skip.details.some((d) => /incomplete/.test(d)));
  assert.match(L.sensitiveSummary(result({ findings: 1, options: { sensitive_data: 'mask' } })).headline, /\[REDACTED\]/);
});

test('barWidths and downloadFilename', () => {
  assert.deepEqual(L.barWidths(100, 25), { original: 100, optimized: 25 });
  assert.deepEqual(L.barWidths(0, 0), { original: 0, optimized: 0 });
  assert.equal(L.downloadFilename('prompt.txt'), 'prompt.optimized.txt');
  assert.equal(L.downloadFilename('C:\\docs\\notes.md'), 'notes.optimized.md');
  assert.equal(L.downloadFilename('README'), 'README.optimized.txt');
  assert.equal(L.downloadFilename(null), 'optimized.txt');
});

test('history keeps numbers only, is capped and survives corrupt storage', () => {
  const entry = L.buildHistoryEntry({ ...result({ budget: { requested: 7 } }), text: 'SECRET TEXT', tokenizer: { label: 'Tok' } }, '2026-01-01T00:00:00Z');
  assert.equal(JSON.stringify(entry).includes('SECRET'), false);
  assert.equal(entry.budget, 7);
  let list = [];
  for (let i = 0; i < 15; i++) list = L.pushHistory(list, { ...entry, original_tokens: i });
  assert.equal(list.length, L.HISTORY_LIMIT);
  assert.equal(list[0].original_tokens, 14); // newest first
  assert.deepEqual(L.sanitizeHistory('garbage'), []);
  assert.deepEqual(L.sanitizeHistory([{ at: 1 }, null, 5]), []);
  assert.equal(L.sanitizeHistory([entry]).length, 1);
  const t = L.sessionTotals([{ original_tokens: 100, optimized_tokens: 50 }, { original_tokens: 100, optimized_tokens: 100 }]);
  assert.deepEqual(t, { runs: 2, original: 200, optimized: 150, saved: 50, percent: 25 });
  assert.equal(L.sessionTotals([]).percent, 0);
});

test('prompt history is versioned, bounded, and validates every saved text field', () => {
  const promptResult = { ...result(), text: 'optimized prompt' };
  const entry = L.buildPromptHistoryEntry(promptResult, 'original prompt', 'prompt.txt', '2026-01-01T00:00:00.000Z', 'entry-1');
  assert.equal(entry.original_text, 'original prompt');
  assert.equal(entry.optimized_text, 'optimized prompt');
  const stored = JSON.stringify({ version: L.PROMPT_HISTORY_VERSION, entries: [entry] });
  assert.deepEqual(L.parsePromptHistory(stored), { ok: true, entries: [entry] });
  assert.deepEqual(L.parsePromptHistory(null), { ok: true, entries: [] });
  assert.equal(L.parsePromptHistory('{broken').ok, false);
  assert.equal(L.parsePromptHistory(JSON.stringify({ version: 99, entries: [entry] })).ok, false);
  assert.equal(L.parsePromptHistory(JSON.stringify({ version: 1, entries: [{ ...entry, optimized_text: 7 }] })).ok, false);
  assert.equal(L.parsePromptHistory('x'.repeat(L.PROMPT_HISTORY_MAX_STORAGE_CHARS + 1)).ok, false);
  assert.throws(() => L.buildPromptHistoryEntry(
    promptResult, 'x'.repeat(L.PROMPT_HISTORY_MAX_TEXT_CHARS), 'too-long.txt', '2026-01-01T00:00:00.000Z', 'entry-2',
  ), /combined text characters/);
  assert.equal(L.sanitizePromptHistory({
    version: 1, entries: Array.from({ length: L.PROMPT_HISTORY_LIMIT + 2 }, (_, i) => ({ ...entry, id: `entry-${i}` })),
  }).entries.length, L.PROMPT_HISTORY_LIMIT);
});

test('sanitizeSettings falls back safely', () => {
  assert.deepEqual(L.sanitizeSettings(null), L.DEFAULT_SETTINGS);
  const s = L.sanitizeSettings({ tokenizer: 'x', budget: 'abc', task_type: 'evil', sensitive_data: 'mask', protect_code_blocks: 'yes' });
  assert.deepEqual(s, { tokenizer: 'x', budget: '', task_type: 'auto', sensitive_data: 'mask', protect_code_blocks: true });
});

const ops = [
  { tag: 'equal', a: ['k1', 'k2', 'k3', 'k4', 'k5', 'k6', 'k7', 'k8', 'k9', 'k10'], a_start: 1, b_start: 1 },
  { tag: 'delete', a: ['gone'], a_start: 11, b_start: 11 },
  { tag: 'replace', a: ['old  text', 'x'], b: ['old text'], a_start: 12, b_start: 11, words: [[{ t: 'equal', a: 'old', b: 'old' }]] },
  { tag: 'insert', b: ['new'], a_start: 14, b_start: 12 },
  { tag: 'equal', a: ['t1'], a_start: 14, b_start: 13 },
];

test('diffRows maps every opcode and pairs replaced lines', () => {
  const rows = L.diffRows(ops);
  assert.deepEqual(rows.map((r) => r.kind).slice(10), ['removed', 'changed', 'removed', 'added', 'equal']);
  const changed = rows.find((r) => r.kind === 'changed');
  assert.equal(changed.a, 'old  text'); assert.equal(changed.b, 'old text'); assert.ok(changed.words);
  assert.equal(rows.find((r) => r.kind === 'added').bNo, 12);
});

test('diffBlocks collapses long unchanged runs but keeps context', () => {
  const blocks = L.diffBlocks(L.diffRows(ops), 3);
  const collapsed = blocks.find((b) => b.type === 'collapsed');
  assert.equal(collapsed.rows.length, 7); // 10 equal lines at the start: keep the last 3 only
  assert.equal(blocks[0].type, 'collapsed');
  const total = blocks.reduce((n, b) => n + b.rows.length, 0);
  assert.equal(total, L.diffRows(ops).length); // nothing is lost, only grouped
  assert.equal(L.diffBlocks(L.diffRows([{ tag: 'equal', a: ['a', 'b', 'c'], a_start: 1, b_start: 1 }]), 3).some((b) => b.type === 'collapsed'), false);
});

test('diffViewModel handles unavailable and identical diffs', () => {
  assert.deepEqual(L.diffViewModel({ available: false, reason: 'too big' }), { available: false, reason: 'too big', blocks: [] });
  assert.equal(L.diffViewModel({ available: true, identical: true, ops: [], summary: {} }).identical, true);
  assert.equal(L.diffViewModel({ available: true, identical: false, ops, summary: {} }).blocks.length > 0, true);
});

test('clipForDisplay limits huge text but reports it', () => {
  assert.deepEqual(L.clipForDisplay('abc', 10), { text: 'abc', clipped: false, total: 3 });
  const c = L.clipForDisplay('x'.repeat(50), 10);
  assert.equal(c.text.length, 10); assert.equal(c.clipped, true); assert.equal(c.total, 50);
});
