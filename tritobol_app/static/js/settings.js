import { $, clear, h } from './dom.js';
import { validateBudget } from './lib.js';
import { clearHistory, resetSettings, saveSettings, state } from './store.js';

const say = (msg, ok = true) => { const el = $('set-status'); el.textContent = msg; el.className = ok ? 'ok-text' : 'err-text'; };

export function renderSettings() {
  const s = state.settings, sel = clear($('set-tokenizer'));
  state.tokenizers.forEach((t) => sel.append(h('option', { value: t.id, disabled: !t.available }, t.available ? t.label : `${t.label} — unavailable`)));
  if ([...sel.options].some((o) => o.value === s.tokenizer)) sel.value = s.tokenizer;
  $('set-budget').value = s.budget; $('set-task').value = s.task_type; $('set-sensitive').value = s.sensitive_data; $('set-protect').checked = s.protect_code_blocks;
}

export function initSettings(onChange) {
  $('btn-save-settings').addEventListener('click', () => {
    const b = validateBudget($('set-budget').value), err = $('set-budget-error');
    err.hidden = b.ok; err.textContent = b.ok ? '' : b.error;
    if (!b.ok) { say('Settings not saved: fix the budget first.', false); return; }
    saveSettings({ tokenizer: $('set-tokenizer').value, budget: b.value == null ? '' : String(b.value), task_type: $('set-task').value,
      sensitive_data: $('set-sensitive').value, protect_code_blocks: $('set-protect').checked });
    say('Settings saved in this browser.'); onChange();
  });
  $('btn-reset-settings').addEventListener('click', () => { resetSettings(); renderSettings(); say('Settings reset to defaults.'); onChange(); });
  $('btn-clear-history').addEventListener('click', () => { clearHistory(); say('Run history erased.'); onChange(); });
}
