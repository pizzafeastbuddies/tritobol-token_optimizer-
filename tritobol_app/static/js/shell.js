import { $ } from './dom.js';

const KEY = 'tritobol.sidebar.v1';
const PUBLIC = new Set(['home', 'features', 'about', 'contact', 'terms', 'privacy', 'signin', 'signup', 'forgot', 'reset']);
const TITLES = {
  dashboard: 'Dashboard', optimize: 'Optimizer', results: 'Results', history: 'Prompt history',
  analytics: 'Analytics', privacy: 'Privacy', settings: 'Settings', home: 'Home', features: 'Features',
  about: 'About', contact: 'Contact', terms: 'Terms', privacy: 'Privacy', signin: 'Sign in', signup: 'Create account', forgot: 'Forgot password',
  reset: 'Password recovery',
};

function collapsed() {
  try { return localStorage.getItem(KEY) === '1'; } catch { return false; }
}

function applyCollapsed(on) {
  const shell = $('shell');
  const btn = $('sidebar-collapse');
  if (!shell || !btn) return;
  shell.classList.toggle('is-collapsed', on);
  btn.setAttribute('aria-expanded', on ? 'false' : 'true');
  btn.textContent = on ? 'Expand' : 'Collapse';
  btn.title = on ? 'Expand sidebar' : 'Collapse sidebar';
}

function closeDrawer() {
  $('shell')?.classList.remove('drawer-open');
  const open = $('nav-open');
  if (open) open.setAttribute('aria-expanded', 'false');
  const backdrop = $('nav-backdrop');
  if (backdrop) backdrop.hidden = true;
  applyCollapsed(collapsed());
}

export function syncShell(view) {
  const shell = $('shell');
  if (!shell) return;
  const pub = PUBLIC.has(view);
  shell.classList.toggle('is-public', pub);
  const footer = $('site-footer');
  if (footer) footer.hidden = !pub;
  const title = $('topbar-title');
  if (title) title.textContent = TITLES[view] || 'Tritobol';
  document.querySelectorAll('.site-nav a').forEach((link) => {
    const name = (link.getAttribute('href') || '').replace(/^#\/?/, '');
    if (name && name === view) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  closeDrawer();
}

export function initShell() {
  applyCollapsed(collapsed());
  $('sidebar-collapse')?.addEventListener('click', () => {
    const shell = $('shell');
    const narrow = window.matchMedia('(max-width: 980px)').matches;
    if (narrow && shell.classList.contains('drawer-open')) { closeDrawer(); return; }
    const next = !shell.classList.contains('is-collapsed');
    try { localStorage.setItem(KEY, next ? '1' : '0'); } catch { /* preference stays for this view */ }
    applyCollapsed(next);
  });
  $('nav-open')?.addEventListener('click', () => {
    $('shell').classList.add('drawer-open');
    $('nav-open').setAttribute('aria-expanded', 'true');
    const backdrop = $('nav-backdrop');
    if (backdrop) backdrop.hidden = false;
    const btn = $('sidebar-collapse');
    if (btn) { btn.textContent = 'Close'; btn.title = 'Close menu'; }
  });
  $('nav-backdrop')?.addEventListener('click', closeDrawer);
  $('sidebar')?.addEventListener('click', (event) => { if (event.target.closest('a')) closeDrawer(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeDrawer(); });
}
