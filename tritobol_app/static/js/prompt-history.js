import { $, clear, h } from './dom.js';
import {
  formatInt, formatPercent, PROMPT_HISTORY_LIMIT, PROMPT_HISTORY_MAX_STORAGE_CHARS, PROMPT_HISTORY_MAX_TEXT_CHARS,
} from './lib.js';
import { openHistoryPrompt } from './editor.js';
import { clearPromptHistory, deletePromptFromHistory, state } from './store.js';

let operationMessage = '';
let operationIsError = false;

function renderEntry(entry) {
  const review = h('details', { class: 'prompt-history-review' },
    h('summary', {}, 'Review original and optimized text'),
    h('div', { class: 'prompt-history-texts' },
      h('section', {}, h('h4', {}, 'Original prompt'), h('pre', {}, entry.original_text)),
      h('section', {}, h('h4', {}, 'Optimized result'), h('pre', {}, entry.optimized_text))));
  const actions = h('div', { class: 'actions' });
  const open = h('button', { type: 'button', class: 'btn btn-small' }, 'Open original in optimizer');
  open.addEventListener('click', () => {
    openHistoryPrompt(entry.original_text);
    location.hash = '#/optimize';
  });
  const copy = h('button', { type: 'button', class: 'btn btn-small btn-quiet' }, 'Copy optimized text');
  copy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(entry.optimized_text);
      operationMessage = 'Optimized text copied to the clipboard.';
      operationIsError = false;
    } catch {
      operationMessage = 'Copy was blocked by the browser. Open the review and select the optimized text to copy it manually.';
      operationIsError = true;
    }
    renderPromptHistory();
  });
  const remove = h('button', { type: 'button', class: 'btn btn-small btn-quiet' }, 'Delete');
  remove.addEventListener('click', () => {
    if (!window.confirm('Delete this saved prompt and result from this browser?')) return;
    const outcome = deletePromptFromHistory(entry.id);
    operationMessage = outcome.ok ? state.promptHistoryMessage : outcome.error;
    operationIsError = !outcome.ok;
    renderPromptHistory();
  });
  actions.append(open, copy, remove);
  return h('article', { class: 'card prompt-history-card' },
    h('div', { class: 'prompt-history-heading' },
      h('div', {}, h('h3', {}, entry.source_name || 'Pasted text'), h('p', { class: 'muted' }, new Date(entry.at).toLocaleString())),
      h('span', { class: 'prompt-history-badge' }, entry.truncated ? 'Budget cut' : 'Saved result')),
    h('p', { class: 'prompt-history-stats' },
      `${entry.tokenizer} · ${formatInt(entry.original_tokens)} → ${formatInt(entry.optimized_tokens)} tokens · ${formatInt(entry.saved_tokens)} saved (${formatPercent(entry.saved_percent)})`),
    entry.truncated ? h('p', { class: 'hint' }, `${formatInt(entry.discarded_tokens)} tokens were discarded from the start. The saved result is truncated, not a summary.`) : null,
    review, actions);
}

export function renderPromptHistory() {
  const root = clear($('prompt-history-list'));
  const alert = $('prompt-history-error');
  alert.hidden = !state.promptHistoryError;
  alert.textContent = state.promptHistoryError || '';
  $('prompt-history-status').textContent = operationMessage || state.promptHistoryMessage || '';
  $('prompt-history-status').className = operationIsError ? 'err-text' : 'ok-text';
  $('btn-clear-prompt-history').disabled = !state.promptHistory.length && !state.promptHistoryError;

  if (state.promptHistoryError) {
    root.append(h('p', { class: 'muted' }, 'Saved prompt entries are not shown because their stored format could not be safely read.'));
  } else if (!state.promptHistory.length) {
    root.append(h('div', { class: 'card empty' },
      h('p', {}, 'No prompts saved yet.'),
      h('p', { class: 'muted' }, 'After a successful optimization, choose “Save to history” if you want to keep both texts in this browser. Nothing is saved automatically.')));
  } else {
    root.append(...state.promptHistory.map(renderEntry));
  }
}

export function initPromptHistory() {
  $('btn-clear-prompt-history').addEventListener('click', () => {
    if (!window.confirm('Clear all saved prompt text and results from this browser? This cannot be undone.')) return;
    const outcome = clearPromptHistory();
    operationMessage = outcome.ok ? state.promptHistoryMessage : outcome.error;
    operationIsError = !outcome.ok;
    renderPromptHistory();
  });
  $('prompt-history-limit').textContent =
    `Up to ${PROMPT_HISTORY_LIMIT} entries; each original + optimized text pair is limited to ${formatInt(PROMPT_HISTORY_MAX_TEXT_CHARS)} characters. Stored history is capped at ${formatInt(PROMPT_HISTORY_MAX_STORAGE_CHARS)} characters; your browser may impose a smaller quota. Saving a new entry removes the oldest entry when the limit is reached.`;
  renderPromptHistory();
}
