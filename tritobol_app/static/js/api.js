// Backend client. `globalThis.TRITOBOL_BASE_URL` exists only so tests can point it at a test server.
export class ApiError extends Error {
  constructor(code, message, field = null) { super(message); this.code = code; this.field = field; }
}
const base = () => globalThis.TRITOBOL_BASE_URL || '';
const token = () => document.querySelector('meta[name="tritobol-token"]')?.content || '';

async function request(path, { method = 'GET', json, form, signal } = {}) {
  const headers = {};
  if (method === 'POST') headers['X-Tritobol-Token'] = token();
  if (json !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(base() + path, { method, headers, signal, body: json !== undefined ? JSON.stringify(json) : form });
  } catch (err) {
    if (err && err.name === 'AbortError') throw new ApiError('cancelled', 'Cancelled.');
    throw new ApiError('backend_unavailable', 'Cannot reach the Tritobol backend. Check that the app is still running (start it again with start.bat), then reload this page.');
  }
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON error page */ }
  if (!res.ok || !data || data.ok === false) {
    const e = data && data.error;
    throw new ApiError((e && e.code) || `http_${res.status}`, (e && e.message) || `Unexpected response from the backend (HTTP ${res.status}).`, e && e.field);
  }
  return data;
}

export const api = {
  health: () => request('/api/health'),
  tokenizers: () => request('/api/tokenizers'),
  uploadTokenizer: (file) => { const f = new FormData(); f.append('file', file, file.name); return request('/api/tokenizers/upload', { method: 'POST', form: f }); },
  loadFile: (file) => { const f = new FormData(); f.append('file', file, file.name); return request('/api/load-file', { method: 'POST', form: f }); },
  optimize: (payload, signal) => request('/api/optimize', { method: 'POST', json: payload, signal }),
  exportText: (payload) => request('/api/export', { method: 'POST', json: payload }),
};
