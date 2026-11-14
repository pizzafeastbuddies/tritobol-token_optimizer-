// Pure helpers: no DOM, no network. Everything here is unit-tested with `node --test frontend_tests`.

export const MAX_INPUT_BYTES = 2 * 1024 * 1024;
export const MAX_BUDGET = 100_000_000;
export const HISTORY_LIMIT = 10;
export const PROMPT_HISTORY_VERSION = 1;
export const PROMPT_HISTORY_LIMIT = 10;
export const PROMPT_HISTORY_MAX_TEXT_CHARS = 50_000;
export const PROMPT_HISTORY_MAX_STORAGE_CHARS = 1_000_000;
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
      details: ['You chose “Leave untouched”, so these values are still in the output and in any export.',
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

// ---- automatic numeric run history; prompt text has a separate explicit opt-in store ------------
export function buildHistoryEntry(result, nowIso) {
  const s = result.stats;
  return { at: nowIso, tokenizer: result.tokenizer.label, original_tokens: s.original_tokens, optimized_tokens: s.optimized_tokens,
    saved_tokens: s.saved_tokens, saved_percent: s.saved_percent, truncated: !!s.truncated, budget: result.budget.requested ?? null };
}
export function pushHistory(list, entry, limit = HISTORY_LIMIT) { return [entry, ...list].slice(0, limit); }
export function sanitizeHistory(value) {
  if (!Array.isArray(value)) return [];
  const num = (x) => typeof x === 'number' && Number.isFinite(x);
  return value.filter((e) => e && typeof e.at === 'string' && typeof e.tokenizer === 'string' &&
    num(e.original_tokens) && num(e.optimized_tokens) && num(e.saved_tokens) && num(e.saved_percent)).slice(0, HISTORY_LIMIT)
    .map((e) => ({ at: e.at, tokenizer: e.tokenizer.slice(0, 80), original_tokens: e.original_tokens, optimized_tokens: e.optimized_tokens,
      saved_tokens: e.saved_tokens, saved_percent: e.saved_percent, truncated: !!e.truncated, budget: num(e.budget) ? e.budget : null }));
}

function validPromptHistoryEntry(entry) {
  const isInt = (value) => Number.isSafeInteger(value);
  const validBudget = entry?.budget === null || (isInt(entry?.budget) && entry.budget >= 1);
  return entry && typeof entry === 'object' && !Array.isArray(entry) &&
    typeof entry.id === 'string' && entry.id.length > 0 && entry.id.length <= 100 &&
    typeof entry.at === 'string' && Number.isFinite(Date.parse(entry.at)) &&
    typeof entry.source_name === 'string' && entry.source_name.length <= 256 &&
    typeof entry.original_text === 'string' && typeof entry.optimized_text === 'string' &&
    codePointLength(entry.original_text) + codePointLength(entry.optimized_text) <= PROMPT_HISTORY_MAX_TEXT_CHARS &&
    typeof entry.tokenizer === 'string' && entry.tokenizer.length > 0 && entry.tokenizer.length <= 100 &&
    isInt(entry.original_tokens) && entry.original_tokens >= 0 &&
    isInt(entry.optimized_tokens) && entry.optimized_tokens >= 0 &&
    isInt(entry.saved_tokens) &&
    typeof entry.saved_percent === 'number' && Number.isFinite(entry.saved_percent) &&
    typeof entry.truncated === 'boolean' &&
    isInt(entry.discarded_tokens) && entry.discarded_tokens >= 0 &&
    validBudget &&
    (entry.warning === null || (typeof entry.warning === 'string' && entry.warning.length <= 2000));
}

export function buildPromptHistoryEntry(result, sourceText, sourceName, at, id) {
  const stats = result?.stats;
  const entry = {
    id,
    at,
    source_name: String(sourceName || 'Pasted text').slice(0, 256),
    original_text: sourceText,
    optimized_text: result?.text,
    tokenizer: result?.tokenizer?.label,
    original_tokens: stats?.original_tokens,
    optimized_tokens: stats?.optimized_tokens,
    saved_tokens: stats?.saved_tokens,
    saved_percent: stats?.saved_percent,
    truncated: !!stats?.truncated,
    discarded_tokens: stats?.discarded_tokens,
    budget: result?.budget?.requested ?? null,
    warning: result?.warning ?? null,
  };
  if (!validPromptHistoryEntry(entry)) {
    throw new RangeError(`Saved prompt history requires a complete result with at most ${formatInt(PROMPT_HISTORY_MAX_TEXT_CHARS)} combined text characters.`);
  }
  return entry;
}

export function sanitizePromptHistory(value) {
  if (value === null || value === undefined) return { ok: true, entries: [] };
  if (!value || typeof value !== 'object' || Array.isArray(value) || value.version !== PROMPT_HISTORY_VERSION) {
    return { ok: false, entries: [], error: 'Saved prompt history has an unsupported version or format. Clear it to start a new history.' };
  }
  if (!Array.isArray(value.entries)) {
    return { ok: false, entries: [], error: 'Saved prompt history is damaged. Clear it to start a new history.' };
  }
  const entries = value.entries.slice(0, PROMPT_HISTORY_LIMIT);
  if (entries.some((entry) => !validPromptHistoryEntry(entry))) {
    return { ok: false, entries: [], error: 'Saved prompt history contains invalid data. Clear it to start a new history.' };
  }
  return { ok: true, entries };
}

export function parsePromptHistory(raw) {
  if (raw === null || raw === undefined) return { ok: true, entries: [] };
  if (typeof raw !== 'string' || raw.length > PROMPT_HISTORY_MAX_STORAGE_CHARS) {
    return { ok: false, entries: [], error: 'Saved prompt history is too large or unreadable. Clear it to start a new history.' };
  }
  try {
    return sanitizePromptHistory(JSON.parse(raw));
  } catch {
    return { ok: false, entries: [], error: 'Saved prompt history is unreadable. Clear it to start a new history.' };
  }
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
