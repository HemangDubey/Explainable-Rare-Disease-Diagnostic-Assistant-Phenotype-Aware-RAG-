import React, { useState } from 'react';

export default function EvidenceCards({ candidate, onExplain, isExplaining, explanation }) {
  const [expanded, setExpanded] = useState(true);

  if (!candidate) return null;

  const {
    disease_id,
    disease_name,
    rank,
    final_score,
    phenotype_evidence = {},
    retrieval_evidence = {},
    population_evidence = {},
    genes = [],
    evidence_items = []
  } = candidate;

  return (
    <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30 flex flex-col gap-space-md transition-all hover:shadow-md">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-space-sm">
        <div className="flex items-center gap-space-sm">
          <div className="w-9 h-9 rounded-xl bg-primary-container text-on-primary-container font-headline-sm flex items-center justify-center font-bold">
            #{rank}
          </div>
          <div>
            <h3 className="font-title-lg text-title-lg text-primary font-bold flex items-center gap-space-xs">
              {disease_name}
              <span className="font-code-metric text-label-sm font-normal text-on-surface-variant px-space-xs py-0.5 rounded bg-surface-container">
                {disease_id}
              </span>
            </h3>
            <p className="font-body-md text-body-md text-on-surface-variant">
              Priority Composite Score: <span className="font-bold text-primary">{final_score?.toFixed(4)}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-space-xs">
          <button
            onClick={() => onExplain(disease_id)}
            disabled={isExplaining}
            className="inline-flex items-center gap-space-2xs px-space-sm py-space-xs rounded-lg bg-secondary text-on-secondary font-label-md hover:bg-secondary/90 transition-colors shadow-sm disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[18px]">psychology</span>
            <span>{isExplaining ? 'Synthesizing...' : 'Synthesize LLM Explanation'}</span>
          </button>
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-space-xs rounded-lg text-on-surface-variant hover:bg-surface-container transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">
              {expanded ? 'expand_less' : 'expand_more'}
            </span>
          </button>
        </div>
      </div>

      {/* Quick Score Metrics Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-space-xs pt-space-xs border-t border-outline-variant/20">
        <div className="p-space-xs bg-surface-container-low rounded-lg">
          <span className="block font-label-sm text-label-sm text-on-surface-variant">Phenotype Alignment</span>
          <div className="flex items-center justify-between mt-1">
            <span className="font-code-metric text-body-md font-bold text-primary">
              {phenotype_evidence.score !== undefined ? phenotype_evidence.score.toFixed(4) : '0.0000'}
            </span>
            <span className={`px-space-2xs py-0.5 rounded text-[10px] font-bold ${
              phenotype_evidence.confidence === 'High' ? 'bg-primary-fixed text-on-primary-fixed' :
              phenotype_evidence.confidence === 'Moderate' ? 'bg-secondary-fixed text-on-secondary-fixed' :
              'bg-surface-container text-on-surface-variant'
            }`}>
              {phenotype_evidence.confidence || 'Moderate'}
            </span>
          </div>
        </div>

        <div className="p-space-xs bg-surface-container-low rounded-lg">
          <span className="block font-label-sm text-label-sm text-on-surface-variant">Retrieval Sim</span>
          <div className="flex items-center justify-between mt-1">
            <span className="font-code-metric text-body-md font-bold text-primary">
              {retrieval_evidence.score !== undefined ? retrieval_evidence.score.toFixed(4) : '0.0000'}
            </span>
            <span className="px-space-2xs py-0.5 rounded text-[10px] font-bold bg-secondary-fixed/50 text-on-secondary-fixed">
              {retrieval_evidence.confidence || 'High'}
            </span>
          </div>
        </div>

        <div className="p-space-xs bg-surface-container-low rounded-lg">
          <span className="block font-label-sm text-label-sm text-on-surface-variant">Indian Prior (IndiGen)</span>
          <div className="flex items-center justify-between mt-1">
            <span className="font-code-metric text-body-md font-bold text-primary">
              {population_evidence.indian_signal !== undefined ? population_evidence.indian_signal.toFixed(4) : '0.5000'}
            </span>
            <span className={`px-space-2xs py-0.5 rounded text-[10px] font-bold ${
              population_evidence.status === 'available' ? 'bg-primary-fixed text-on-primary-fixed' :
              'bg-surface-container-high text-on-surface-variant'
            }`}>
              {population_evidence.status === 'available' ? 'Available' : 'Neutral Prior'}
            </span>
          </div>
        </div>

        <div className="p-space-xs bg-surface-container-low rounded-lg">
          <span className="block font-label-sm text-label-sm text-on-surface-variant">Global AF (gnomAD)</span>
          <div className="flex items-center justify-between mt-1">
            <span className="font-code-metric text-body-md font-bold text-primary">
              {population_evidence.global_signal !== undefined ? population_evidence.global_signal.toFixed(4) : '0.5000'}
            </span>
            <span className="px-space-2xs py-0.5 rounded text-[10px] font-bold bg-surface-container-high text-on-surface-variant">
              gnomAD SAS
            </span>
          </div>
        </div>
      </div>

      {expanded && (
        <div className="flex flex-col gap-space-sm pt-space-xs border-t border-outline-variant/20">
          {/* Matched Phenotypes Badges */}
          <div>
            <span className="font-label-sm text-label-sm font-semibold text-primary block mb-space-2xs">
              Matched Patient Phenotypes (HPO):
            </span>
            <div className="flex flex-wrap gap-space-2xs">
              {phenotype_evidence.matched_phenotypes && phenotype_evidence.matched_phenotypes.length > 0 ? (
                phenotype_evidence.matched_phenotypes.map((m, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-space-3xs px-space-xs py-0.5 rounded-full bg-secondary-fixed/40 text-on-secondary-fixed text-label-sm font-medium"
                  >
                    <span className="material-symbols-outlined text-[14px]">check_circle</span>
                    {m.name || m.hpo_id} <span className="text-[10px] opacity-75">({m.hpo_id})</span>
                  </span>
                ))
              ) : (
                <span className="text-body-sm text-on-surface-variant italic">
                  No direct patient HPO overlap identified; prioritized via dense embedding similarity.
                </span>
              )}
            </div>
          </div>

          {/* Associated Genes */}
          {genes && genes.length > 0 && (
            <div>
              <span className="font-label-sm text-label-sm font-semibold text-primary block mb-space-2xs">
                Associated Causal Genes:
              </span>
              <div className="flex flex-wrap gap-space-2xs">
                {genes.map((g, idx) => (
                  <span
                    key={idx}
                    className="px-space-xs py-0.5 rounded bg-primary-fixed/40 text-on-primary-fixed font-code-metric text-label-sm font-bold"
                  >
                    {g}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Traceable Evidence Trail Table */}
          {evidence_items && evidence_items.length > 0 && (
            <div className="mt-space-xs">
              <span className="font-label-sm text-label-sm font-semibold text-primary block mb-space-2xs">
                Traceable Multi-Modal Evidence Trail:
              </span>
              <div className="divide-y divide-outline-variant/20 bg-surface rounded-xl overflow-hidden border border-outline-variant/30">
                {evidence_items.map((item, idx) => (
                  <div key={idx} className="p-space-xs flex items-center justify-between text-body-sm">
                    <div className="flex items-center gap-space-xs">
                      <span className={`px-space-2xs py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                        item.category === 'SUPPORTING' ? 'bg-primary-fixed text-on-primary-fixed' :
                        item.category === 'MISSING' ? 'bg-surface-container-high text-on-surface-variant' :
                        'bg-secondary-fixed/40 text-on-secondary-fixed'
                      }`}>
                        {item.category}
                      </span>
                      <span className="text-on-surface font-medium">{item.aspect}:</span>
                      <span className="text-on-surface-variant">{item.description}</span>
                    </div>
                    <span className="font-code-metric text-[11px] text-on-surface-variant/80 pl-space-xs whitespace-nowrap">
                      {item.source}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Rendered LLM Explanation Box */}
          {explanation && explanation.candidate?.disease_id === disease_id && (
            <div className="mt-space-sm p-space-md rounded-xl bg-surface-container-low border border-secondary/30 flex flex-col gap-space-xs">
              <div className="flex items-center gap-space-2xs text-secondary font-bold font-title-sm">
                <span className="material-symbols-outlined text-[18px]">verified</span>
                <span>Ollama LLM Clinical Evidence Synthesis</span>
              </div>
              <p className="font-body-md text-on-surface leading-relaxed italic">
                "{explanation.reasoning_summary}"
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-space-xs mt-space-xs pt-space-xs border-t border-outline-variant/20 text-body-sm">
                <div>
                  <span className="font-bold text-primary block">Phenotypic Justification:</span>
                  <ul className="list-disc list-inside text-on-surface-variant">
                    {explanation.phenotype_reasoning?.supporting?.map((s, i) => <li key={i}>{s}</li>)}
                  </ul>
                </div>
                <div>
                  <span className="font-bold text-primary block">Population & Genetic Insight:</span>
                  <p className="text-on-surface-variant">{explanation.population_reasoning}</p>
                </div>
              </div>

              <div className="mt-space-xs p-space-xs bg-surface-container-highest/60 rounded-lg text-label-sm text-on-surface-variant flex items-center gap-space-2xs">
                <span className="material-symbols-outlined text-[16px] text-secondary">info</span>
                <span>{explanation.limitations?.[0] || 'Decision support only; molecular confirmation required.'}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
