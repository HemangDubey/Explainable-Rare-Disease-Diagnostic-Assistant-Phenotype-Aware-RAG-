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

export async function runScribe({ case_id, clinical_text }) {
  const res = await fetch(`${API_BASE_URL}/api/scribe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id, clinical_text })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Server error (${res.status})`);
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
  exp_config = 'rag_indigen_gnomad',
  top_k = 5
}) {
  const res = await fetch(`${API_BASE_URL}/api/counterfactual`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
    throw new Error(errData.detail || `Server error (${res.status})`);
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
  const res = await fetch(`${API_BASE_URL}/api/counterfactual/${case_id}`);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Server error (${res.status})`);
  }
  return await res.json();
}

export async function validateClinicalInput({ text }) {
  const res = await fetch(`${API_BASE_URL}/api/input/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Validation error (${res.status})`);
  }
  return await res.json();
}

export async function enhanceClinicalText({ text }) {
  const res = await fetch(`${API_BASE_URL}/api/input/enhance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `AI Enhancement error (${res.status})`);
  }
  return await res.json();
}

// ==========================================
// PHASE 6: LITERATURE & REPORTING API CALLS
// ==========================================

export async function searchLiterature({ disease_id, disease_name, genes = [], phenotypes = [], max_results = 8, custom_query = null }) {
  const res = await fetch(`${API_BASE_URL}/api/literature/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ disease_id, disease_name, genes, phenotypes, max_results, custom_query })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Literature search error (${res.status})`);
  }
  return await res.json();
}

export async function getLiteratureArticle(pmid) {
  const res = await fetch(`${API_BASE_URL}/api/literature/${pmid}`);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Error fetching article ${pmid} (${res.status})`);
  }
  return await res.json();
}

export async function getEvidenceProfile(disease_id, case_id = null) {
  const url = case_id 
    ? `${API_BASE_URL}/api/evidence/profile/${encodeURIComponent(disease_id)}?case_id=${encodeURIComponent(case_id)}`
    : `${API_BASE_URL}/api/evidence/profile/${encodeURIComponent(disease_id)}`;
  const res = await fetch(url);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Error fetching evidence profile (${res.status})`);
  }
  return await res.json();
}

export async function getEvidenceMatrix(disease_id, case_id = null) {
  const url = case_id 
    ? `${API_BASE_URL}/api/evidence/matrix/${encodeURIComponent(disease_id)}?case_id=${encodeURIComponent(case_id)}`
    : `${API_BASE_URL}/api/evidence/matrix/${encodeURIComponent(disease_id)}`;
  const res = await fetch(url);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Error fetching evidence matrix (${res.status})`);
  }
  return await res.json();
}

export async function generateCaseReport({ case_id = null, clinical_text = null, top_k = 5 }) {
  const res = await fetch(`${API_BASE_URL}/api/report/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id, clinical_text, top_k })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Report generation error (${res.status})`);
  }
  return await res.json();
}

export async function getCaseReport(report_id) {
  const res = await fetch(`${API_BASE_URL}/api/report/${encodeURIComponent(report_id)}`);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Error fetching report (${res.status})`);
  }
  return await res.json();
}

export function getExportReportHtmlUrl(report_id) {
  return `${API_BASE_URL}/api/report/${encodeURIComponent(report_id)}/export`;
}


