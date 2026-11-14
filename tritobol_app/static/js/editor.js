import { api, ApiError } from './api.js';
import { $, clear, h } from './dom.js';
import { MAX_INPUT_BYTES, formatBytes, formatInt, utf8Bytes, validateBudget, validateInput } from './lib.js';
import { renderResult } from './results.js';
import { setResult, state } from './store.js';

let controller = null, timer = null, loadedName = null;

function setError(id, message, inputId) {
  const el = $(id);
  el.hidden = !message; el.textContent = message || '';
  if (inputId) { if (message) $(inputId).setAttribute('aria-invalid', 'true'); else $(inputId).removeAttribute('aria-invalid'); }
}

export function updateCounts() {
  const text = $('input-text').value, bytes = utf8Bytes(text);
  $('char-count').textContent = `${formatInt([...text].length)} characters`;
  const meter = $('size-meter');
  meter.textContent = `${formatBytes(bytes)} of 2 MB`;
  meter.classList.toggle('meter-over', bytes > MAX_INPUT_BYTES);
  if (bytes > MAX_INPUT_BYTES) setError('input-error', `Input is ${formatBytes(bytes)}; the limit is 2 MB. Shorten the text or split it into parts.`, 'input-text');
  else if ($('input-error').textContent.startsWith('Input is')) setError('input-error', '', 'input-text');
}

export function populateTokenizers() {
  const sel = $('opt-tokenizer'), previous = sel.value || state.settings.tokenizer;
  clear(sel);
  state.tokenizers.forEach((t) => sel.append(h('option', { value: t.id, disabled: !t.available }, t.available ? t.label : `${t.label} — unavailable`)));
  const usable = state.tokenizers.find((t) => t.id === previous && t.available) || state.tokenizers.find((t) => t.available);
  if (usable) sel.value = usable.id;
  showTokenizerStatus();
}

function showTokenizerStatus() {
  const t = state.tokenizers.find((x) => x.id === $('opt-tokenizer').value);
  const el = $('tok-status');
  el.className = 'hint';
  if (!state.tokenizers.length) el.textContent = 'Loading tokenizers…';
  else if (!t) { el.className = 'field-error'; el.textContent = 'No usable tokenizer. ' + (state.tokenizers[0]?.error || ''); }
  else el.textContent = `Active: ${t.label}${t.vocab_size ? ` · vocabulary ${formatInt(t.vocab_size)}` : ''}. Counts exclude chat templates and API overhead.`;
}

export function applySettingsToForm() {
  const s = state.settings;
  $('opt-budget').value = s.budget; $('opt-task').value = s.task_type; $('opt-sensitive').value = s.sensitive_data; $('opt-protect').checked = s.protect_code_blocks;
  populateTokenizers();
}

async function loadFile(file) {
  setError('input-error', '');
  $('file-info').hidden = true;
  try {
    const res = await api.loadFile(file);
    $('input-text').value = res.text; loadedName = res.filename;
    $('file-info').hidden = false;
    $('file-info').textContent = `Loaded ${res.filename} (${formatBytes(res.bytes)}, ${formatInt(res.chars)} characters). The file on disk is never modified.`;
    updateCounts();
  } catch (err) {
    setError('input-error', err.message, 'input-text'); // editor content is left exactly as it was
  }
}

async function uploadTokenizer(file) {
  const el = $('tok-status'); el.className = 'hint'; el.textContent = `Validating ${file.name}…`;
  try {
    const res = await api.uploadTokenizer(file);
    state.tokenizers = res.tokenizers; populateTokenizers(); $('opt-tokenizer').value = res.tokenizer.id; showTokenizerStatus();
    el.textContent = `Loaded “${res.tokenizer.label}”. It is kept in memory only until the app stops. ` + el.textContent;
  } catch (err) { el.className = 'field-error'; el.textContent = `Tokenizer not loaded: ${err.message}`; }
}

function setBusy(busy) {
  state.busy = busy;
  const b = $('btn-optimize'); b.disabled = busy; b.classList.toggle('busy', busy); b.textContent = busy ? 'Optimizing…' : 'Optimize';
  $('btn-cancel').hidden = !busy;
}

export async function runOptimize() {
  if (state.busy) return;
  const text = $('input-text').value; // sent exactly as typed; never modified client-side
  const input = validateInput(text), budget = validateBudget($('opt-budget').value);
  setError('input-error', input.ok ? '' : input.error, 'input-text'); setError('budget-error', budget.ok ? '' : budget.error, 'opt-budget');
  $('run-status').textContent = ''; $('run-status').className = 'muted';
  if (!input.ok) { $('input-text').focus(); return; }
  if (!budget.ok) { $('opt-budget').focus(); return; }
  controller = new AbortController();
  setBusy(true);
  const started = Date.now();
  timer = setInterval(() => { $('run-status').textContent = `Optimizing… ${((Date.now() - started) / 1000).toFixed(0)} s (large inputs can take several seconds)`; }, 500);
  $('run-status').textContent = 'Optimizing…';
  try {
    const { result } = await api.optimize({
      text, tokenizer: $('opt-tokenizer').value, max_tokens: budget.value, task_type: $('opt-task').value,
      sensitive_data: $('opt-sensitive').value, protect_code_blocks: $('opt-protect').checked,
    }, controller.signal);
    setResult(result, text, loadedName);
    renderResult(result, text, loadedName);
    $('run-status').textContent = `Done in ${formatInt(result.elapsed_ms)} ms.`;
    $('h-res').tabIndex = -1; $('h-res').focus({ preventScroll: true }); $('results').scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  } catch (err) {
    const e = err instanceof ApiError ? err : new ApiError('unexpected', `Unexpected error: ${err.message}`);
    if (e.code === 'cancelled') $('run-status').textContent = 'Cancelled. Your text is unchanged.';
    else if (e.field === 'max_tokens') setError('budget-error', e.message, 'opt-budget');
    else if (e.field === 'text') setError('input-error', e.message, 'input-text');
    else { $('run-status').className = 'err-text'; $('run-status').textContent = e.message; }
  } finally { clearInterval(timer); setBusy(false); controller = null; }
}

export function initEditor() {
  const ta = $('input-text');
  ta.addEventListener('input', () => { setError('input-error', ''); ta.removeAttribute('aria-invalid'); updateCounts(); });
  $('btn-load').addEventListener('click', () => $('file-input').click());
  $('file-input').addEventListener('change', async (e) => { const f = e.target.files[0]; e.target.value = ''; if (f) await loadFile(f); });
  $('btn-clear').addEventListener('click', () => { ta.value = ''; loadedName = null; $('file-info').hidden = true; setError('input-error', ''); updateCounts(); ta.focus(); });
  $('btn-tok-upload').addEventListener('click', () => $('tok-file').click());
  $('tok-file').addEventListener('change', async (e) => { const f = e.target.files[0]; e.target.value = ''; if (f) await uploadTokenizer(f); });
  $('opt-tokenizer').addEventListener('change', showTokenizerStatus);
  $('opt-budget').addEventListener('input', () => { const v = validateBudget($('opt-budget').value); setError('budget-error', v.ok ? '' : v.error, 'opt-budget'); });
  $('btn-optimize').addEventListener('click', runOptimize);
  $('btn-cancel').addEventListener('click', () => controller?.abort());
  ta.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); runOptimize(); } });
  updateCounts();
}
