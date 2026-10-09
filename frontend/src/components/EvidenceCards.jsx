import React, { useEffect, useState } from 'react';
import { getIndigenDemoGenes } from '../api/client';
import { DemoBanner, useIndigenDemo } from './twin/indigenDemo';

export default function EvidenceCards({ candidate, onExplain, isExplaining, explanation }) {
  const [expanded, setExpanded] = useState(true);
  const demo = useIndigenDemo();
  const [demoGenes, setDemoGenes] = useState(null);     // synthetic IndiGen demo values (display only, never part of the score)
  const geneKey = ((candidate && candidate.genes) || []).join(',');
  useEffect(() => {
    if (!demo.enabled || !geneKey) { setDemoGenes(null); return undefined; }
    let alive = true;
    setDemoGenes({ status: 'loading' });
    getIndigenDemoGenes(geneKey.split(',')).then((r) => alive && setDemoGenes(r))
      .catch((e) => alive && setDemoGenes({ status: 'error', reason: e.message }));
    return () => { alive = false; };
  }, [demo.enabled, geneKey]);

  if (!candidate) return null;

  const {
    disease_id,
    disease_name,
    rank,
    final_score,
    phenotype_evidence = {},
    retrieval_evidence = {},
    population_evidence = {},
    population = null,
    population_contribution = null,
    baseline_rank = null,
    rank_change = null,
    genes = [],
    evidence_items = [],
    labels = null,
    evidence_completeness = null,
    score_breakdown = null
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
              <span className="ml-space-xs text-[12px] text-on-surface-variant">
                {baseline_rank == null ? '' : rank_change === 0
                  ? '· No rank change from population evidence.'
                  : `· Rank #${baseline_rank} → #${rank} (${rank_change > 0 ? 'promoted' : 'demoted'} by ${Math.abs(rank_change)})`}
              </span>
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
              phenotype_evidence.label === 'Strong phenotype overlap' ? 'bg-primary-fixed text-on-primary-fixed' :
              phenotype_evidence.label === 'Partial phenotype overlap' ? 'bg-secondary-fixed text-on-secondary-fixed' :
              'bg-surface-container text-on-surface-variant'
            }`}>
              {phenotype_evidence.label || 'Unlabelled'}
            </span>
          </div>
        </div>

        <div className="p-space-xs bg-surface-container-low rounded-lg">
          <span className="block font-label-sm text-label-sm text-on-surface-variant">Retrieval score</span>
          <div className="flex items-center justify-between mt-1">
            <span className="font-code-metric text-body-md font-bold text-primary">
              {retrieval_evidence.score !== undefined ? retrieval_evidence.score.toFixed(4) : '0.0000'}
            </span>
            <span className="px-space-2xs py-0.5 rounded text-[10px] font-bold bg-secondary-fixed/50 text-on-secondary-fixed">
              not a probability
            </span>
          </div>
        </div>

        {[
          { key: 'indigen', title: 'Indian Population Evidence', tag: 'IndiGen', missing: 'IndiGen: unavailable — access required',
            ev: population?.indigen, hint: 'Indian-specific evidence requires IndiGen data.' },
          { key: 'sas', title: 'Regional Comparator', tag: 'gnomAD South Asian', missing: 'gnomAD South Asian: unavailable',
            ev: population?.gnomad_south_asian, hint: 'South Asian is not Indian-specific.' },
          { key: 'glo', title: 'Global Baseline', tag: 'gnomAD global', missing: 'gnomAD global: unavailable',
            ev: population?.gnomad_global, hint: null },
        ].filter((t) => !(t.key === 'indigen' && demo.enabled && demoGenes && demoGenes.genes)).map((t) => (
          <div key={t.key} className="p-space-xs bg-surface-container-low rounded-lg">
            <span className="block font-label-sm text-label-sm text-on-surface-variant">{t.title}</span>
            <div className="flex items-center justify-between mt-1">
              <span className="font-code-metric text-body-md font-bold text-primary">
                {t.ev?.status === 'available' && t.ev.caf != null ? t.ev.caf.toExponential(2) : '—'}
              </span>
              <span className={`px-space-2xs py-0.5 rounded text-[10px] font-bold ${
                t.ev?.status === 'available' ? 'bg-primary-fixed text-on-primary-fixed' : 'bg-surface-container-high text-on-surface-variant'
              }`}>
                {t.ev?.status === 'available' ? t.tag : (t.ev?.status || 'unavailable').replace('_', ' ')}
              </span>
            </div>
            <span className="block mt-1 text-[10px] text-on-surface-variant">
              {t.ev?.status === 'available' ? `${t.tag}: cumulative P/LP allele frequency (gene-level)` : t.missing}
            </span>
          </div>
        ))}
        {demo.enabled && demoGenes && (
          <div className="sm:col-span-3 p-space-xs rounded-lg bg-surface-container-low flex flex-col gap-1">
            <span className="flex items-center gap-2 font-label-sm text-label-sm text-on-surface-variant">IndiGen <DemoBanner /></span>
            {demoGenes.status === 'loading' && <span className="text-[11px] text-on-surface-variant">Loading…</span>}
            {demoGenes.status === 'error' && <span className="text-[11px] text-error">Could not be loaded: {demoGenes.reason}</span>}
            {demoGenes.genes && Object.entries(demoGenes.genes).map(([g, v]) => (
              <span key={g} className="text-[11px] text-on-surface">
                <span className="font-mono font-semibold">{g}</span>: {v.status === 'available'
                  ? `cumulative AF ${v.cumulative_af.toExponential(2)} (${v.n_variants} variants)`
                  : `no records (${v.status})`}
              </span>
            ))}
          </div>
        )}
      </div>

      {population && (
        <p className="text-[12px] text-on-surface-variant -mt-space-xs">
          Population contribution to final score:{' '}
          <span className="font-bold text-primary">{population_contribution == null ? '—' : `${population_contribution >= 0 ? '+' : ''}${population_contribution.toFixed(4)}`}</span>
          {' · '}evidence level: {population.level === 'GENE_LEVEL' ? 'gene-level' : population.level}
          {population.signal == null ? ' · no population adjustment applied' : ''}
          {population.sas_vs_global?.status === 'available' ? ` · South Asian vs global log2 ratio ${population.sas_vs_global.log2_ratio.toFixed(2)}` : ''}
          {' · '}Population frequency is shown as evidence; it affects the ranking only if the configured population weight is above 0 (the contribution above is the actual effect). It is not a disease probability.
        </p>
      )}

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
                  No patient HPO term is annotated to this disease in the knowledge base; it was retrieved by semantic similarity only.
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

          {/* Evidence completeness + reproducible score breakdown */}
          {(evidence_completeness || score_breakdown) && (
            <div className="p-space-xs rounded-xl bg-surface-container-low border border-outline-variant/30 text-body-sm text-on-surface-variant">
              {evidence_completeness && (
                <p>
                  <span className="font-bold text-primary">Evidence completeness: </span>
                  {evidence_completeness.fraction != null ? `${Math.round(evidence_completeness.fraction * 100)}%` : 'unknown'}
                  {' '}(available: {evidence_completeness.available?.join(', ') || 'none'}; unavailable: {evidence_completeness.unavailable?.join(', ') || 'none'}; literature: not assessed).
                  {' '}Descriptive only — not a probability and not a calibrated confidence.
                </p>
              )}
              {score_breakdown && (
                <p className="mt-space-2xs">
                  <span className="font-bold text-primary">Score breakdown: </span>
                  base {score_breakdown.base_score?.toFixed(4)} = {score_breakdown.weights?.w_phenotype} × phenotype {score_breakdown.phenotype_score?.toFixed(4)} + {score_breakdown.weights?.w_retrieval} × retrieval {score_breakdown.retrieval_score?.toFixed(4)};
                  {' '}population contribution {score_breakdown.population_contribution == null ? '—' : score_breakdown.population_contribution.toFixed(4)};
                  {' '}final {score_breakdown.final_score?.toFixed(4)} (rank {score_breakdown.rank}).
                  {' '}{score_breakdown.population_note}
                  {score_breakdown.matches_backend === false ? ' ⚠ recomputation does not match the backend value.' : ''}
                </p>
              )}
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
                        item.category === 'CONTRADICTING' ? 'bg-error-container text-on-error-container' :
                        item.category === 'MISSING' ? 'bg-surface-container-high text-on-surface-variant' :
                        'bg-secondary-fixed/40 text-on-secondary-fixed'
                      }`}>
                        {item.category === 'MISSING' ? 'UNVERIFIED / UNAVAILABLE' : item.category}
                      </span>
                      <span className="font-code-metric text-[10px] text-on-surface-variant/70">{item.id}</span>
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

          {/* Grounded explanation (language model) or clearly labelled fallback / provider-unavailable state */}
          {isExplaining && (
            <div className="mt-space-sm p-space-md rounded-xl bg-surface-container-low border border-outline-variant/30 text-body-sm text-on-surface-variant">
              Generating a grounded explanation…
            </div>
          )}
          {!isExplaining && explanation && explanation.candidate_id === disease_id && (
            <div className="mt-space-sm p-space-md rounded-xl bg-surface-container-low border border-secondary/30 flex flex-col gap-space-xs">
              <div className="flex flex-wrap items-center justify-between gap-space-2xs">
                <div className="flex items-center gap-space-2xs text-secondary font-bold font-title-sm">
                  <span className="material-symbols-outlined text-[18px]">{explanation.fallback ? 'rule' : 'verified'}</span>
                  <span>Evidence-grounded explanation</span>
                </div>
                <span className={`px-space-xs py-0.5 rounded text-[10px] font-bold ${
                  explanation.fallback ? 'bg-error-container text-on-error-container' : 'bg-primary-fixed text-on-primary-fixed'
                }`}>
                  {explanation.fallback
                    ? `DETERMINISTIC FALLBACK — language model ${explanation.provider_status === 'ok' ? 'not used' : (explanation.provider_status || 'unavailable').replace('_', ' ')}`
                    : 'AI-generated from the recorded evidence'}
                </span>
              </div>
              {explanation.fallback && (
                <p className="text-label-sm text-on-surface-variant">
                  No language-model text is shown. The statements below are the recorded evidence, copied verbatim from the knowledge base
                  {explanation.fallback_reason ? ` (reason: ${explanation.fallback_reason})` : ''}.
                </p>
              )}
              <p className="font-body-md text-on-surface leading-relaxed">
                {explanation.summary}
                {explanation.summary_evidence_ids?.length > 0 && (
                  <span className="font-code-metric text-[10px] text-on-surface-variant ml-space-2xs">[{explanation.summary_evidence_ids.join(', ')}]</span>
                )}
              </p>
              {explanation.ranking_note && (
                <p className="text-body-sm text-on-surface-variant">
                  <span className="font-bold text-primary">Ranking: </span>{explanation.ranking_note.text}
                </p>
              )}
              {[
                ['supporting_evidence', 'Supporting evidence'],
                ['missing_or_unverified_evidence', 'Missing or unverified (absence not established)'],
                ['contradictory_evidence', 'Contradictory evidence'],
                ['genetic_evidence', 'Genetic evidence'],
                ['population_evidence', 'Population-frequency evidence'],
                ['uncertainties', 'Uncertainties'],
              ].map(([key, title]) => (explanation[key]?.length > 0 ? (
                <div key={key} className="text-body-sm">
                  <span className="font-bold text-primary block">{title}:</span>
                  <ul className="list-disc list-inside text-on-surface-variant">
                    {explanation[key].map((c, i) => (
                      <li key={i}>{c.text} <span className="font-code-metric text-[10px] opacity-70">[{c.evidence_ids.join(', ')}]</span></li>
                    ))}
                  </ul>
                </div>
              ) : null))}
              {explanation.source_references?.length > 0 && (
                <details className="text-label-sm text-on-surface-variant">
                  <summary className="cursor-pointer font-bold text-primary">Source references ({explanation.source_references.length})</summary>
                  <ul className="mt-space-2xs">
                    {explanation.source_references.map((r) => <li key={r.evidence_id}><span className="font-code-metric">{r.evidence_id}</span> — {r.source}</li>)}
                  </ul>
                </details>
              )}
              {explanation.provider?.grounding?.claims_removed > 0 && (
                <p className="text-label-sm text-on-surface-variant">
                  {explanation.provider.grounding.claims_removed} model statement(s) were removed because they could not be tied to the evidence.
                </p>
              )}
              <div className="mt-space-xs p-space-xs bg-surface-container-highest/60 rounded-lg text-label-sm text-on-surface-variant flex items-start gap-space-2xs">
                <span className="material-symbols-outlined text-[16px] text-secondary">info</span>
                <span>{(explanation.limitations || []).join(' ')}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
