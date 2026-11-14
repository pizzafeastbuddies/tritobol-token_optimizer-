import { api } from './api.js';
import { renderAnalytics } from './analytics.js';
import { renderDashboard } from './dashboard.js';
import { $ } from './dom.js';
import { applySettingsToForm, initEditor, populateTokenizers } from './editor.js';
import { initResults } from './results.js';
import { initPromptHistory, renderPromptHistory } from './prompt-history.js';
import { initSettings, renderSettings } from './settings.js';
import { state, subscribe } from './store.js';

const VIEWS = ['dashboard', 'optimize', 'analytics', 'prompt-history', 'privacy', 'settings'];

function route() {
  const name = (location.hash.replace(/^#\/?/, '') || 'dashboard');
  const view = VIEWS.includes(name) ? name : 'dashboard';
  document.querySelectorAll('[data-view]').forEach((el) => { el.hidden = el.dataset.view !== view; });
  document.querySelectorAll('[data-route]').forEach((a) => { if (a.dataset.route === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  if (view === 'analytics') renderAnalytics();
  if (view === 'prompt-history') renderPromptHistory();
  if (view === 'dashboard') renderDashboard();
  if (view === 'settings') renderSettings();
  document.title = `Tritobol — ${view === 'optimize' ? 'optimizer' : view}`;
}

async function boot() {
  initEditor(); initResults(); initPromptHistory(); initSettings(() => { applySettingsToForm(); renderDashboard(); });
  subscribe(() => { renderDashboard(); if (location.hash === '#/prompt-history') renderPromptHistory(); });
  applySettingsToForm();
  window.addEventListener('hashchange', route);
  route();
  try {
    const [{ tokenizers }, health] = await Promise.all([api.tokenizers(), api.health()]);
    state.tokenizers = tokenizers;
    $('privacy-live').textContent = health.local_only ? 'The backend currently reports that it is running local-only.' : '';
  } catch (err) {
    const box = $('app-alert'); box.hidden = false; box.textContent = err.message;
  }
  populateTokenizers(); applySettingsToForm(); renderDashboard(); renderSettings();
}

boot();
