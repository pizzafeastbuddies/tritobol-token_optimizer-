import { api } from './api.js';
import { hasAppSession, initAuth, initContact, loadSession, prepareAuthScreen, refreshAccount, authState } from './auth.js';
import { renderAnalytics } from './analytics.js';
import { renderDashboard } from './dashboard.js';
import { $ } from './dom.js';
import { applySettingsToForm, initEditor, populateTokenizers } from './editor.js';
import { initHistory, renderHistory } from './history.js';
import { initResults, renderResultsPage } from './results.js';
import { initSettings, renderSettings } from './settings.js';
import { initShell, syncShell } from './shell.js';
import { bindThemeToggles, currentTheme, saveTheme, state, subscribe, watchSystemTheme } from './store.js';

const VIEWS = ['dashboard', 'optimize', 'results', 'analytics', 'history', 'privacy', 'settings', 'home', 'features', 'about', 'contact', 'terms', 'signin', 'signup', 'forgot', 'reset'];
const PROTECTED = new Set(['dashboard', 'optimize', 'results', 'analytics', 'history', 'settings']);

function requestedView() {
  const raw = (location.hash.replace(/^#\/?/, '') || 'home').split(/[?#]/)[0];
  if (VIEWS.includes(raw)) return raw;
  return hasAppSession() ? 'dashboard' : 'home';
}

function route() {
  const gate = $('session-gate');
  if (!authState.ready) {
    document.documentElement.dataset.session = 'loading';
    document.querySelectorAll('[data-view]').forEach((el) => { el.hidden = true; });
    if (gate) gate.hidden = false;
    return;
  }
  if (gate) gate.hidden = true;
  refreshAccount();
  document.documentElement.dataset.session = hasAppSession() ? 'in' : 'out';
  const view = requestedView();
  if (PROTECTED.has(view) && !hasAppSession()) {
    location.hash = `#/signin?next=${encodeURIComponent(view)}`;
    return;
  }
  if ((view === 'signin' || view === 'signup') && hasAppSession()) {
    location.hash = '#/dashboard';
    return;
  }
  document.querySelectorAll('[data-view]').forEach((el) => { el.hidden = el.dataset.view !== view; });
  document.querySelectorAll('[data-route]').forEach((a) => { if (a.dataset.route === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  syncShell(view);
  if (view === 'signin') prepareAuthScreen();
  if (view === 'analytics') renderAnalytics();
  if (view === 'dashboard') renderDashboard();
  if (view === 'settings') renderSettings();
  if (view === 'results') renderResultsPage();
  if (view === 'history') renderHistory();
  const titles = { optimize: 'optimizer', results: 'results', analytics: 'analytics', history: 'history', privacy: 'privacy', settings: 'settings', dashboard: 'dashboard', home: 'home', features: 'features', about: 'about', contact: 'contact', terms: 'terms', signin: 'sign in', signup: 'create account', forgot: 'forgot password', reset: 'password recovery' };
  document.title = `Tritobol — ${titles[view] || view}`;
}

async function boot() {
  saveTheme(currentTheme());
  watchSystemTheme();
  bindThemeToggles();
  initShell();
  initAuth();
  initContact();
  initEditor(); initResults(); initHistory(); initSettings(() => { applySettingsToForm(); renderDashboard(); renderHistory(); });
  subscribe(() => { renderDashboard(); if ((location.hash || '').includes('history')) renderHistory(); if ((location.hash || '').includes('results')) renderResultsPage(); });
  applySettingsToForm();
  window.addEventListener('hashchange', route);
  authState.ready = false;
  route();
  try {
    await loadSession();
  } catch (err) {
    authState.user = null;
    const box = $('app-alert');
    if (box) { box.hidden = false; box.textContent = err.message; }
  }
  authState.ready = true;
  route();
  try {
    const [{ tokenizers }, health] = await Promise.all([api.tokenizers(), api.health()]);
    state.tokenizers = tokenizers;
    if ($('privacy-live')) $('privacy-live').textContent = health.local_only ? 'The backend currently reports that it is running local-only.' : '';
  } catch (err) {
    const box = $('app-alert'); box.hidden = false; box.textContent = err.message;
  }
  populateTokenizers(); applySettingsToForm(); renderDashboard(); renderSettings();
}

boot();
