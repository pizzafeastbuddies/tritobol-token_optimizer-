import { api, setCsrf } from './api.js';
import { $ } from './dom.js';
import { passwordIssues, passwordStrength, validateRegistration, validateSignIn } from './lib.js';
import { state } from './store.js';

const NOTICE_KEY = 'tritobol.authNotice';
const PREFILL_KEY = 'tritobol.prefillEmail';

function sessionGet(k) { try { return globalThis.sessionStorage?.getItem(k) || ''; } catch { return ''; } }
function sessionSet(k, v) { try { globalThis.sessionStorage?.setItem(k, v); } catch {} }
function sessionRemove(k) { try { globalThis.sessionStorage?.removeItem(k); } catch {} }

export const authState = { ready: false, user: null };

export function hasAppSession() {
  return !!authState.user;
}

function fieldError(inputId, errorId, message) {
  const input = $(inputId);
  const err = $(errorId);
  if (!err) return;
  const text = message || '';
  err.hidden = !text;
  err.textContent = text;
  if (input) input.setAttribute('aria-invalid', text ? 'true' : 'false');
}

function togglePassword(buttonId, inputId) {
  $(buttonId)?.addEventListener('click', () => {
    const input = $(inputId);
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    $(buttonId).textContent = show ? 'Hide' : 'Show';
    $(buttonId).setAttribute('aria-pressed', show ? 'true' : 'false');
  });
}

function busy(button, label, on) {
  if (!button) return;
  button.disabled = on;
  button.classList.toggle('busy', on);
  if (on) { button.dataset.label = button.textContent; button.textContent = label; }
  else if (button.dataset.label) button.textContent = button.dataset.label;
}

function friendly(error) {
  return String(error?.message || 'The account request failed.');
}

export function clearSensitiveMemory() {
  state.result = null;
  state.sourceText = null;
  state.sourceName = null;
  const input = $('input-text');
  if (input) {
    input.value = '';
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }
  for (const id of ['signin-password', 'signup-password', 'signup-confirm', 'account-current', 'account-new', 'account-confirm']) {
    const field = $(id);
    if (field) field.value = '';
  }
}

export function refreshAccount() {
  const menu = $('profile-menu');
  const user = authState.user;
  if (menu) menu.hidden = !user;
  if (!user) return;
  if ($('profile-name')) $('profile-name').textContent = user.full_name || 'Signed in';
  if ($('profile-email')) $('profile-email').textContent = user.email || '';
  if ($('account-name')) $('account-name').textContent = user.full_name || '';
  if ($('account-email')) $('account-email').textContent = user.email || '';
}

function rememberSession(payload) {
  authState.user = payload?.authenticated || payload?.user ? (payload.user || null) : null;
  if (payload && Object.prototype.hasOwnProperty.call(payload, 'authenticated') && !payload.authenticated) authState.user = null;
  if (payload?.csrf_token) setCsrf(payload.csrf_token);
}

export async function loadSession() {
  const payload = await api.session();
  rememberSession(payload);
  return payload;
}

let shownNotice = '';

export function initAuth() {
  togglePassword('signin-toggle', 'signin-password');
  togglePassword('signup-toggle', 'signup-password');
  $('signup-password')?.addEventListener('input', () => {
    const el = $('signup-strength');
    if (el) el.textContent = `Strength: ${passwordStrength($('signup-password').value)}`;
  });
  $('profile-open')?.addEventListener('click', () => {
    const panel = $('profile-panel');
    const open = panel.hidden;
    panel.hidden = !open;
    $('profile-open').setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  $('btn-sign-out')?.addEventListener('click', async () => {
    try {
      const payload = await api.logout();
      if (payload?.csrf_token) setCsrf(payload.csrf_token);
    } catch { /* the local session is cleared either way */ }
    authState.user = null;
    clearSensitiveMemory();
    shownNotice = '';
    refreshAccount();
    location.hash = '#/home';
  });
  $('form-signin')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const result = validateSignIn({ email: $('signin-email').value, password: $('signin-password').value });
    fieldError('signin-email', 'signin-email-error', result.errors.email);
    fieldError('signin-password', 'signin-password-error', result.errors.password);
    $('signin-status').textContent = '';
    if (!result.ok) return;
    busy($('signin-submit'), 'Signing in', true);
    try {
      const payload = await api.login({ email: $('signin-email').value.trim(), password: $('signin-password').value });
      $('signin-password').value = '';
      shownNotice = '';
      rememberSession({ ...payload, authenticated: true });
      refreshAccount();
      const next = new URLSearchParams((location.hash.split('?')[1] || '')).get('next');
      const safe = ['dashboard', 'optimize', 'results', 'analytics', 'history', 'settings'].includes(next) ? next : 'dashboard';
      location.hash = `#/${safe}`;
    } catch (error) {
      $('signin-password').value = '';
      $('signin-status').textContent = friendly(error);
    } finally {
      busy($('signin-submit'), '', false);
    }
  });
  $('form-signup')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const result = validateRegistration({
      name: $('signup-name').value,
      email: $('signup-email').value,
      password: $('signup-password').value,
      confirm: $('signup-confirm').value,
    });
    fieldError('signup-name', 'signup-name-error', result.errors.name);
    fieldError('signup-email', 'signup-email-error', result.errors.email);
    fieldError('signup-password', 'signup-password-error', result.errors.password);
    fieldError('signup-confirm', 'signup-confirm-error', result.errors.confirm);
    $('signup-status').textContent = '';
    if (!result.ok) return;
    busy($('signup-submit'), 'Creating account', true);
    try {
      const email = $('signup-email').value.trim();
      const created = await api.register({
        name: $('signup-name').value.trim(),
        email,
        password: $('signup-password').value,
        confirm: $('signup-confirm').value,
      });
      $('signup-password').value = '';
      $('signup-confirm').value = '';
      sessionSet(PREFILL_KEY, email);
      sessionSet(NOTICE_KEY, created.message || 'Your account has been created successfully. Please sign in.');
      location.hash = '#/signin';
    } catch (error) {
      $('signup-status').textContent = friendly(error);
    } finally {
      busy($('signup-submit'), '', false);
    }
  });
  $('form-password')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const issues = passwordIssues($('account-new').value);
    fieldError('account-new', 'account-new-error', issues.length ? issues.join(' ') : '');
    const mismatch = $('account-new').value !== $('account-confirm').value;
    fieldError('account-confirm', 'account-confirm-error', mismatch ? 'Those passwords do not match.' : '');
    fieldError('account-current', 'account-current-error', $('account-current').value ? '' : 'Enter your current password.');
    $('account-status').textContent = '';
    if (issues.length || mismatch || !$('account-current').value) return;
    busy($('account-submit'), 'Updating', true);
    try {
      const payload = await api.changePassword({
        current_password: $('account-current').value,
        new_password: $('account-new').value,
        confirm: $('account-confirm').value,
      });
      rememberSession({ ...payload, authenticated: true });
      $('account-current').value = '';
      $('account-new').value = '';
      $('account-confirm').value = '';
      $('account-status').textContent = 'Password updated.';
    } catch (error) {
      $('account-status').textContent = friendly(error);
    } finally {
      busy($('account-submit'), '', false);
    }
  });
}

export function initContact() {
  $('contact-copy')?.addEventListener('click', async () => {
    const note = $('contact-note')?.value || '';
    const status = $('contact-status');
    if (!status) return;
    if (!note.trim()) { status.textContent = 'Write a note before copying it.'; return; }
    try {
      await navigator.clipboard.writeText(note);
      status.textContent = 'Copied. The note stays in this form and was not uploaded.';
    } catch {
      status.textContent = 'Could not copy. The note is still only in this form.';
    }
  });
}

export function prepareAuthScreen() {
  refreshAccount();
  const notice = sessionGet(NOTICE_KEY);
  if (notice) {
    shownNotice = notice;
    sessionRemove(NOTICE_KEY);
  }
  const banner = $('signin-banner');
  if (banner) banner.textContent = shownNotice;
  const email = sessionGet(PREFILL_KEY);
  if (email && $('signin-email') && !$('signin-email').value) {
    $('signin-email').value = email;
    sessionRemove(PREFILL_KEY);
  }
}
