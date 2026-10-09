import React, { useState } from 'react';
import { runCounterfactualScenario } from '../api/client';

const SAMPLE_CASE_TEXT = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.";
const fmt = (v, d = 4) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));
const fmtDelta = (v) => (v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${Number(v).toFixed(4)}`);

function Displacement({ row }) {
  if (row.presence === 'entered_list') return <span className="px-space-xs py-0.5 rounded-full bg-secondary-fixed text-on-secondary-fixed font-label-sm font-bold">entered list</span>;
  if (row.presence === 'left_list') return <span className="px-space-xs py-0.5 rounded-full bg-surface-container text-on-surface-variant font-label-sm font-bold">not in scenario list</span>;
  const d = row.rank_displacement;
  if (d > 0) return <span className="px-space-xs py-0.5 rounded-full bg-accent-sage/20 text-accent-sage font-label-sm font-bold">↑ up {d}</span>;
  if (d < 0) return <span className="px-space-xs py-0.5 rounded-full bg-error-container text-on-error-container font-label-sm font-bold">↓ down {Math.abs(d)}</span>;
  return <span className="px-space-xs py-0.5 rounded-full bg-surface-container text-on-surface-variant font-label-sm font-semibold">— unchanged</span>;
}

const ORIGIN = {
  observed: { label: 'observed', cls: 'bg-secondary-fixed/60 text-on-secondary-fixed' },
  hypothetical_added: { label: 'hypothetical · added', cls: 'bg-tertiary-fixed text-on-tertiary-fixed' },
  hypothetical_modified: { label: 'hypothetical · modified', cls: 'bg-tertiary-fixed text-on-tertiary-fixed' },
};

export default function CounterfactualView({ caseId, clinicalText = SAMPLE_CASE_TEXT }) {
  const [baselineText, setBaselineText] = useState(clinicalText || SAMPLE_CASE_TEXT);
  const [activeCaseId, setActiveCaseId] = useState(caseId || null);
  const [ops, setOps] = useState([]);           // the full, ordered, reversible operation history
  const [result, setResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [addInput, setAddInput] = useState('');
  const [modTarget, setModTarget] = useState('');
  const [modInput, setModInput] = useState('');

  const run = async (nextOps, useCase = activeCaseId) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await runCounterfactualScenario({
        case_id: useCase || undefined,
        clinical_text: useCase ? undefined : baselineText,
        operations: nextOps.map((o) => ({ op: o.op, phenotype: o.phenotype, replacement: o.replacement })),
        top_k: 5
      });
      setResult(data);
      setOps(nextOps);
      if (data.case_id) setActiveCaseId(data.case_id);   // the baseline is now a stored case owned by this user
    } catch (err) {
      setError(err.message || 'Scenario failed');
    } finally {
      setIsLoading(false);
    }
  };

  const loadBaseline = () => {
    if (ops.length && !window.confirm('Loading a new baseline discards the current hypothetical operations. Continue?')) return;
    setActiveCaseId(null);           // analyse the text shown here, not a different patient's stored case
    setResult(null);
    run([], null);
  };

  const useDashboardCase = () => {
    if (!caseId) return;
    if (ops.length && !window.confirm('Switching to the dashboard case discards the current hypothetical operations. Continue?')) return;
    setActiveCaseId(caseId);
    setBaselineText(clinicalText);
    setResult(null);
    run([], caseId);
  };

  const addOp = (op) => run([...ops, op]);
  const undoLast = () => run(ops.slice(0, -1));
  const removeOpAt = (i) => run(ops.filter((_, k) => k !== i));
  const reset = () => { if (!ops.length || window.confirm('Reset to the baseline case? All hypothetical operations will be cleared (the saved case is unchanged).')) run([]); };

  const submitAdd = (e) => { e.preventDefault(); if (addInput.trim()) { addOp({ op: 'add', phenotype: addInput.trim() }); setAddInput(''); } };
  const submitModify = (e) => {
    e.preventDefault();
    if (modTarget && modInput.trim()) { addOp({ op: 'modify', phenotype: modTarget, replacement: modInput.trim() }); setModInput(''); setModTarget(''); }
  };
  const applySuggestion = (i, hpoId) => {
    const next = ops.map((o, k) => (k === i ? { ...o, [o.op === 'modify' ? 'replacement' : 'phenotype']: hpoId } : o));
    run(next);
  };

  const rows = result?.comparison || [];
  const shown = rows.filter((r) => (r.baseline.rank && r.baseline.rank <= 5) || (r.counterfactual.rank && r.counterfactual.rank <= 5));

  return (
    <div className="flex flex-col gap-space-xl">
      {/* Baseline input */}
      <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30">
        <h3 className="font-title-md text-primary font-bold mb-space-xs flex items-center gap-space-2xs">
          <span className="material-symbols-outlined text-secondary text-[20px]">science</span>
          Baseline case (observed)
        </h3>
        <textarea rows={2} value={baselineText} onChange={(e) => { setBaselineText(e.target.value); setActiveCaseId(null); }}
          className="w-full p-space-sm rounded-xl bg-surface border border-outline-variant text-body-md focus:outline-none focus:ring-2 focus:ring-secondary" />
        <div className="flex flex-wrap items-center gap-space-xs mt-space-xs">
          <button onClick={loadBaseline} disabled={isLoading || !baselineText.trim()}
            className="px-space-md py-space-xs rounded-xl bg-primary text-on-primary font-label-md font-bold disabled:opacity-50 flex items-center gap-space-2xs">
            <span className="material-symbols-outlined text-[18px]">{isLoading ? 'progress_activity' : 'play_arrow'}</span>
            {result ? 'Reload baseline from this text' : 'Run baseline'}
          </button>
          {caseId && activeCaseId !== caseId && (
            <button onClick={useDashboardCase} disabled={isLoading} className="px-space-md py-space-xs rounded-xl bg-surface-container text-primary font-label-md font-bold">
              Use the dashboard case
            </button>
          )}
          <span className="text-label-sm text-on-surface-variant">The baseline is never modified. All changes below act on a copy.</span>
        </div>
      </div>

      {error && <div className="p-space-md rounded-xl bg-error-container text-on-error-container font-label-md">{error}</div>}

      {!result && !error && !isLoading && (
        <div className="p-space-3xl text-center text-on-surface-variant bg-surface-container-lowest rounded-2xl border border-outline-variant/30">
          <span className="material-symbols-outlined text-[56px] text-secondary mb-space-xs">compare_arrows</span>
          <h3 className="font-title-lg text-primary font-bold">No scenario yet</h3>
          <p className="font-body-md mt-1 max-w-md mx-auto">Run the baseline, then add, remove or modify a phenotype to see how the real ranking pipeline responds.</p>
        </div>
      )}
      {isLoading && !result && <div className="p-space-lg rounded-xl bg-surface-container-low text-on-surface-variant">Running the retrieval and ranking pipeline…</div>}

      {result && (
        <>
          <div className="p-space-sm rounded-xl bg-tertiary-fixed text-on-tertiary-fixed font-bold text-label-md flex items-center gap-space-xs">
            <span className="material-symbols-outlined text-[18px]">warning</span>
            {result.scenario_label}{ops.length === 0 ? ' — no operations applied yet (baseline = scenario)' : ''}
            {isLoading && <span className="ml-auto font-normal">recomputing…</span>}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
            {/* Phenotype sets */}
            <div className="lg:col-span-7 bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30 flex flex-col gap-space-sm">
              <div>
                <span className="font-label-md text-on-surface-variant font-bold block mb-1">Baseline phenotypes (observed)</span>
                <div className="flex flex-wrap gap-space-xs">
                  {result.baseline_phenotypes.map((h) => (
                    <span key={h.hpo_id} className="px-space-sm py-space-xs rounded-xl bg-secondary-fixed/60 text-on-secondary-fixed font-code-metric text-label-sm font-bold">{h.name} <span className="opacity-60">{h.hpo_id}</span></span>
                  ))}
                </div>
              </div>
              <div>
                <span className="font-label-md text-on-surface-variant font-bold block mb-1">Hypothetical phenotypes (click ✕ to hypothetically remove)</span>
                <div className="flex flex-wrap gap-space-xs">
                  {result.hypothetical_phenotypes.length === 0 && <span className="text-body-sm text-on-surface-variant">Empty set.</span>}
                  {result.hypothetical_phenotypes.map((h) => (
                    <span key={h.hpo_id} className={`inline-flex items-center gap-space-3xs px-space-sm py-space-xs rounded-xl font-code-metric text-label-sm font-bold ${(ORIGIN[h.origin] || ORIGIN.observed).cls}`}>
                      {h.name} <span className="opacity-60">{h.hpo_id}</span>
                      <span className="text-[9px] uppercase opacity-80">{(ORIGIN[h.origin] || ORIGIN.observed).label}</span>
                      <button title="Hypothetically remove" disabled={isLoading} onClick={() => addOp({ op: 'remove', phenotype: h.hpo_id })} className="material-symbols-outlined text-[14px] text-error">cancel</button>
                      <button title="Hypothetically modify" disabled={isLoading} onClick={() => setModTarget(h.hpo_id)} className="material-symbols-outlined text-[14px]">edit</button>
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Controls */}
            <div className="lg:col-span-5 bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30 flex flex-col gap-space-sm">
              <form onSubmit={submitAdd} className="flex gap-space-xs">
                <input value={addInput} onChange={(e) => setAddInput(e.target.value)} placeholder="Add: phenotype text or HP:0001251"
                  className="flex-1 p-space-xs rounded-xl bg-surface border border-outline-variant text-body-sm focus:outline-none focus:ring-2 focus:ring-secondary" />
                <button type="submit" disabled={isLoading || !addInput.trim()} className="px-space-md rounded-xl bg-primary text-on-primary font-label-md font-bold disabled:opacity-50">Add</button>
              </form>
              <form onSubmit={submitModify} className="flex flex-col gap-space-xs">
                <select value={modTarget} onChange={(e) => setModTarget(e.target.value)} className="p-space-xs rounded-xl bg-surface border border-outline-variant text-body-sm">
                  <option value="">Modify: choose the term to replace…</option>
                  {result.hypothetical_phenotypes.map((h) => <option key={h.hpo_id} value={h.hpo_id}>{h.name} ({h.hpo_id})</option>)}
                </select>
                <div className="flex gap-space-xs">
                  <input value={modInput} onChange={(e) => setModInput(e.target.value)} placeholder="Replacement text or HPO id"
                    className="flex-1 p-space-xs rounded-xl bg-surface border border-outline-variant text-body-sm" />
                  <button type="submit" disabled={isLoading || !modTarget || !modInput.trim()} className="px-space-md rounded-xl bg-primary text-on-primary font-label-md font-bold disabled:opacity-50">Replace</button>
                </div>
              </form>
              <div className="flex gap-space-xs">
                <button onClick={undoLast} disabled={isLoading || !ops.length} className="px-space-md py-space-xs rounded-xl bg-surface-container text-primary font-label-md font-bold disabled:opacity-50">Undo last</button>
                <button onClick={reset} disabled={isLoading || !ops.length} className="px-space-md py-space-xs rounded-xl bg-surface-container text-secondary font-label-md font-bold disabled:opacity-50">Reset to baseline</button>
              </div>
            </div>
          </div>

          {/* Operation history */}
          {result.operations.length > 0 && (
            <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30">
              <h4 className="font-label-md text-primary font-bold mb-space-xs">Operation history</h4>
              <ol className="flex flex-col gap-space-xs">
                {result.operations.map((o, i) => (
                  <li key={i} className="p-space-xs rounded-lg bg-surface-container-low text-body-sm flex flex-wrap items-center gap-space-xs">
                    <span className="font-code-metric font-bold">{i + 1}. {o.op}</span>
                    <span>{o.input}{o.replacement_input ? ` → ${o.replacement_input}` : ''}</span>
                    <span className={`px-space-xs py-0.5 rounded text-[10px] font-bold ${o.applied ? 'bg-secondary-fixed/60 text-on-secondary-fixed' : 'bg-error-container text-on-error-container'}`}>
                      {o.applied ? 'applied' : `NOT applied: ${o.status}${o.resolution?.reason ? ' (' + o.resolution.reason + ')' : ''}`}
                    </span>
                    {o.resolution?.hpo_id && <span className="font-code-metric text-[10px] text-on-surface-variant">{o.resolution.hpo_id} · {o.resolution.name} · {o.resolution.matching_method} ({fmt(o.resolution.score, 2)})</span>}
                    {o.resolution?.suggestions?.length > 0 && (
                      <span className="text-[11px] text-on-surface-variant">choose a valid term:{' '}
                        {o.resolution.suggestions.slice(0, 3).map((sg) => (
                          <button key={sg.hpo_id} onClick={() => applySuggestion(i, sg.hpo_id)} className="underline text-secondary font-semibold mr-1">{sg.name || sg.term} ({sg.hpo_id})</button>
                        ))}
                      </span>
                    )}
                    <button onClick={() => removeOpAt(i)} disabled={isLoading} className="ml-auto text-[11px] text-error font-semibold">revert this step</button>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Side-by-side rankings */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-lg">
            {[['Baseline ranking (observed)', result.baseline_ranking], ['Counterfactual ranking (hypothetical)', result.counterfactual_ranking]].map(([title, list]) => (
              <div key={title} className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30">
                <h4 className="font-title-sm text-primary font-bold mb-space-xs">{title}</h4>
                {list.length === 0 ? <p className="text-body-sm text-on-surface-variant">No candidates (empty phenotype set).</p> : (
                  <ol className="flex flex-col gap-space-2xs text-body-sm">
                    {list.map((c, i) => (
                      <li key={c.disease_id} className="flex justify-between gap-space-xs"><span><b>#{i + 1}</b> {c.disease_name}</span><span className="font-code-metric">{fmt(c.final_score)}</span></li>
                    ))}
                  </ol>
                )}
              </div>
            ))}
          </div>

          {/* Comparison table */}
          <div className="bg-surface-container-lowest rounded-2xl p-space-xl shadow-sm border border-outline-variant/30">
            <h3 className="font-title-lg text-primary font-bold mb-space-xs">Rank and score-component comparison</h3>
            <p className="text-label-sm text-on-surface-variant mb-space-sm">{result.rank_displacement_convention} Ranks are over the top {result.pipeline.compare_depth}; “not in scenario list” is not an exclusion.</p>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-body-sm">
                <thead>
                  <tr className="border-b border-outline-variant/30 text-label-md text-on-surface-variant uppercase font-bold bg-surface-container-low/50">
                    <th className="py-space-xs px-space-sm">Candidate</th><th className="px-space-sm text-center">Baseline</th><th className="px-space-sm text-center">Scenario</th>
                    <th className="px-space-sm text-center">Displacement</th><th className="px-space-sm text-right">Δ retrieval</th><th className="px-space-sm text-right">Δ phenotype</th>
                    <th className="px-space-sm text-right">Δ population</th><th className="px-space-sm text-right">Δ final</th><th className="px-space-sm">Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((r) => {
                    const ev = result.evidence_changes?.[r.disease_id];
                    return (
                      <tr key={r.disease_id} className="border-b border-outline-variant/10 align-top">
                        <td className="py-space-sm px-space-sm font-bold text-primary">{r.disease_name}<span className="block font-code-metric text-[10px] text-on-surface-variant font-normal">{r.disease_id} · {r.magnitude}</span></td>
                        <td className="px-space-sm text-center font-code-metric">{r.baseline.rank ? `#${r.baseline.rank}` : '—'}<span className="block text-[10px]">{fmt(r.baseline.final_score)}</span></td>
                        <td className="px-space-sm text-center font-code-metric font-bold text-secondary">{r.counterfactual.rank ? `#${r.counterfactual.rank}` : '—'}<span className="block text-[10px]">{fmt(r.counterfactual.final_score)}</span></td>
                        <td className="px-space-sm text-center"><Displacement row={r} /></td>
                        <td className="px-space-sm text-right font-code-metric">{fmtDelta(r.deltas.retrieval_score)}</td>
                        <td className="px-space-sm text-right font-code-metric">{fmtDelta(r.deltas.phenotype_score)}</td>
                        <td className="px-space-sm text-right font-code-metric">{fmtDelta(r.deltas.population_contribution)}</td>
                        <td className="px-space-sm text-right font-code-metric font-bold">{fmtDelta(r.deltas.final_score)}</td>
                        <td className="px-space-sm text-[11px] text-on-surface-variant">
                          {ev ? (<>
                            {ev.baseline_label || '—'} → {ev.counterfactual_label || '—'}
                            {ev.matched_hpo_gained.length > 0 && <span className="block">matched +{ev.matched_hpo_gained.join(', ')}</span>}
                            {ev.matched_hpo_lost.length > 0 && <span className="block">matched −{ev.matched_hpo_lost.join(', ')}</span>}
                          </>) : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-on-surface-variant mt-space-xs">{result.magnitude_rule}</p>
          </div>

          {/* Explanations */}
          <div className="bg-surface-container-lowest rounded-2xl p-space-xl shadow-sm border border-outline-variant/30 flex flex-col gap-space-sm">
            <h3 className="font-title-lg text-primary font-bold">What changed (derived from the computed values)</h3>
            {result.explanations.map((t, i) => (
              <p key={i} className="p-space-sm rounded-xl bg-surface-container-low text-body-sm text-on-surface">{t}</p>
            ))}
            <p className="text-label-sm text-on-surface-variant">{result.population_note}</p>
            <div className="p-space-sm rounded-xl bg-surface-container text-on-surface-variant text-label-sm flex items-center gap-space-xs border border-outline-variant/20">
              <span className="material-symbols-outlined text-secondary text-[18px]">info</span>
              <span>{result.disclaimer} Scenario id: {result.scenario_id} (held in memory only).</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
