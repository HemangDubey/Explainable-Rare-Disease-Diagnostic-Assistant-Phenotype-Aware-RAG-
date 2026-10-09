import React, { useState } from 'react';

export default function DifferentialExplorer({ differential, onSelectCandidate }) {
  const [selectedRank, setSelectedRank] = useState(1);

  if (!differential || !differential.top_candidates || differential.top_candidates.length === 0) {
    return (
      <div className="p-space-xl text-center text-on-surface-variant bg-surface-container-lowest rounded-2xl border border-outline-variant/30">
        <span className="material-symbols-outlined text-[48px] text-secondary mb-space-xs">compare_arrows</span>
        <p className="font-title-md">Run a clinical case analysis to view differential comparisons.</p>
      </div>
    );
  }

  const { top_candidates = [], comparisons = [], distinguishing_features = [], summary, disclaimer } = differential;
  const currentCandidate = top_candidates.find(c => c.rank === selectedRank) || top_candidates[0];

  return (
    <div className="flex flex-col gap-space-lg">
      {/* Summary Banner */}
      <div className="p-space-md rounded-2xl bg-secondary-fixed/20 border border-secondary/30 flex items-start gap-space-sm">
        <span className="material-symbols-outlined text-secondary text-[24px]">balance</span>
        <div>
          <h4 className="font-title-md text-primary font-bold">Algorithmic Differential Overview</h4>
          <p className="font-body-md text-on-surface mt-1">{summary}</p>
        </div>
      </div>

      {/* Candidate Selector Tabs */}
      <div className="flex flex-wrap items-center gap-space-xs p-space-xs bg-surface-container-low rounded-xl">
        {top_candidates.map((c) => (
          <button
            key={c.rank}
            onClick={() => {
              setSelectedRank(c.rank);
              if (onSelectCandidate) onSelectCandidate(c);
            }}
            className={`flex items-center gap-space-2xs px-space-md py-space-xs rounded-lg font-label-md transition-all ${
              selectedRank === c.rank
                ? 'bg-primary text-on-primary shadow-sm font-bold'
                : 'text-on-surface hover:bg-surface-container'
            }`}
          >
            <span className="w-5 h-5 rounded-full bg-surface-container-highest text-on-surface text-[11px] flex items-center justify-center font-bold">
              #{c.rank}
            </span>
            <span className="truncate max-w-[160px]">{c.disease_name}</span>
            <span className="font-code-metric text-[11px] opacity-80 font-normal">
              {c.final_score.toFixed(3)}
            </span>
          </button>
        ))}
      </div>

      {/* Candidate Deep Dive Card */}
      <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30 flex flex-col gap-space-md">
        <div className="flex flex-wrap items-center justify-between gap-space-sm">
          <div>
            <div className="flex items-center gap-space-xs">
              <span className="px-space-xs py-0.5 rounded bg-primary-container text-on-primary-container font-bold text-label-sm">
                Rank #{currentCandidate.rank}
              </span>
              <span className="font-code-metric text-label-sm text-on-surface-variant">
                {currentCandidate.disease_id}
              </span>
            </div>
            <h3 className="font-headline-sm text-primary font-bold mt-1">
              {currentCandidate.disease_name}
            </h3>
          </div>

          <div className="text-right">
            <span className="font-label-sm text-on-surface-variant block">Composite Priority Score</span>
            <span className="font-code-metric text-headline-sm font-bold text-primary">
              {currentCandidate.final_score.toFixed(4)}
            </span>
          </div>
        </div>

        {/* Breakdown Meters */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-space-sm">
          <div className="p-space-xs bg-surface-container-low rounded-xl">
            <span className="font-label-sm text-on-surface-variant block">Phenotype Alignment</span>
            <div className="w-full bg-surface-container-highest h-2 rounded-full mt-1 overflow-hidden">
              <div className="bg-primary h-full rounded-full" style={{ width: `${Math.min(currentCandidate.phenotype_score * 100, 100)}%` }}></div>
            </div>
            <span className="font-code-metric text-label-sm font-bold text-primary mt-1 block">
              {currentCandidate.phenotype_score.toFixed(4)}
            </span>
          </div>

          <div className="p-space-xs bg-surface-container-low rounded-xl">
            <span className="font-label-sm text-on-surface-variant block">Retrieval Similarity</span>
            <div className="w-full bg-surface-container-highest h-2 rounded-full mt-1 overflow-hidden">
              <div className="bg-secondary h-full rounded-full" style={{ width: `${Math.min(currentCandidate.retrieval_score * 100, 100)}%` }}></div>
            </div>
            <span className="font-code-metric text-label-sm font-bold text-primary mt-1 block">
              {currentCandidate.retrieval_score.toFixed(4)}
            </span>
          </div>

          <div className="p-space-xs bg-surface-container-low rounded-xl">
            <span className="font-label-sm text-on-surface-variant block">Population evidence</span>
            <span className="font-code-metric text-label-sm font-bold text-primary mt-1 block">
              {currentCandidate.population_contribution == null
                ? '—'
                : `contribution ${currentCandidate.population_contribution >= 0 ? '+' : ''}${currentCandidate.population_contribution.toFixed(4)}`}
            </span>
            <span className="text-[10px] text-on-surface-variant block mt-1">
              {currentCandidate.population_status === 'available'
                ? 'gnomAD evidence available (gene-level, global and South Asian reported separately)'
                : 'Population evidence unavailable for this candidate'}
              {currentCandidate.indian_population_signal == null
                ? ' · IndiGen unavailable (not substituted)'
                : ` · IndiGen signal ${currentCandidate.indian_population_signal.toFixed(3)}`}
            </span>
          </div>

          <div className="p-space-xs bg-surface-container-low rounded-xl">
            <span className="font-label-sm text-on-surface-variant block">Evidence label</span>
            <span className="font-label-md font-bold text-primary mt-1 block">{currentCandidate.evidence_label || '—'}</span>
            <span className="text-[10px] text-on-surface-variant block mt-1">
              completeness {currentCandidate.evidence_completeness == null ? 'unknown' : `${Math.round(currentCandidate.evidence_completeness * 100)}%`}
              {' '}(descriptive, not a probability)
            </span>
          </div>

          <div className="p-space-xs bg-surface-container-low rounded-xl">
            <span className="font-label-sm text-on-surface-variant block">Associated Genetics</span>
            <div className="mt-1 flex flex-wrap gap-1">
              {currentCandidate.associated_genes && currentCandidate.associated_genes.length > 0 ? (
                currentCandidate.associated_genes.map((g, i) => (
                  <span key={i} className="font-code-metric text-[11px] font-bold px-1.5 py-0.5 rounded bg-surface-container">
                    {g}
                  </span>
                ))
              ) : (
                <span className="text-[11px] text-on-surface-variant italic">Unmapped</span>
              )}
            </div>
          </div>
        </div>

        {/* Matched vs Missing Phenotypes */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-space-sm pt-space-xs border-t border-outline-variant/20">
          <div>
            <h5 className="font-label-md font-bold text-primary flex items-center gap-1 mb-1">
              <span className="material-symbols-outlined text-[16px] text-secondary">check_circle</span>
              Matched Patient Phenotypes
            </h5>
            <div className="flex flex-wrap gap-1">
              {currentCandidate.matched_phenotypes.map((p, i) => (
                <span key={i} className="px-space-xs py-0.5 rounded bg-secondary-fixed/30 text-on-secondary-fixed text-label-sm">
                  {p}
                </span>
              ))}
            </div>
          </div>

          <div>
            <h5 className="font-label-md font-bold text-primary flex items-center gap-1 mb-1">
              <span className="material-symbols-outlined text-[16px] text-on-surface-variant">help_outline</span>
              Unverified (annotated to this candidate, not stated in the record)
            </h5>
            <div className="flex flex-wrap gap-1">
              {currentCandidate.missing_phenotypes && currentCandidate.missing_phenotypes.length > 0 ? (
                currentCandidate.missing_phenotypes.slice(0, 4).map((p, i) => (
                  <span key={i} className="px-space-xs py-0.5 rounded bg-surface-container text-on-surface-variant text-label-sm">
                    {p}
                  </span>
                ))
              ) : (
                <span className="text-body-sm text-on-surface-variant italic">None recorded; absence of a listed finding is never inferred</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {currentCandidate.contradictory_evidence?.length > 0 && (
        <div className="p-space-sm rounded-xl bg-error-container/40 text-body-sm text-on-surface">
          <span className="font-bold block">Contradictory evidence</span>
          <ul className="list-disc list-inside">{currentCandidate.contradictory_evidence.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </div>
      )}
      {currentCandidate.uncertainties?.length > 0 && (
        <details className="p-space-sm rounded-xl bg-surface-container-low text-body-sm text-on-surface-variant">
          <summary className="cursor-pointer font-bold text-primary">Uncertainties and sources</summary>
          <ul className="list-disc list-inside mt-space-2xs">{currentCandidate.uncertainties.map((t, i) => <li key={i}>{t}</li>)}</ul>
          {currentCandidate.source_references?.length > 0 && (
            <p className="mt-space-2xs text-label-sm">
              Sources: {currentCandidate.source_references.map((r) => `${r.evidence_id} (${r.source})`).join('; ')}
            </p>
          )}
        </details>
      )}

      {/* Comparative Pairwise Analysis Table */}
      {comparisons.length > 0 && (
        <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30">
          <h4 className="font-title-md text-primary font-bold mb-space-sm flex items-center gap-space-xs">
            <span className="material-symbols-outlined text-secondary text-[20px]">swap_horiz</span>
            Score comparison vs. Rank #1 (not ruled out)
          </h4>
          <div className="divide-y divide-outline-variant/20">
            {comparisons.map((cmp, idx) => (
              <div key={idx} className="py-space-sm flex flex-col md:flex-row md:items-center justify-between gap-space-xs">
                <div>
                  <div className="flex items-center gap-space-2xs">
                    <span className="font-bold text-primary">#{cmp.compared_rank} {cmp.compared_disease}</span>
                    <span className="font-code-metric text-label-sm text-on-surface-variant">
                      (Δ final score vs #1: {cmp.score_delta == null ? '—' : `-${cmp.score_delta.toFixed(4)}`})
                    </span>
                  </div>
                  <ul className="list-disc list-inside text-body-sm text-on-surface-variant mt-1">
                    {cmp.distinguishing_factors.map((f, fi) => (
                      <li key={fi}>{f}</li>
                    ))}
                  </ul>
                </div>

                {cmp.primary_differentiating_phenotypes.length > 0 && (
                  <div className="text-right">
                    <span className="font-label-sm text-on-surface-variant block">Rank #1 Unique Alignment:</span>
                    <span className="font-label-sm text-secondary font-semibold">
                      {cmp.primary_differentiating_phenotypes.join(', ')}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Mandatory Clinical Disclaimer */}
      <div className="p-space-sm rounded-xl bg-surface-container text-label-sm text-on-surface-variant flex items-center gap-space-xs">
        <span className="material-symbols-outlined text-[18px] text-secondary">verified_user</span>
        <span>{disclaimer}</span>
      </div>
    </div>
  );
}
