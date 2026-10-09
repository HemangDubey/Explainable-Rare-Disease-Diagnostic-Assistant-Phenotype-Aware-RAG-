// Diagnostic Workspace: clinical text intake (primary action) -> phenotype extraction status -> ranked candidates with evidence.
// All case state lives in the shared WorkspaceContext so other modules (differential, copilot, reports...) see the same case.
import React from 'react';
import { Link } from 'react-router-dom';
import ClinicalInputSection from '../components/ClinicalInputSection';
import EvidenceCards from '../components/EvidenceCards';
import { EmptyState, ErrorAlert, PageHeader } from '../app/ui';
import { SAMPLE_CASES, useWorkspace } from '../app/WorkspaceContext';

function mappingLabel(item) {
  if (item.mapping_status === 'ambiguous') return 'Ambiguous — several HPO terms fit';
  if (item.mapping_status === 'non_phenotype') return 'HPO modifier — not used as a phenotype';
  return 'No confident HPO mapping';
}

function ExtractionPanel({ caseData }) {
  const items = caseData.extracted_phenotypes || [];
  const mapped = items.filter((i) => i.hpo_id && i.mapping_status !== 'non_phenotype');
  const cov = caseData.population_coverage;
  const twin = `/digital-twin?case=${encodeURIComponent(caseData.case_id)}`;
  return (
    <section className="ui-card ui-card-pad" aria-labelledby="extraction-title">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <h2 id="extraction-title" className="ui-section-title">Extracted phenotypes</h2>
        <span className="ui-chip-success">{mapped.length} mapped to HPO</span>
        {items.length - mapped.length > 0 && <span className="ui-chip-warn">{items.length - mapped.length} not mapped</span>}
        <span className="ui-chip-neutral">Not yet verified</span>
        <span className="ml-auto flex flex-wrap gap-2">
          <Link to={`${twin}#twin-phenotypes`} className="ui-btn-secondary py-1.5">
            <span className="material-symbols-outlined text-[18px]" aria-hidden="true">fact_check</span>Verify findings
          </Link>
          <Link to={twin} className="ui-btn-secondary py-1.5">
            <span className="material-symbols-outlined text-[18px]" aria-hidden="true">accessibility_new</span>Open in Digital Twin
          </Link>
        </span>
      </div>
      <ul className="flex flex-wrap gap-2">
        {items.map((item, idx) => {
          const ok = item.hpo_id && item.mapping_status !== 'non_phenotype';
          return (
            <li key={idx}
              title={ok ? `${item.hpo_term} — ${item.matching_method} match (${Number(item.mapping_score || 0).toFixed(2)}); NER confidence ${Number(item.confidence || 0).toFixed(2)}`
                : `NER confidence ${Number(item.confidence || 0).toFixed(2)}`}
              className={`inline-flex flex-wrap items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[13px] ${ok ? 'border-line bg-white' : 'border-warn/30 bg-warn-soft'}`}>
              <strong className="font-semibold text-ink">{item.mention || item.phenotype}</strong>
              {ok ? <span className="font-mono text-[11px] text-ocean">{item.hpo_id} · {item.hpo_term}</span>
                : <span className="text-[11px] text-warn">{mappingLabel(item)}</span>}
            </li>
          );
        })}
      </ul>
      <div className="mt-3 flex flex-col gap-0.5 text-[12px] text-ink-muted">
        {caseData.retrieval_metadata?.model && (
          <p>Retrieval: {caseData.retrieval_metadata.model_name || caseData.retrieval_metadata.model} · {caseData.retrieval_metadata.strategy}
            {' · '}{caseData.retrieval_metadata.n_mapped_hpo_terms} of {caseData.retrieval_metadata.n_mentions} detected phenotypes mapped to HPO</p>
        )}
        {cov && (
          <p>Population evidence ({cov.candidates} candidates): gnomAD South Asian {cov.gnomad_south_asian_available}/{cov.candidates}
            {' · '}gnomAD global {cov.gnomad_global_available}/{cov.candidates}
            {' · '}IndiGen {cov.indigen_available}/{cov.candidates}{cov.indigen_dataset !== 'available' ? ' (dataset unavailable — access required)' : ''}
            {!cov.signal_defined ? ` · population signal not defined (${cov.reference_genes}/${cov.reference_genes_required} reference genes)` : ''}</p>
        )}
      </div>
    </section>
  );
}

export default function DashboardPage() {
  const { inputText, setInputText, caseData, isLoading, error, runDiagnosis, explanations, isExplaining, reasoningStatus,
    explainCandidates } = useWorkspace();
  const cands = caseData?.fused_candidates || [];

  return (
    <>
      <PageHeader title="Diagnostic Workspace"
        description="Enter or dictate the clinical description, run phenotype extraction and HPO mapping, and review the ranked rare-disease candidates with their evidence. Scores are prioritisation scores, not diagnoses."
        actions={caseData && <Link to="/reports" className="ui-btn-secondary"><span className="material-symbols-outlined text-[18px]" aria-hidden="true">description</span>Create report</Link>} />

      <div className="flex flex-col gap-4">
        <ClinicalInputSection inputText={inputText} setInputText={setInputText} onRunDiagnosis={(t) => runDiagnosis(t)}
          isLoading={isLoading} sampleCases={SAMPLE_CASES} />

        {error && <ErrorAlert onRetry={() => runDiagnosis()}>{error}</ErrorAlert>}

        {caseData?.extracted_phenotypes?.length > 0 && <ExtractionPanel caseData={caseData} />}

        {reasoningStatus && (reasoningStatus.status === 'error' || reasoningStatus.fallback) && (
          <div className="ui-alert-warn" role="status">
            Language-model explanation unavailable ({(reasoningStatus.status || 'error').replace('_', ' ')}
            {reasoningStatus.reason ? `: ${reasoningStatus.reason}` : ''}). Deterministic evidence shown instead; it is not model output.
          </div>
        )}

        <section aria-labelledby="candidates-title" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="candidates-title" className="ui-section-title">Ranked candidates</h2>
            {cands.length > 0 && <span className="ui-chip-info">{cands.length}</span>}
            {cands.length > 0 && (
              <Link to="/differential" className="ml-auto ui-btn-ghost py-1">
                <span className="material-symbols-outlined text-[18px]" aria-hidden="true">balance</span>Compare in differential view
              </Link>
            )}
          </div>
          {cands.length > 0 ? (
            cands.map((cand) => (
              <EvidenceCards key={cand.disease_id} candidate={cand} onExplain={explainCandidates} isExplaining={isExplaining}
                explanation={explanations[cand.disease_id]} />
            ))
          ) : (
            <EmptyState icon="clinical_notes" title={isLoading ? 'Running the diagnostic pipeline…' : 'No diagnosis run yet'}>
              {isLoading ? 'Extracting phenotypes, mapping to HPO, retrieving and ranking candidates.'
                : 'Choose a sample case or enter clinical text above, then run the diagnostic prioritisation. Results appear here only after a real run.'}
            </EmptyState>
          )}
        </section>
      </div>
    </>
  );
}
