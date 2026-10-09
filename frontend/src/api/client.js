// Configure with VITE_API_BASE_URL at build time (e.g. https://api.example.org); defaults to the local backend.
const API_BASE_URL = (import.meta.env && import.meta.env.VITE_API_BASE_URL) || 'http://localhost:8000';

// ---- session handling -------------------------------------------------------------------------------------------------
// The bearer token lives in sessionStorage (per browser tab, cleared when the tab closes), is sent only in the Authorization header,
// and never appears in URLs. There is no signing secret in the frontend: tokens are opaque and validated server-side.
const SESSION_KEY = 'rd_session';

export function getSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    const s = raw ? JSON.parse(raw) : null;
    return s && s.access_token ? s : null;
  } catch (e) {
    return null;
  }
}
function saveSession(s) {
  try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(s)); } catch (e) { /* storage unavailable: session lasts for this page only */ }
}
export function clearSession() {
  try { sessionStorage.removeItem(SESSION_KEY); } catch (e) { /* ignore */ }
}

function authHeaders() {
  return { 'Content-Type': 'application/json' };
}

// The single place that calls fetch(): attaches the credential and reports an expired / revoked session without touching page state,
// so unsaved work stays on screen while the user signs in again.
export async function authFetch(url, init = {}) {
  const headers = { ...(init.headers || {}) };
  const sess = getSession();
  if (sess) headers['Authorization'] = `Bearer ${sess.access_token}`;
  const res = await fetch(url, { ...init, headers });
  if (res.status === 401 && sess) {
    const body = await res.clone().json().catch(() => ({}));
    clearSession();
    window.dispatchEvent(new CustomEvent('rd-auth-expired', { detail: { status: body?.detail?.status || 'session_expired' } }));
  }
  return res;
}

async function authJson(path, body) {
  const res = await authFetch(`${API_BASE_URL}${path}`, { method: 'POST', headers: authHeaders(), body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    const err = new Error((d && typeof d === 'object' ? d.message : d) || `Request failed (${res.status})`);
    err.status = d && typeof d === 'object' ? d.status : undefined;
    err.problems = d && typeof d === 'object' ? d.problems || [] : [];
    err.httpStatus = res.status;
    throw err;
  }
  return data;
}

export async function registerUser({ email, password, display_name }) {
  return authJson('/api/auth/register', { email, password, display_name });
}

export async function loginUser({ email, password }) {
  const data = await authJson('/api/auth/login', { email, password });
  saveSession({ access_token: data.access_token, expires_at: data.expires_at, user: data.user });
  return data;
}

export async function logoutUser() {
  try {
    await authFetch(`${API_BASE_URL}/api/auth/logout`, { method: 'POST', headers: authHeaders() });
  } finally {
    clearSession();   // the local credential is dropped even if the server could not be reached
  }
}
function detailMessage(d) {
  if (!d) return '';
  return typeof d === 'object' ? (d.message || d.status || '') : d;
}

export async function checkBackendHealth() {
  try {
    const res = await authFetch(`${API_BASE_URL}/`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('Backend health check failed:', err);
    return { status: 'offline', error: err.message };
  }
}

export async function diagnoseCase({ text, top_k = 5, exp_config = 'rag_south_asian_global' }) {
  const res = await authFetch(`${API_BASE_URL}/api/diagnose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, top_k, exp_config })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Server error (${res.status})`);
  }
  return await res.json();
}

export async function explainCandidate({ case_id, disease_id, clinical_text = '' }) {
  const res = await authFetch(`${API_BASE_URL}/api/explain`, {
    method: 'POST',
    headers: authHeaders(case_id),
    body: JSON.stringify({ case_id, disease_id, clinical_text })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Server error (${res.status})`);
  }
  return await res.json();
}

export async function reasonCase({ case_id, clinical_text = '', top_k = 5 }) {
  const res = await authFetch(`${API_BASE_URL}/api/reason`, {
    method: 'POST',
    headers: authHeaders(case_id),
    body: JSON.stringify({ case_id, clinical_text, top_k })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Server error (${res.status})`);
  }
  return await res.json();
}

export async function getDifferential({ case_id, clinical_text = '', top_k = 5 }) {
  const res = await authFetch(`${API_BASE_URL}/api/differential`, {
    method: 'POST',
    headers: authHeaders(case_id),
    body: JSON.stringify({ case_id, clinical_text, top_k })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Server error (${res.status})`);
  }
  return await res.json();
}

export async function askDoctorCopilot({ query, case_id, clinical_text = '' }) {
  const res = await authFetch(`${API_BASE_URL}/api/copilot`, {
    method: 'POST',
    headers: authHeaders(case_id),
    body: JSON.stringify({ query, case_id, clinical_text })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    const err = new Error(detailMessage(errData.detail) || `Server error (${res.status})`);
    err.httpStatus = res.status;
    throw err;
  }
  return await res.json();
}

export async function runScribe({ case_id, clinical_text }) {
  const res = await authFetch(`${API_BASE_URL}/api/scribe`, {
    method: 'POST',
    headers: authHeaders(case_id),
    body: JSON.stringify({ case_id, clinical_text })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Server error (${res.status})`);
  }
  return await res.json();
}

export async function runCounterfactual({
  case_id,
  clinical_text,
  operation = 'remove',
  phenotype_id,
  added_phenotypes = [],
  removed_phenotypes = [],
  modified_phenotypes = [],
  exp_config = 'rag_south_asian_global',
  top_k = 5
}) {
  const res = await authFetch(`${API_BASE_URL}/api/counterfactual`, {
    method: 'POST',
    headers: authHeaders(case_id),
    body: JSON.stringify({
      case_id,
      clinical_text,
      operation,
      phenotype_id,
      added_phenotypes,
      removed_phenotypes,
      modified_phenotypes,
      exp_config,
      top_k
    })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Server error (${res.status})`);
  }
  return await res.json();
}

export async function counterfactualAdd({ case_id, phenotype_id }) {
  return runCounterfactual({ case_id, operation: 'add', phenotype_id });
}

export async function counterfactualRemove({ case_id, phenotype_id }) {
  return runCounterfactual({ case_id, operation: 'remove', phenotype_id });
}

export async function counterfactualCompare({ case_id, modified_phenotypes }) {
  return runCounterfactual({ case_id, operation: 'compare', modified_phenotypes });
}

export async function getCounterfactualHistory(case_id) {
  const res = await authFetch(`${API_BASE_URL}/api/counterfactual/${encodeURIComponent(case_id)}`, {});
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Server error (${res.status})`);
  }
  return await res.json();
}

export async function validateClinicalInput({ text }) {
  const res = await authFetch(`${API_BASE_URL}/api/input/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Validation error (${res.status})`);
  }
  return await res.json();
}

export async function enhanceClinicalText({ text }) {
  const res = await authFetch(`${API_BASE_URL}/api/input/enhance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `AI Enhancement error (${res.status})`);
  }
  return await res.json();
}

// ==========================================
// PHASE 6: LITERATURE & REPORTING API CALLS
// ==========================================

export async function searchLiterature({ disease_id, disease_name, genes = [], phenotypes = [], max_results = 8, custom_query = null }) {
  const res = await authFetch(`${API_BASE_URL}/api/literature/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ disease_id, disease_name, genes, phenotypes, max_results, custom_query })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Literature search error (${res.status})`);
  }
  return await res.json();
}

export async function getLiteratureArticle(pmid) {
  const res = await authFetch(`${API_BASE_URL}/api/literature/${pmid}`);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Error fetching article ${pmid} (${res.status})`);
  }
  return await res.json();
}

export async function getEvidenceProfile(disease_id, case_id = null) {
  const url = case_id 
    ? `${API_BASE_URL}/api/evidence/profile/${encodeURIComponent(disease_id)}?case_id=${encodeURIComponent(case_id)}`
    : `${API_BASE_URL}/api/evidence/profile/${encodeURIComponent(disease_id)}`;
  const res = await authFetch(url, {});
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Error fetching evidence profile (${res.status})`);
  }
  return await res.json();
}

export async function getEvidenceMatrix(disease_id, case_id = null) {
  const url = case_id 
    ? `${API_BASE_URL}/api/evidence/matrix/${encodeURIComponent(disease_id)}?case_id=${encodeURIComponent(case_id)}`
    : `${API_BASE_URL}/api/evidence/matrix/${encodeURIComponent(disease_id)}`;
  const res = await authFetch(url, {});
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Error fetching evidence matrix (${res.status})`);
  }
  return await res.json();
}

export async function generateCaseReport({ case_id = null, clinical_text = null, top_k = 5, include_indigen_demo = false }) {
  const res = await authFetch(`${API_BASE_URL}/api/report/generate`, {
    method: 'POST',
    headers: authHeaders(case_id),
    body: JSON.stringify({ case_id, clinical_text, top_k, include_indigen_demo })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Report generation error (${res.status})`);
  }
  const rep = await res.json();
  return rep;
}

export async function getCaseReport(report_id) {
  const res = await authFetch(`${API_BASE_URL}/api/report/${encodeURIComponent(report_id)}`, {});
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Error fetching report (${res.status})`);
  }
  return await res.json();
}

// The export needs the session credential (a header, never a URL), so it is fetched and opened/downloaded as a blob.
export async function openReportHtml(report_id, { download = false } = {}) {
  const res = await authFetch(`${API_BASE_URL}/api/report/${encodeURIComponent(report_id)}/export`);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(detailMessage(errData.detail) || `Report export failed (${res.status})`);
  }
  const url = URL.createObjectURL(await res.blob());
  if (download) {
    const a = document.createElement('a');
    a.href = url;
    a.download = `Report_${report_id}.html`;
    a.click();
  } else {
    window.open(url, '_blank', 'noopener');
  }
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}



// ==========================================
// PHASE 5R: SCRIBE DRAFTS + COUNTERFACTUAL SCENARIOS
// ==========================================

async function jsonOrThrow(res, fallback) {
  if (res.ok) return await res.json();
  const errData = await res.json().catch(() => ({}));
  const d = errData.detail;
  const msg = d && typeof d === 'object' ? (d.message || d.status) : d;
  const err = new Error(msg || `${fallback} (${res.status})`);
  err.status = d && typeof d === 'object' ? d.status : undefined;
  err.httpStatus = res.status;
  throw err;
}

export async function createScribeDraft({ clinical_text, supplied_phenotypes = null, check_enhancement = false, save = true }) {
  const res = await authFetch(`${API_BASE_URL}/api/scribe/draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clinical_text, supplied_phenotypes, check_enhancement, save })
  });
  return jsonOrThrow(res, 'Draft generation failed');
}

export async function updateScribeDraft({ draft_id, token, update }) {
  const res = await authFetch(`${API_BASE_URL}/api/scribe/draft/${encodeURIComponent(draft_id)}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(update)
  });
  return jsonOrThrow(res, 'Saving the draft failed');
}

export async function runCounterfactualScenario({ case_id, clinical_text, operations = [], top_k = 5 }) {
  const res = await authFetch(`${API_BASE_URL}/api/counterfactual/scenario`, {
    method: 'POST',
    headers: authHeaders(case_id),
    body: JSON.stringify({ case_id, clinical_text, operations, top_k })
  });
  return jsonOrThrow(res, 'Scenario failed');
}

// ==========================================
// PHASE 7R.5: CLINICAL DIGITAL TWIN (owner-scoped; every call carries the session credential)
// ==========================================
async function twinJson(path, init = {}) {
  const res = await authFetch(`${API_BASE_URL}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(init.headers || {}) } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    const err = new Error((d && typeof d === 'object' ? d.message : d) || `Request failed (${res.status})`);
    err.httpStatus = res.status;
    err.status = d && typeof d === 'object' ? d.status : undefined;
    throw err;
  }
  return data;
}

export const getTwinCases = () => twinJson('/api/twin/cases');
// Deletes one of the caller's own cases and everything derived from it (scenarios, reports); owner-scoped on the server.
export const deleteCase = (caseId) => twinJson(`/api/case/${encodeURIComponent(caseId)}`, { method: 'DELETE' });
export const getTwinCase = (caseId) => twinJson(`/api/twin/${encodeURIComponent(caseId)}`);
export const reviewTwinFindings = (caseId, updates) =>
  twinJson(`/api/twin/${encodeURIComponent(caseId)}/findings`, { method: 'PUT', body: JSON.stringify({ updates }) });
export const mapTwinRegions = (hpoIds) => twinJson('/api/twin/regions', { method: 'POST', body: JSON.stringify({ hpo_ids: hpoIds }) });
export const getScenario = (scenarioId) => twinJson(`/api/counterfactual/scenario/${encodeURIComponent(scenarioId)}`);
export const runTwinScenario = (caseId, operations) =>
  twinJson('/api/counterfactual/scenario', { method: 'POST', body: JSON.stringify({ case_id: caseId, operations, top_k: 5 }) });

// Gene-level reference evidence (same backend service as the Digital Twin payload).
export const getGeneEvidence = (symbol, { demo = false } = {}) =>
  twinJson(`/api/genomic/gene/${encodeURIComponent(symbol)}${demo ? '?indigen_demo=true' : ''}`);
export const ingestGeneEvidence = (symbol, { demo = false } = {}) =>
  twinJson(`/api/genomic/gene/${encodeURIComponent(symbol)}/ingest${demo ? '?indigen_demo=true' : ''}`, { method: 'POST' });
// IndiGen DEMO (synthetic, display only)
export const getIndigenDemoStatus = () => twinJson('/api/genomic/indigen-demo/status');
export const getIndigenDemoGenes = (symbols) => twinJson(`/api/genomic/indigen-demo/genes?symbols=${encodeURIComponent(symbols.join(','))}`);
