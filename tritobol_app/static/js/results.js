import { api } from './api.js';
import { $, clear, h } from './dom.js';
import { renderDiff } from './diffview.js';
import {
  clipForDisplay, codePointLength, downloadFilename, formatInt, formatPercent, savingsSummary, sensitiveSummary, truncationSummary,
} from './lib.js';
import { savePromptToHistory, state } from './store.js';

const TABS = ['compare', 'diff', 'details'];
let shown = null;

function banner(summary) {
  const cls = { warn: 'banner-warn', ok: 'banner-ok', info: 'banner-info', error: 'banner-error' }[summary.level];
  return h('div', { class: `banner ${cls}`, role: summary.level === 'warn' || summary.level === 'error' ? 'alert' : 'status' },
    h('h3', {}, summary.headline), h('ul', {}, summary.details.map((d) => h('li', {}, d))));
}

function tiles(result) {
  const s = result.stats, sv = savingsSummary(s);
  const tile = (label, value, sub, accent) => h('div', { class: `tile${accent ? ' tile-accent' : ''}` },
    h('span', { class: 'label' }, label), h('span', { class: 'value' }, value), sub ? h('span', { class: 'sub' }, sub) : null);
  return [
    tile('Original tokens', formatInt(s.original_tokens), `${formatInt(s.original_chars)} characters`),
    tile('Optimized tokens', formatInt(s.optimized_tokens), `${formatInt(s.optimized_chars)} characters`),
    tile(s.saved_tokens < 0 ? 'Tokens added' : 'Tokens saved', formatInt(Math.abs(s.saved_tokens)), sv.kind === 'increase' ? 'output is longer' : null),
    tile('Reduction', formatPercent(s.saved_percent), s.original_tokens === 0 ? 'empty input' : sv.kind === 'none' ? 'no change in tokens' : null, true),
  ];
}

function pane(title, text, tokens) {
  const wrap = h('section', { class: 'pane' });
  const view = clipForDisplay(text);
  const pre = h('pre', { tabindex: '0', 'aria-label': `${title} text` });
  if (text === '') pre.append(h('span', { class: 'empty-note' }, '(empty)'));
  else pre.append(view.text);
  wrap.append(h('h3', {}, title, h('span', {}, `${formatInt(tokens)} tokens · ${formatInt(codePointLength(text))} chars`)), pre);
  if (view.clipped) {
    const btn = h('button', { type: 'button', class: 'btn btn-small' }, `Showing the first ${formatInt(view.text.length)} of ${formatInt(view.total)} characters — show all`);
    btn.addEventListener('click', () => { pre.textContent = text; btn.remove(); });
    wrap.append(btn);
  }
  return wrap;
}

function details(result) {
  const s = result.stats;
  const root = h('div', { class: 'analytics-grid' });
  const kv = (rows) => h('dl', { class: 'stat-list' }, rows.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)]));
  root.append(
    h('div', { class: 'card' }, h('h3', {}, 'What the cleanup removed'), kv([
      ['Repeated paragraphs', formatInt(s.removed_paragraphs)], ['Repeated lines', formatInt(s.removed_lines)],
      ['Repeated sentences', formatInt(s.removed_sentences)], ['Separator lines', formatInt(s.removed_separators)],
      ['Characters removed', formatInt(s.removed_chars)], ['Tokens discarded by budget', formatInt(s.discarded_tokens)]])),
    h('div', { class: 'card' }, h('h3', {}, 'Run settings'), kv([
      ['Tokenizer', result.tokenizer.label], ['Token budget', result.budget.requested == null ? 'none' : formatInt(result.budget.requested)],
      ['Strategy', result.options.task_type], ['Credential values', result.options.sensitive_data],
      ['Protect code blocks', result.options.protect_code_blocks ? 'yes' : 'no'], ['Engine version', result.engine_version], ['Time', `${formatInt(result.elapsed_ms)} ms`]])));
  if (result.notes.length) root.append(h('div', { class: 'card' }, h('h3', {}, 'Notes'), h('ul', {}, result.notes.map((n) => h('li', {}, n)))));
  const segs = h('div', { class: 'card' }, h('h3', {}, 'Segments'));
  if (result.sensitive_findings) segs.append(h('p', { class: 'hint' }, `${result.sensitive_findings} credential-looking value(s) matched a pattern (values are never shown). Detection is pattern-based and incomplete.`));
  segs.append(h('div', { class: 'table-wrap' }, h('table', {},
    h('thead', {}, h('tr', {}, h('th', {}, 'Kind'), h('th', {}, 'Status'), h('th', {}, 'Detail'), h('th', { class: 'num' }, 'Tokens'))),
    h('tbody', {}, result.segments.map((g) => h('tr', {}, h('td', {}, g.kind + (g.provider ? ` (${g.provider})` : '')), h('td', {}, g.status), h('td', {}, g.detail),
      h('td', { class: 'num' }, `${formatInt(g.original_tokens)} → ${formatInt(g.optimized_tokens)}`)))))));
  root.append(segs);
  return root;
}

export function selectTab(name) {
  TABS.forEach((t) => {
    const on = t === name;
    $(`tab-${t}`).setAttribute('aria-selected', String(on));
    $(`tab-${t}`).tabIndex = on ? 0 : -1;
    $(`panel-${t}`).hidden = !on;
  });
}

export function renderResult(result, sourceText, sourceName) {
  shown = { result, sourceText };
  const root = $('results');
  root.hidden = false;
  const banners = clear($('result-banner'));
  banners.append(banner(truncationSummary(result)));
  const sens = sensitiveSummary(result);
  if (sens) banners.append(banner(sens));
  clear($('result-tiles')).append(...tiles(result));
  clear($('panel-compare')).append(h('div', { class: 'compare' }, pane('Original', sourceText, result.stats.original_tokens), pane('Optimized', result.text, result.stats.optimized_tokens)));
  renderDiff($('panel-diff'), result.diff);
  clear($('panel-details')).append(details(result));
  $('export-name').value = downloadFilename(sourceName);
  clear($('export-status'));
  $('history-save-consent').checked = false;
  $('history-save-confirm').disabled = true;
  $('history-save-confirmation').hidden = true;
  $('history-save-status').textContent = state.promptHistoryError
    ? 'Saved prompt history is unavailable. Open Prompt history to review or clear its stored data.'
    : '';
  $('history-save-status').className = state.promptHistoryError ? 'err-text' : 'muted';
  $('btn-save-history').disabled = false;
  $('btn-save-history').textContent = 'Save to history';
  selectTab('compare');
}

function status(msg, ok) { const el = $('export-status'); el.textContent = msg; el.className = ok ? 'ok-text' : 'err-text'; }

export function initResults() {
  $('btn-save-history').addEventListener('click', () => {
    if (!shown) return;
    if (state.promptHistoryError) {
      $('history-save-status').textContent = `${state.promptHistoryError} Open Prompt history to clear it before saving.`;
      $('history-save-status').className = 'err-text';
      return;
    }
    if (state.currentPromptHistoryId) {
      $('history-save-status').textContent = 'This result is already saved in Prompt history.';
      $('history-save-status').className = 'ok-text';
      return;
    }
    $('history-save-confirmation').hidden = false;
    $('history-save-consent').checked = false;
    $('history-save-confirm').disabled = true;
    $('history-save-consent').focus();
  });
  $('history-save-consent').addEventListener('change', () => {
    $('history-save-confirm').disabled = !$('history-save-consent').checked;
  });
  $('history-save-cancel').addEventListener('click', () => {
    $('history-save-confirmation').hidden = true;
    $('history-save-consent').checked = false;
    $('history-save-status').textContent = 'Nothing was saved.';
    $('history-save-status').className = 'muted';
    $('btn-save-history').focus();
  });
  $('history-save-confirm').addEventListener('click', () => {
    if (!$('history-save-consent').checked) return;
    const outcome = savePromptToHistory();
    $('history-save-status').textContent = outcome.ok
      ? 'Saved on this browser. It is not synced to other devices.'
      : outcome.error;
    $('history-save-status').className = outcome.ok ? 'ok-text' : 'err-text';
    if (outcome.ok) {
      $('history-save-confirmation').hidden = true;
      $('btn-save-history').textContent = 'Saved to history';
    }
  });
  TABS.forEach((t, i) => {
    $(`tab-${t}`).addEventListener('click', () => selectTab(t));
    $(`tab-${t}`).addEventListener('keydown', (e) => {
      const next = e.key === 'ArrowRight' ? (i + 1) % TABS.length : e.key === 'ArrowLeft' ? (i + TABS.length - 1) % TABS.length : null;
      if (next !== null) { e.preventDefault(); selectTab(TABS[next]); $(`tab-${TABS[next]}`).focus(); }
    });
  });
  $('btn-download').addEventListener('click', () => {
    if (!shown) return;
    const blob = new Blob([shown.result.text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = h('a', { href: url, download: $('export-name').value.trim() || 'optimized.txt' });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status('Download started. Your browser saves it as a new file; the original is untouched.', true);
  });
  $('btn-save-copy').addEventListener('click', async () => {
    if (!shown) return;
    const btn = $('btn-save-copy'); btn.disabled = true;
    try {
      const { export: saved } = await api.exportText({ text: shown.result.text, filename: $('export-name').value, directory: $('export-dir').value });
      status(`Saved a new file: ${saved.path}${saved.renamed ? ' (the name already existed, so a numbered name was used)' : ''}`, true);
    } catch (err) { status(`Export failed: ${err.message}`, false); } finally { btn.disabled = false; }
  });
  $('btn-copy').addEventListener('click', async () => {
    if (!shown) return;
    try { await navigator.clipboard.writeText(shown.result.text); status('Optimized text copied to the clipboard.', true); }
    catch { status('Copy was blocked by the browser. Use Download instead.', false); }
  });
}
export const _state = state;
