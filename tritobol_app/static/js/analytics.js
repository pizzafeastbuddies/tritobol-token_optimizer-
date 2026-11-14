import { $, clear, h } from './dom.js';
import { barWidths, formatInt, formatPercent, savingsSummary, sessionTotals, truncationSummary } from './lib.js';
import { state } from './store.js';

function barRow(label, value, width, cls) {
  return h('div', { class: 'bar-row' }, h('span', {}, label),
    h('div', { class: 'bar-track' }, h('div', { class: `bar-fill ${cls}`, style: `width:${width.toFixed(2)}%` })), h('span', { class: 'num' }, formatInt(value)));
}

function historyChart(history) {
  const ns = 'http://www.w3.org/2000/svg';
  const pts = [...history].reverse().map((e) => e.saved_percent);
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 400 160'); svg.setAttribute('class', 'history-chart'); svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `Reduction percentage for the last ${pts.length} runs: ${pts.map(formatPercent).join(', ')}`);
  const lo = Math.min(0, ...pts), hi = Math.max(1, ...pts), y = (v) => 140 - ((v - lo) / (hi - lo)) * 120, x = (i) => 20 + (i * 360) / Math.max(1, pts.length - 1);
  const mk = (tag, attrs) => { const el = document.createElementNS(ns, tag); Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v)); return el; };
  svg.append(mk('line', { x1: 20, x2: 380, y1: y(0), y2: y(0), stroke: '#3b3129', 'stroke-width': 1 }));
  svg.append(mk('polyline', { points: pts.map((v, i) => `${x(i)},${y(v)}`).join(' '), fill: 'none', stroke: '#d2641a', 'stroke-width': 3 }));
  pts.forEach((v, i) => svg.append(mk('circle', { cx: x(i), cy: y(v), r: 4, fill: '#f2a73b' })));
  return svg;
}

export function renderAnalytics() {
  const r = state.result;
  $('analytics-empty').hidden = !!r; $('analytics-body').hidden = !r;
  if (!r) return;
  const s = r.stats, w = barWidths(s.original_tokens, s.optimized_tokens), sv = savingsSummary(s), tr = truncationSummary(r);
  const body = clear($('analytics-body'));
  body.append(
    h('div', { class: 'card' }, h('h2', {}, 'Latest run'), h('p', {}, sv.headline),
      h('div', { class: 'bars', role: 'group', 'aria-label': 'Original versus optimized tokens' },
        barRow('Original', s.original_tokens, w.original, ''), barRow('Optimized', s.optimized_tokens, w.optimized, 'opt')),
      h('p', { class: 'fineprint' }, `Reduction = tokens saved ÷ original tokens × 100 = ${formatInt(s.saved_tokens)} ÷ ${formatInt(s.original_tokens)}` +
        `${s.original_tokens === 0 ? ' (shown as 0.0% because the input has no tokens)' : ''}. Counts cover the supplied text only — no chat template or API overhead.`)),
    h('div', { class: `banner ${{ warn: 'banner-warn', ok: 'banner-ok', info: 'banner-info', error: 'banner-error' }[tr.level]}` }, h('h3', {}, tr.headline), h('ul', {}, tr.details.map((d) => h('li', {}, d)))));
  const grid = h('div', { class: 'analytics-grid' });
  const segs = r.segments.filter((g) => g.original_tokens || g.optimized_tokens);
  const max = Math.max(1, ...segs.map((g) => Math.max(g.original_tokens, g.optimized_tokens)));
  grid.append(h('div', { class: 'card' }, h('h3', {}, 'Tokens by segment (before budget cut)'), segs.length
    ? h('div', { class: 'bars' }, segs.map((g) => barRow(`${g.kind}: ${g.status}`, g.optimized_tokens, (g.optimized_tokens / max) * 100, 'seg')))
    : h('p', { class: 'muted' }, 'The engine reported no segments.'), h('p', { class: 'fineprint' }, 'Tokens per segment as reported by the engine after cleanup but before any budget cut, so they can add up to more than the final optimized count.')));
  grid.append(h('div', { class: 'card' }, h('h3', {}, 'Removed by cleanup'), h('dl', { class: 'stat-list' },
    ...[['Paragraphs', s.removed_paragraphs], ['Lines', s.removed_lines], ['Sentences', s.removed_sentences], ['Separators', s.removed_separators], ['Characters', s.removed_chars]]
      .flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, formatInt(v))]))));
  body.append(grid);
  const hist = state.history, t = sessionTotals(hist);
  body.append(h('div', { class: 'card', style: 'margin-top:1rem' }, h('h3', {}, 'Runs in this browser'),
    hist.length >= 2 ? historyChart(hist) : h('p', { class: 'muted' }, 'Run at least two optimizations to see a trend. Prompt text is stored only when you choose Save to history.'),
    h('p', {}, `${t.runs} run(s) · ${formatInt(t.original)} → ${formatInt(t.optimized)} tokens · ${formatPercent(t.percent)} overall`)));
}
