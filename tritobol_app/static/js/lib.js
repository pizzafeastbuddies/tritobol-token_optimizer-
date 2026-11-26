// Pure helpers: no DOM, no network. Everything here is unit-tested with `node --test frontend_tests`.

export const MAX_INPUT_BYTES = 2 * 1024 * 1024;
export const MAX_BUDGET = 100_000_000;
export const HISTORY_LIMIT = 10;
export const PROMPT_HISTORY_LIMIT = 50;
const MAX_SAVED_PROMPT_CHARS = 200_000;
export const DEFAULT_SETTINGS = Object.freeze({
  tokenizer: 'deepseek-v4.1-flash', budget: '', task_type: 'auto', sensitive_data: 'skip', protect_code_blocks: true,
});

export const formatInt = (n) => Number(n).toLocaleString('en-US');
export const formatPercent = (p) => `${Number(p).toFixed(1)}%`;
export const utf8Bytes = (s) => new TextEncoder().encode(s).length;
// Characters as Python's len() counts them (code points), so the UI agrees with the engine's own character stats.
export function codePointLength(s) { let n = 0; for (const _ of s) n++; return n; }

export function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function validateInput(text, bytes = utf8Bytes(text ?? '')) {
  if (typeof text !== 'string' || text.trim() === '') return { ok: false, error: 'Enter or load some text first.' };
  if (bytes > MAX_INPUT_BYTES) {
    return { ok: false, error: `Input is ${formatBytes(bytes)}; the limit is 2 MB. Shorten the text or split it into parts.` };
  }
  return { ok: true };
}

export function validateBudget(raw) {
  const s = String(raw ?? '').trim().replace(/[,_]/g, '');
  if (s === '') return { ok: true, value: null };
  if (!/^-?\d+$/.test(s)) return { ok: false, error: 'Enter a whole number, or leave it empty for no budget.' };
  const value = Number.parseInt(s, 10);
  if (value < 1) return { ok: false, error: 'The budget must be 1 or more. Leave it empty for no budget.' };
  if (value > MAX_BUDGET) return { ok: false, error: `The budget must be at most ${formatInt(MAX_BUDGET)}.` };
  return { ok: true, value };
}

export function savingsSummary(stats) {
  const pct = formatPercent(stats.saved_percent);
  if (stats.saved_tokens > 0) return { kind: 'saved', headline: `${formatInt(stats.saved_tokens)} tokens saved (${pct})` };
  if (stats.saved_tokens === 0) {
    return { kind: 'none', headline: 'No token savings: the text had nothing the cleanup rules remove.' };
  }
  return {
    kind: 'increase',
    headline: `The optimized text is ${formatInt(-stats.saved_tokens)} tokens longer (${pct}). This can happen, for example, when values are replaced by [REDACTED].`,
  };
}

export function truncationSummary(result) {
  const { stats, budget, warning } = result;
  if (budget.enforced && budget.verified_within_budget === false) {
    return { level: 'error', headline: 'The token budget was not met',
      details: [`The output re-counts to ${formatInt(budget.recount_tokens)} tokens, above the budget of ${formatInt(budget.requested)}.`, ...(warning ? [warning] : [])] };
  }
  if (stats.truncated) {
    return { level: 'warn', headline: 'Older content was removed to fit your token budget',
      details: [warning,
        `${formatInt(stats.discarded_tokens)} tokens were discarded from the start of the trimmed text; only the newest part remains.`,
        'This is truncation, not a summary: the removed content is not represented in the output.',
        `Verified by re-counting: the output is ${formatInt(budget.recount_tokens)} tokens (budget ${formatInt(budget.requested)}).`].filter(Boolean) };
  }
  if (budget.enforced) {
    return { level: 'ok', headline: 'Everything fit within your token budget',
      details: ['No content was cut by the budget. Cleanup rules may still have removed repeated or low-value text; see the diff.'] };
  }
  return { level: 'info', headline: 'No token budget set: nothing was cut by a window',
    details: ['Cleanup rules may still have removed repeated or low-value text; see the diff.'] };
}

export function sensitiveSummary(result) {
  const n = result.sensitive_findings || 0, mode = result.options.sensitive_data;
  if (!n || mode === 'off') return null;
  if (mode === 'skip') {
    return { level: 'warn', headline: `${formatInt(n)} credential-looking value(s) were found and left in the optimized text`,
      details: ['You chose "Leave untouched", so these values are still in the output and in any export.',
        'Detection is pattern-based and incomplete: other secrets may be present that were not found. Review the text before sharing it.'] };
  }
  return { level: 'info', headline: `${formatInt(n)} credential-looking value(s) were replaced with [REDACTED]`,
    details: ['Only values matching the built-in patterns are replaced. Detection is incomplete: review the text before sharing it.'] };
}

export function barWidths(original, optimized) {
  const max = Math.max(original, optimized, 1);
  return { original: (original / max) * 100, optimized: (optimized / max) * 100 };
}

export function downloadFilename(sourceName) {
  const raw = String(sourceName || '').replace(/\\/g, '/').split('/').pop().trim();
  if (!raw) return 'optimized.txt';
  const dot = raw.lastIndexOf('.');
  const stem = dot > 0 ? raw.slice(0, dot) : raw;
  const ext = dot > 0 ? raw.slice(dot) : '.txt';
  return `${stem}.optimized${ext}`;
}

// ---- session history (numbers only, never text) -------------------------------------------------
export function buildHistoryEntry(result, nowIso) {
  const s = result.stats;
  const task = result.options && result.options.task_type;
  return { at: nowIso, tokenizer: result.tokenizer.label, original_tokens: s.original_tokens, optimized_tokens: s.optimized_tokens,
    saved_tokens: s.saved_tokens, saved_percent: s.saved_percent, truncated: !!s.truncated, budget: result.budget.requested ?? null,
    task_type: task === 'coding' || task === 'document' || task === 'auto' ? task : 'auto' };
}
export function pushHistory(list, entry, limit = HISTORY_LIMIT) { return [entry, ...list].slice(0, limit); }
function stableId(prefix, parts) {
  const raw = parts.map((part) => String(part ?? '')).join('\u001f');
  let hash = 2166136261;
  for (let i = 0; i < raw.length; i++) {
    hash ^= raw.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return `${prefix}-${(hash >>> 0).toString(16)}-${raw.length}`;
}

function cleanId(value, prefix, parts) {
  if (typeof value === 'string' && /^[A-Za-z0-9_-]{6,80}$/.test(value)) return value;
  return stableId(prefix, parts);
}

export function sanitizeHistory(value) {
  if (!Array.isArray(value)) return [];
  const num = (x) => typeof x === 'number' && Number.isFinite(x);
  return value.filter((e) => e && typeof e.at === 'string' && typeof e.tokenizer === 'string' &&
    num(e.original_tokens) && num(e.optimized_tokens) && num(e.saved_tokens) && num(e.saved_percent)).slice(0, HISTORY_LIMIT)
    .map((e) => ({
      id: cleanId(e.id, 's', [e.at, e.tokenizer, e.original_tokens, e.optimized_tokens, e.saved_tokens, e.truncated]),
      at: e.at, tokenizer: e.tokenizer.slice(0, 80), original_tokens: e.original_tokens, optimized_tokens: e.optimized_tokens,
      saved_tokens: e.saved_tokens, saved_percent: e.saved_percent, truncated: !!e.truncated, budget: num(e.budget) ? e.budget : null,
      task_type: e.task_type === 'coding' || e.task_type === 'document' ? e.task_type : 'auto',
    }));
}

export function sanitizePrompts(value) {
  if (!Array.isArray(value)) return [];
  const num = (x) => typeof x === 'number' && Number.isFinite(x);
  const out = [];
  for (const e of value) {
    if (!e || typeof e.original_text !== 'string' || typeof e.optimized_text !== 'string') continue;
    if (e.original_text.length > MAX_SAVED_PROMPT_CHARS || e.optimized_text.length > MAX_SAVED_PROMPT_CHARS) continue;
    if (typeof e.at !== 'string' || !num(e.original_tokens) || !num(e.optimized_tokens) || !num(e.saved_percent)) continue;
    out.push({
      id: cleanId(e.id, 'p', [e.at, e.original_text.slice(0, 120), e.optimized_text.slice(0, 120)]),
      at: e.at,
      tokenizer: String(e.tokenizer || 'tokenizer').slice(0, 80),
      task_type: e.task_type === 'coding' || e.task_type === 'document' ? e.task_type : 'auto',
      truncated: !!e.truncated,
      source_name: typeof e.source_name === 'string' ? e.source_name.slice(0, 180) : '',
      original_tokens: e.original_tokens,
      optimized_tokens: e.optimized_tokens,
      saved_percent: e.saved_percent,
      original_text: e.original_text,
      optimized_text: e.optimized_text,
    });
    if (out.length >= PROMPT_HISTORY_LIMIT) break;
  }
  return out;
}

function dayKey(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

export function filterHistory(entries, filters = {}) {
  const query = String(filters.query || '').trim().toLowerCase();
  const truncated = filters.truncated || 'any';
  const from = /^\d{4}-\d{2}-\d{2}$/.test(String(filters.from || '')) ? filters.from : '';
  const to = /^\d{4}-\d{2}-\d{2}$/.test(String(filters.to || '')) ? filters.to : '';
  return (Array.isArray(entries) ? entries : []).filter((entry) => {
    if (truncated === 'yes' && !entry.truncated) return false;
    if (truncated === 'no' && entry.truncated) return false;
    const day = dayKey(entry.at || entry.saved_at);
    if (from && (!day || day < from)) return false;
    if (to && (!day || day > to)) return false;
    if (!query) return true;
    const haystack = [entry.tokenizer, entry.task_type, entry.source_name, entry.original_text, entry.optimized_text]
      .filter((part) => typeof part === 'string').join('\n').toLowerCase();
    return haystack.includes(query);
  });
}

export function groupByDate(entries) {
  const groups = [];
  for (const entry of entries || []) {
    const date = new Date(entry.at || entry.saved_at);
    const day = Number.isNaN(date.getTime())
      ? 'Unknown date'
      : date.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
    const last = groups[groups.length - 1];
    if (!last || last.day !== day) groups.push({ day, entries: [entry] });
    else last.entries.push(entry);
  }
  return groups;
}

export function exportBackup(history, prompts, exportedAt) {
  return {
    format: 'tritobol-history',
    version: 1,
    exported_at: exportedAt,
    statistics: sanitizeHistory(history),
    prompts: sanitizePrompts(prompts),
  };
}

export function inspectBackup(text) {
  let data;
  try { data = JSON.parse(String(text ?? '')); }
  catch { return { ok: false, error: 'That file is not valid JSON. Existing history was kept.' }; }
  if (!data || typeof data !== 'object' || Array.isArray(data) || data.format !== 'tritobol-history') {
    return { ok: false, error: 'That file is not a Tritobol history backup. Existing history was kept.' };
  }
  if (data.version !== 1) return { ok: false, error: 'This backup version is not supported. Existing history was kept.' };
  if (!Array.isArray(data.statistics) || !Array.isArray(data.prompts)) {
    return { ok: false, error: 'That backup is missing its history lists. Existing history was kept.' };
  }
  return { ok: true, exported_at: typeof data.exported_at === 'string' ? data.exported_at : '', statistics: data.statistics, prompts: data.prompts };
}

function statKey(entry) {
  return `${entry.id}|${entry.at}|${entry.tokenizer}|${entry.original_tokens}|${entry.optimized_tokens}`;
}

export function planHistoryImport(history, prompts, inspected) {
  const statsRejected = [];
  const promptsRejected = [];
  const statsNew = [];
  const promptsNew = [];
  const knownStats = new Set(sanitizeHistory(history).map(statKey));
  const knownPrompts = new Set(sanitizePrompts(prompts).map((entry) => entry.id));
  let statRoom = Math.max(0, HISTORY_LIMIT - knownStats.size);
  let promptRoom = Math.max(0, PROMPT_HISTORY_LIMIT - knownPrompts.size);
  for (const raw of inspected?.statistics || []) {
    const clean = sanitizeHistory([raw])[0];
    if (!clean) { statsRejected.push('A statistic record was skipped because it was incomplete.'); continue; }
    const key = statKey(clean);
    if (knownStats.has(key)) continue;
    if (statRoom <= 0) { statsRejected.push('A statistic record was skipped because this browser is at its statistic limit.'); continue; }
    knownStats.add(key);
    statsNew.push(clean);
    statRoom -= 1;
  }
  for (const raw of inspected?.prompts || []) {
    const clean = sanitizePrompts([raw])[0];
    if (!clean) { promptsRejected.push('A saved prompt was skipped because it was incomplete or too large.'); continue; }
    if (knownPrompts.has(clean.id)) continue;
    if (promptRoom <= 0) { promptsRejected.push('A saved prompt was skipped because this browser is at its saved-prompt limit.'); continue; }
    knownPrompts.add(clean.id);
    promptsNew.push(clean);
    promptRoom -= 1;
  }
  return { blocked: false, statsNew, promptsNew, statsRejected, promptsRejected };
}

export function importSummary(plan) {
  const stats = plan?.statsNew?.length || 0;
  const prompts = plan?.promptsNew?.length || 0;
  return `${formatInt(stats)} new statistic record(s) and ${formatInt(prompts)} new saved prompt(s) can be imported.`;
}
export function sessionTotals(history) {
  const original = history.reduce((a, e) => a + e.original_tokens, 0);
  const optimized = history.reduce((a, e) => a + e.optimized_tokens, 0);
  return { runs: history.length, original, optimized, saved: original - optimized,
    percent: original === 0 ? 0 : ((original - optimized) / original) * 100 };
}
export function sanitizeSettings(value) {
  const v = value && typeof value === 'object' ? value : {};
  const pick = (x, allowed, d) => (allowed.includes(x) ? x : d);
  return {
    tokenizer: typeof v.tokenizer === 'string' && v.tokenizer ? v.tokenizer : DEFAULT_SETTINGS.tokenizer,
    budget: validateBudget(v.budget).ok ? String(v.budget ?? '') : '',
    task_type: pick(v.task_type, ['auto', 'coding', 'document'], 'auto'),
    sensitive_data: pick(v.sensitive_data, ['skip', 'mask', 'off'], 'skip'),
    protect_code_blocks: typeof v.protect_code_blocks === 'boolean' ? v.protect_code_blocks : true,
  };
}

// ---- diff view-model ------------------------------------------------------------------------------
// Turns the backend's opcodes into rows, then collapses long unchanged runs into expandable blocks.
export function diffRows(ops) {
  const rows = [];
  for (const op of ops) {
    if (op.tag === 'equal') {
      op.a.forEach((text, i) => rows.push({ kind: 'equal', aNo: op.a_start + i, bNo: op.b_start + i, a: text, b: text }));
    } else if (op.tag === 'delete') {
      op.a.forEach((text, i) => rows.push({ kind: 'removed', aNo: op.a_start + i, a: text }));
    } else if (op.tag === 'insert') {
      op.b.forEach((text, i) => rows.push({ kind: 'added', bNo: op.b_start + i, b: text }));
    } else {
      const n = Math.min(op.a.length, op.b.length);
      for (let i = 0; i < n; i++) {
        rows.push({ kind: 'changed', aNo: op.a_start + i, bNo: op.b_start + i, a: op.a[i], b: op.b[i], words: op.words?.[i] ?? null });
      }
      for (let i = n; i < op.a.length; i++) rows.push({ kind: 'removed', aNo: op.a_start + i, a: op.a[i] });
      for (let i = n; i < op.b.length; i++) rows.push({ kind: 'added', bNo: op.b_start + i, b: op.b[i] });
    }
  }
  return rows;
}

export function diffBlocks(rows, context = 3) {
  const blocks = [];
  let i = 0;
  while (i < rows.length) {
    if (rows[i].kind !== 'equal') { blocks.push({ type: 'rows', rows: [rows[i]] }); i++; continue; }
    let j = i;
    while (j < rows.length && rows[j].kind === 'equal') j++;
    const run = rows.slice(i, j);
    const atStart = i === 0, atEnd = j === rows.length;
    const head = atStart && !atEnd ? 0 : context, tail = atEnd && !atStart ? 0 : context;
    if (run.length <= head + tail + 1) blocks.push({ type: 'rows', rows: run });
    else {
      if (head) blocks.push({ type: 'rows', rows: run.slice(0, head) });
      blocks.push({ type: 'collapsed', rows: run.slice(head, run.length - tail) });
      if (tail) blocks.push({ type: 'rows', rows: run.slice(run.length - tail) });
    }
    i = j;
  }
  return blocks;
}

export function diffViewModel(diff, context = 3) {
  if (!diff.available) return { available: false, reason: diff.reason, blocks: [] };
  if (diff.identical) return { available: true, identical: true, blocks: [], summary: diff.summary };
  return { available: true, identical: false, blocks: diffBlocks(diffRows(diff.ops), context), summary: diff.summary };
}

export function clipForDisplay(text, limit = 200_000) {
  return text.length <= limit ? { text, clipped: false, total: text.length } : { text: text.slice(0, limit), clipped: true, total: text.length };
}

// ---- password validation ----------------------------------------------------------------
export function passwordStrength(p) {
  const s = String(p || '');
  if (s.length === 0) return 'empty';
  if (s.length < 12) return 'too short';
  if (passwordIssues(s).length) return 'weak';
  return 'good';
}

export function passwordIssues(p) {
  const s = String(p || '');
  const issues = [];
  if (s.length < 12) issues.push('Use at least 12 characters.');
  if (s.length > 200) issues.push('Use 200 characters or fewer.');
  if (s && (!/[a-z]/.test(s) || !/[A-Z]/.test(s))) issues.push('Use both upper and lower case letters.');
  if (s && !/\d/.test(s)) issues.push('Use at least one number.');
  return issues;
}

export function validateRegistration({ name, email, password, confirm }) {
  const errors = { name: '', email: '', password: '', confirm: '' };
  const n = String(name || '').trim();
  const e = String(email || '').trim().toLowerCase();
  const p = String(password || '');
  const c = String(confirm || '');
  let ok = true;
  if (!n) { errors.name = 'Enter your name.'; ok = false; }
  if (!e) { errors.email = 'Enter your email.'; ok = false; }
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) { errors.email = 'Enter a valid email address.'; ok = false; }
  if (!p) { errors.password = ['Enter a password.'].join(''); ok = false; }
  else {
    const issues = passwordIssues(p);
    if (issues.length) { errors.password = issues.join(' '); ok = false; }
  }
  if (!c) { errors.confirm = 'Confirm your password.'; ok = false; }
  else if (p !== c) { errors.confirm = 'Those passwords do not match.'; ok = false; }
  return { ok, errors };
}

export function validateSignIn({ email, password }) {
  const errors = { email: '', password: '' };
  const e = String(email || '').trim().toLowerCase();
  const p = String(password || '');
  let ok = true;
  if (!e) { errors.email = 'Enter your email.'; ok = false; }
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) { errors.email = 'Enter a valid email address.'; ok = false; }
  if (!p) { errors.password = ['Enter your password.'].join(''); ok = false; }
  return { ok, errors };
}
