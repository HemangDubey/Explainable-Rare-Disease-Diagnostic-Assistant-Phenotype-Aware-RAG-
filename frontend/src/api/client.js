const API_BASE_URL = 'http://localhost:8000';

export async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('Backend health check failed:', err);
    return { status: 'offline', error: err.message };
  }
}

export async function diagnoseCase({ text, top_k = 5, exp_config = 'rag_indigen_gnomad' }) {
  const res = await fetch(`${API_BASE_URL}/api/diagnose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, top_k, exp_config })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Server error (${res.status})`);
  }
  return await res.json();
}

export async function explainCandidate({ case_id, disease_id, clinical_text = '' }) {
  const res = await fetch(`${API_BASE_URL}/api/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id, disease_id, clinical_text })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Server error (${res.status})`);
  }
  return await res.json();
}

export async function getDifferential({ case_id, clinical_text = '', top_k = 5 }) {
  const res = await fetch(`${API_BASE_URL}/api/differential`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id, clinical_text, top_k })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Server error (${res.status})`);
  }
  return await res.json();
}

export async function askDoctorCopilot({ query, case_id, clinical_text = '' }) {
  const res = await fetch(`${API_BASE_URL}/api/copilot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, case_id, clinical_text })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Server error (${res.status})`);
  }
  return await res.json();
}
