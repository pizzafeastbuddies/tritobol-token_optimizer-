import { h, clear } from './dom.js';
import { diffViewModel, formatInt } from './lib.js';

const ROW_CHUNK = 400; // rows rendered per step so a huge diff never freezes the page

function wordSpans(words, side) {
  const out = [];
  for (const w of words) {
    if (w.t === 'equal') out.push(w.a);
    else if (side === 'a' && w.a) out.push(h('span', { class: 'w-del' }, w.a));
    else if (side === 'b' && w.b) out.push(h('span', { class: 'w-add' }, w.b));
  }
  return out;
}

function rowEl(r) {
  const a = r.kind === 'added' ? '' : (r.kind === 'changed' && r.words ? wordSpans(r.words, 'a') : r.a);
  const b = r.kind === 'removed' ? '' : (r.kind === 'changed' && r.words ? wordSpans(r.words, 'b') : r.b);
  return h('div', { class: `drow ${r.kind}` },
    h('span', { class: 'dno' }, r.aNo ?? ''), h('span', { class: 'a' }, a),
    h('span', { class: 'dno bn' }, r.bNo ?? ''), h('span', { class: 'b' }, b));
}

// Renders rows lazily: `queue` is a list of nodes-to-be; the "show more" button appends the next chunk.
function renderBlocks(container, blocks) {
  const queue = [];
  for (const block of blocks) {
    if (block.type === 'rows') block.rows.forEach((r) => queue.push({ row: r }));
    else queue.push({ collapsed: block });
  }
  let index = 0;
  const more = h('button', { type: 'button', class: 'btn btn-small diff-more' }, '');
  const pump = () => {
    let drawn = 0;
    while (index < queue.length && drawn < ROW_CHUNK) {
      const item = queue[index++];
      if (item.row) { container.insertBefore(rowEl(item.row), more); drawn++; continue; }
      const hidden = item.collapsed.rows;
      const btn = h('button', { type: 'button', class: 'dcollapse' }, `Show ${formatInt(hidden.length)} unchanged lines`);
      btn.addEventListener('click', () => { const frag = document.createDocumentFragment(); hidden.slice(0, 2000).forEach((r) => frag.append(rowEl(r)));
        if (hidden.length > 2000) frag.append(h('div', { class: 'dcollapse' }, `…${formatInt(hidden.length - 2000)} more unchanged lines not shown`));
        btn.replaceWith(frag); });
      container.insertBefore(btn, more); drawn++;
    }
    if (index >= queue.length) more.remove();
    else more.textContent = `Show more (${formatInt(queue.length - index)} remaining)`;
  };
  more.addEventListener('click', pump);
  container.append(more);
  pump();
}

export function renderDiff(panel, diff) {
  clear(panel);
  const vm = diffViewModel(diff);
  if (!vm.available) { panel.append(h('div', { class: 'banner banner-info' }, h('p', {}, vm.reason))); return; }
  if (vm.identical) { panel.append(h('div', { class: 'banner banner-ok' }, h('p', {}, 'No differences: the optimized text is identical to the original.'))); return; }
  const s = vm.summary;
  panel.append(
    h('div', { class: 'diff-legend' },
      h('span', {}, h('span', { class: 'chip chip-del' }, 'removed'), ' only in the original'),
      h('span', {}, h('span', { class: 'chip chip-add' }, 'kept / added'), ' in the optimized text'),
      h('span', {}, `${formatInt(s.lines_removed_or_changed)} original lines removed or changed · ${formatInt(s.lines_unchanged)} unchanged`)),
    h('p', { class: 'fineprint' }, 'Computed line by line from your original text and the optimizer’s actual output. Whitespace normalisation shows up as a changed line.'));
  const box = h('div', { class: 'diff', role: 'region', 'aria-label': 'Differences between original and optimized text', tabindex: '0' });
  panel.append(box);
  renderBlocks(box, vm.blocks);
}
