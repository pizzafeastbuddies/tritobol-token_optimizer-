import { $, clear, h } from './dom.js';
import { formatInt, formatPercent, sessionTotals } from './lib.js';
import { state } from './store.js';

export function renderDashboard() {
  const hist = state.history, latest = hist[0], t = sessionTotals(hist);
  clear($('dash-hero-stat')).append(latest
    ? [h('span', { class: 'lantern-value' }, formatPercent(Math.abs(latest.saved_percent))), h('span', { class: 'lantern-label' }, `${latest.saved_percent < 0 ? 'more' : 'fewer'} tokens in the latest run`)]
    : h('span', { class: 'lantern-label' }, 'No run yet — nothing to show'));
  const eng = clear($('dash-engine')), tok = state.tokenizers[0];
  if (!tok) eng.append(h('p', { class: 'muted' }, 'Checking tokenizer…'));
  else eng.append(tok.available
    ? h('p', {}, `${tok.label} is ready (vocabulary ${formatInt(tok.vocab_size)}). Bring your own tokenizer.json in the optimizer.`)
    : h('p', { class: 'err-text' }, `The bundled tokenizer is unavailable: ${tok.error}`));
  const ses = clear($('dash-session'));
  if (!hist.length) ses.append(h('p', { class: 'muted' }, 'Run an optimization to see real totals here.'));
  else ses.append(h('dl', { class: 'stat-list' }, h('dt', {}, 'Runs'), h('dd', {}, formatInt(t.runs)), h('dt', {}, 'Original tokens'), h('dd', {}, formatInt(t.original)),
    h('dt', {}, 'Optimized tokens'), h('dd', {}, formatInt(t.optimized)), h('dt', {}, 'Tokens saved'), h('dd', {}, formatInt(t.saved)), h('dt', {}, 'Overall reduction'), h('dd', {}, formatPercent(t.percent))));
  const act = clear($('dash-activity'));
  if (!hist.length) act.append(h('p', { class: 'muted' }, 'Nothing yet. Run statistics are automatic; prompt text is saved only when you choose Save to history.'));
  else act.append(h('ul', { class: 'activity' }, hist.slice(0, 6).map((e) => h('li', {},
    h('span', {}, `${formatInt(e.original_tokens)} → ${formatInt(e.optimized_tokens)} tokens (${formatPercent(e.saved_percent)})${e.truncated ? ' · budget cut' : ''}`),
    h('span', { class: 'when' }, new Date(e.at).toLocaleString())))));
}
