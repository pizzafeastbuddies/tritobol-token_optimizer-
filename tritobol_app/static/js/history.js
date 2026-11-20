import { $, clear, h } from './dom.js';
import { loadDraft } from './editor.js';
import {
  HISTORY_LIMIT, PROMPT_HISTORY_LIMIT, exportBackup, filterHistory, formatBytes, formatInt, formatPercent, groupByDate, importSummary, inspectBackup, planHistoryImport, utf8Bytes,
} from './lib.js';
import { applyImport, removeHistoryEntry, state } from './store.js';

let pending = null;

function say(msg, ok) {
  const el = $('history-status');
  el.textContent = msg;
  el.className = ok ? 'ok-text' : 'err-text';
}

function readFile(file) {
  if (typeof file.text === 'function') return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('That file could not be read. Existing history was kept.'));
    reader.readAsText(file);
  });
}

function download(filename, text) {
  const blob = new Blob([text], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = h('a', { href: url, download: filename });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function filters() {
  return {
    query: $('history-search').value,
    truncated: $('history-truncated').value,
    from: $('history-from').value,
    to: $('history-to').value,
  };
}

function entryLine(e, kind) {
  const when = new Date(e.at || e.saved_at).toLocaleString();
  const title = `${formatInt(e.original_tokens)} → ${formatInt(e.optimized_tokens)} tokens (${formatPercent(e.saved_percent)})`;
  const meta = [e.tokenizer, e.task_type, e.truncated ? 'budget cut' : 'no budget cut', e.source_name || (kind === 'prompt' ? 'saved prompt' : 'statistics only')].filter(Boolean).join(' · ');
  const row = h('article', { class: 'history-item' },
    h('div', {}, h('strong', {}, title), h('p', { class: 'muted' }, `${when} · ${meta}`)),
  );
  const actions = h('div', { class: 'toolbar-actions' });
  if (kind === 'prompt') {
    const open = h('button', { type: 'button', class: 'btn btn-small' }, 'Reopen');
    open.addEventListener('click', () => loadDraft(e.original_text, e.source_name || null));
    const copy = h('button', { type: 'button', class: 'btn btn-small btn-quiet' }, 'Copy optimized');
    copy.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(e.optimized_text); say('Optimized text copied. It stays on this computer.', true); }
      catch { say('Copy was blocked by the browser.', false); }
    });
    actions.append(open, copy);
  }
  const del = h('button', { type: 'button', class: 'btn btn-small btn-quiet' }, 'Remove');
  del.addEventListener('click', () => {
    const result = removeHistoryEntry(kind === 'prompt' ? 'prompt' : 'stat', e.id);
    if (!result.ok) say(result.error, false);
    else { say('That entry was removed. Other history was kept.', true); renderHistory(); }
  });
  actions.append(del);
  row.append(actions);
  return row;
}

function renderGroups(entries, kind) {
  if (!entries.length) return [h('p', { class: 'muted' }, kind === 'prompt' ? 'No saved prompts match these filters.' : 'No statistic records match these filters.')];
  return groupByDate(entries).map((g) => h('section', { class: 'history-day' },
    h('h3', {}, g.day), ...g.entries.map((e) => entryLine(e, kind))));
}

export function renderHistory() {
  const list = $('history-list');
  if (!list) return;
  const f = filters();
  const stats = filterHistory(state.history, f);
  const prompts = filterHistory(state.prompts, f);
  const bytes = utf8Bytes(JSON.stringify(state.history)) + utf8Bytes(JSON.stringify(state.prompts));
  $('history-usage').textContent = `${formatInt(state.history.length)} of ${HISTORY_LIMIT} statistic runs and ${formatInt(state.prompts.length)} of ${PROMPT_HISTORY_LIMIT} saved prompts use about ${formatBytes(bytes)} in this browser.`;
  const empty = !state.history.length && !state.prompts.length;
  $('history-empty').hidden = !empty;
  list.hidden = empty;
  clear(list);
  if (empty) return;
  list.append(
    h('section', {}, h('h2', {}, 'Saved prompts'), h('p', { class: 'hint' }, 'Text is listed here only after you confirm a save. Reopen puts the original back in the optimizer.')),
    ...renderGroups(prompts, 'prompt'),
    h('section', {}, h('h2', {}, 'Run statistics'), h('p', { class: 'hint' }, 'Every optimization adds a row of counts. The prompt itself is not stored in these rows.')),
    ...renderGroups(stats, 'stat'),
  );
}

function showPreview(plan) {
  pending = plan;
  const box = $('history-preview');
  box.hidden = false;
  const lines = [importSummary(plan), ...plan.statsRejected, ...plan.promptsRejected].slice(0, 8);
  clear(box).append(
    h('h3', {}, 'Import preview'),
    h('ul', {}, lines.map((line) => h('li', {}, line))),
    h('p', { class: 'hint' }, 'Nothing is written until you confirm. Existing records are kept, and duplicates are skipped.'),
  );
  const canApply = !plan.blocked && (plan.statsNew.length + plan.promptsNew.length > 0);
  $('btn-import-confirm').hidden = !canApply;
  $('btn-import-cancel').hidden = false;
}

export function initHistory() {
  $('btn-history-export').addEventListener('click', () => {
    const backup = exportBackup(state.history, state.prompts, new Date().toISOString());
    download(`tritobol-history-${backup.exported_at.slice(0, 10)}.json`, JSON.stringify(backup, null, 2));
    say('Backup download started. It contains statistics and any prompts you chose to save.', true);
  });
  $('history-file').addEventListener('change', async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    pending = null;
    $('history-preview').hidden = true;
    $('btn-import-confirm').hidden = true;
    $('btn-import-cancel').hidden = true;
    if (!file) return;
    try {
      const inspected = inspectBackup(await readFile(file));
      if (!inspected.ok) { say(inspected.error, false); return; }
      showPreview(planHistoryImport(state.history, state.prompts, inspected));
      say('Review the preview, then confirm the import. Nothing has been written yet.', true);
    } catch (err) {
      say(err.message || 'That file could not be read. Existing history was kept.', false);
    }
  });
  $('btn-import-confirm').addEventListener('click', () => {
    if (!pending) return;
    const before = state.history.slice();
    const result = applyImport(pending);
    pending = null;
    $('history-preview').hidden = true;
    $('btn-import-confirm').hidden = true;
    $('btn-import-cancel').hidden = true;
    if (!result.ok) { say(result.error, false); return; }
    if (result.unchanged) { say('Nothing new was imported. Existing history was kept.', true); return; }
    say(`Imported ${result.addedStats} statistic record(s) and ${result.addedPrompts} saved prompt(s). Duplicates were skipped and previous records were kept.`, true);
    if (state.history.length < before.length) say('Import finished, but fewer statistic rows are stored than before. Check the storage limit.', false);
    renderHistory();
  });
  $('btn-import-cancel').addEventListener('click', () => {
    pending = null;
    $('history-preview').hidden = true;
    $('btn-import-confirm').hidden = true;
    $('btn-import-cancel').hidden = true;
    say('Import cancelled. Existing history was kept.', true);
  });
  ['history-search', 'history-truncated', 'history-from', 'history-to'].forEach((id) => {
    $(id).addEventListener('input', renderHistory);
    $(id).addEventListener('change', renderHistory);
  });
}
