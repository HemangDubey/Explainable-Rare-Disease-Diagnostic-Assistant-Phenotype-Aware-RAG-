// Counterfactual twin: edits a COPY of the case's phenotype set and asks the existing backend scenario endpoint to re-rank.
// Rankings, score differences and explanations are the backend's; this component only collects operations and displays the result.
import React, { useState } from 'react';
import { getScenario, mapTwinRegions, runTwinScenario } from '../../api/client';

const fmt = (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(3));
const signed = (v) => (v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${Number(v).toFixed(3)}`);

// Turns a backend scenario into the hypothetical phenotype changes the 3D views draw (regions come from the same backend mapping).
export async function hypotheticalChanges(result) {
  const added = (result.hypothetical_phenotypes || []).filter((t) => t.origin === 'hypothetical_added' || t.origin === 'hypothetical_modified')
    .map((t) => ({ op: 'added', hpo_id: t.hpo_id, name: t.name }));
  const removed = [];
  for (const o of result.operations || []) {
    if (!o.applied) continue;
    if (o.removed) removed.push({ op: 'removed', hpo_id: o.removed.hpo_id, name: o.removed.name });
    if (o.original) removed.push({ op: 'removed', hpo_id: o.original.hpo_id, name: o.original.name });
  }
  const all = [...added, ...removed];
  if (!all.length) return [];
  const { regions } = await mapTwinRegions([...new Set(all.map((x) => x.hpo_id))]);
  return all.map((x) => ({ ...x, regions: regions[x.hpo_id] || [] }));
}

export default function CounterfactualTwin({ caseId, findings, scenarios = [], result, onResult, onReset, busy, setBusy }) {
  const [ops, setOps] = useState([]);
  const [kind, setKind] = useState('add');
  const [text, setText] = useState('');
  const [target, setTarget] = useState('');
  const [error, setError] = useState(null);
  const terms = [];
  (findings || []).forEach((f) => { if (f.hpo_id && !terms.some((t) => t.hpo_id === f.hpo_id)) terms.push({ hpo_id: f.hpo_id, name: f.hpo_label }); });

  const addOp = () => {
    setError(null);
    if (kind === 'add' && text.trim()) setOps((o) => [...o, { op: 'add', phenotype: text.trim() }]);
    else if (kind === 'remove' && target) setOps((o) => [...o, { op: 'remove', phenotype: target }]);
    else if (kind === 'modify' && target && text.trim()) setOps((o) => [...o, { op: 'modify', phenotype: target, replacement: text.trim() }]);
    else return;
    setText('');
  };

  const show = async (res) => {
    const changes = await hypotheticalChanges(res);
    onResult(res, changes);
  };

  const run = async () => {
    if (!ops.length) return;
    setBusy(true);
    setError(null);
    try {
      await show(await runTwinScenario(caseId, ops));
    } catch (e) {
      setError(e.message || 'Scenario failed');
    } finally {
      setBusy(false);
    }
  };

  const reopen = async (id) => {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const res = await getScenario(id);
      setOps((res.operations || []).map((o) => ({ op: o.op, phenotype: o.input, ...(o.replacement_input ? { replacement: o.replacement_input } : {}) })));
      await show(res);
    } catch (e) {
      setError(e.message || 'Could not reopen the scenario');
    } finally {
      setBusy(false);
    }
  };

  const reset = () => { setOps([]); setText(''); setTarget(''); setError(null); onReset(); };
  const nameOf = (id) => (terms.find((t) => t.hpo_id === id) || {}).name || id;

  return (
    <div className="flex flex-col gap-2 text-xs">
      <div className="flex items-center gap-2">
        <span className="text-on-surface-variant">Changes a copy of this case's phenotypes and re-runs the real ranking. The stored case is not modified.</span>
      </div>
      <div className="flex flex-wrap gap-1.5 items-center">
        <select value={kind} onChange={(e) => setKind(e.target.value)} className="border border-outline-variant rounded px-1.5 py-1 bg-white" aria-label="Operation">
          <option value="add">Add phenotype</option>
          <option value="remove">Remove phenotype</option>
          <option value="modify">Modify phenotype</option>
        </select>
        {kind !== 'add' && (
          <select value={target} onChange={(e) => setTarget(e.target.value)} className="border border-outline-variant rounded px-1.5 py-1 bg-white max-w-[13rem]" aria-label="Phenotype in this case">
            <option value="">Phenotype in this case…</option>
            {terms.map((t) => <option key={t.hpo_id} value={t.hpo_id}>{t.name} ({t.hpo_id})</option>)}
          </select>
        )}
        {kind !== 'remove' && (
          <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') addOp(); }}
            placeholder={kind === 'add' ? 'HPO id or phenotype text' : 'Replacement (HPO id or text)'}
            className="border border-outline-variant rounded px-1.5 py-1 bg-white flex-1 min-w-[10rem]" aria-label="Phenotype" maxLength={200} />
        )}
        <button type="button" onClick={addOp} className="px-2 py-1 rounded border border-secondary text-secondary hover:bg-secondary/10">Queue</button>
      </div>
      {ops.length > 0 && (
        <ol className="flex flex-wrap gap-1">
          {ops.map((o, i) => (
            <li key={i} className="px-1.5 py-0.5 rounded bg-fuchsia-50 border border-fuchsia-200 text-fuchsia-900">
              {i + 1}. {o.op} {o.op === 'add' ? o.phenotype : nameOf(o.phenotype)}{o.replacement ? ` → ${o.replacement}` : ''}
            </li>
          ))}
        </ol>
      )}
      <div className="flex flex-wrap gap-1.5">
        <button type="button" disabled={!ops.length || busy} onClick={run}
          className="px-3 py-1 rounded bg-secondary text-white disabled:opacity-40">{busy ? 'Running…' : 'Run hypothetical ranking'}</button>
        <button type="button" disabled={!ops.length || busy} onClick={() => setOps((o) => o.slice(0, -1))} className="px-2 py-1 rounded border border-outline-variant disabled:opacity-40">Undo</button>
        <button type="button" disabled={busy} onClick={reset} className="px-2 py-1 rounded border border-outline-variant disabled:opacity-40">Reset to baseline</button>
        {scenarios.length > 0 && (
          <select defaultValue="" onChange={(e) => { reopen(e.target.value); e.target.value = ''; }} className="ml-auto border border-outline-variant rounded px-1.5 py-1 bg-white max-w-[14rem]" aria-label="Reopen a saved scenario">
            <option value="">Reopen saved scenario ({scenarios.length})…</option>
            {scenarios.map((s) => (
              <option key={s.scenario_id} value={s.scenario_id}>
                {new Date(s.created_at).toLocaleString()} · {(s.operations || []).map((o) => `${o.op} ${o.phenotype}`).join(', ').slice(0, 40)}
              </option>
            ))}
          </select>
        )}
      </div>
      {error && <p className="text-error" role="alert">{error}</p>}
      {result && (
        <div className="flex flex-col gap-1.5 border border-fuchsia-200 rounded-md p-2 bg-fuchsia-50/40">
          <div className="flex items-center gap-2 text-[11px]">
            <strong className="text-fuchsia-900">{result.scenario_label || 'HYPOTHETICAL scenario'}</strong>
            <span className="text-on-surface-variant">{result.scenario_id} · saved to this case</span>
          </div>
          <ul className="text-[11px]">
            {(result.operations || []).map((o) => (
              <li key={o.step} className={o.applied ? 'text-on-surface' : 'text-amber-700'}>
                {o.step}. {o.op} “{o.input}”{o.replacement_input ? ` → “${o.replacement_input}”` : ''}: {o.status}
                {o.resolution && o.resolution.hpo_id ? ` (${o.resolution.name || ''} ${o.resolution.hpo_id})` : ''}
              </li>
            ))}
          </ul>
          <p className="text-[10px] text-on-surface-variant">
            “List” = the top {(result.pipeline || {}).display_top_k || 5} shown to the clinician; rows below it come from the backend's comparison depth of {(result.pipeline || {}).compare_depth || '—'}.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead className="text-left text-on-surface-variant">
                <tr><th className="font-normal pr-2">Candidate</th><th className="font-normal pr-2">Baseline</th><th className="font-normal pr-2">Hypothetical</th><th className="font-normal pr-2">Δ final score</th><th className="font-normal">Change</th></tr>
              </thead>
              <tbody>
                {(result.comparison || []).map((d) => (
                  <tr key={d.disease_id} className="border-t border-fuchsia-100">
                    <td className="pr-2 py-0.5 max-w-[14rem] truncate" title={d.disease_name}>{d.disease_name}</td>
                    <td className="pr-2">{d.baseline.rank ? `#${d.baseline.rank} · ${fmt(d.baseline.final_score)}` : 'not in list'}</td>
                    <td className="pr-2">{d.counterfactual.rank ? `#${d.counterfactual.rank} · ${fmt(d.counterfactual.final_score)}` : 'not in list'}</td>
                    <td className="pr-2 font-mono">{signed(d.deltas && d.deltas.final_score)}</td>
                    <td className={d.direction === 'up' ? 'text-teal-700' : d.direction === 'down' ? 'text-rose-700' : 'text-on-surface-variant'}>
                      {d.entered_top_k ? 'entered list' : d.left_top_k ? 'left list' : d.direction === 'up' ? `▲ ${d.rank_displacement}` : d.direction === 'down' ? `▼ ${Math.abs(d.rank_displacement)}` : 'unchanged'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(result.explanations || []).length > 0 && (
            <ul className="list-disc pl-4 text-[11px] text-on-surface-variant">{result.explanations.slice(0, 6).map((e, i) => <li key={i}>{e}</li>)}</ul>
          )}
          <p className="text-[10px] text-on-surface-variant">{result.disclaimer}</p>
        </div>
      )}
    </div>
  );
}
