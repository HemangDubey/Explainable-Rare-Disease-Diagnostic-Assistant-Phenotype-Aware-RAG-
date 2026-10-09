// Saved cases: the signed-in user's own stored cases (owner-scoped list, no note text), with links into the modules and deletion.
import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { deleteCase, getTwinCases } from '../api/client';
import { EmptyState, ErrorAlert, LoadingState, PageHeader } from '../app/ui';

const ORIGIN = { diagnosis: 'Diagnosis', counterfactual_baseline: 'Counterfactual baseline', scribe: 'Clinical Scribe' };

export default function CasesPage() {
  const [cases, setCases] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const load = useCallback(() => {
    setError(null);
    getTwinCases().then((d) => setCases(d.cases)).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const remove = async (id) => {
    setBusy(id);
    try {
      await deleteCase(id);
      setCases((cs) => cs.filter((c) => c.case_id !== id));
    } catch (e) {
      setError(`Could not delete case ${id}: ${e.message}`);
    } finally {
      setBusy(null);
      setConfirm(null);
    }
  };

  return (
    <>
      <PageHeader title="Saved Cases"
        description="Cases stored in your account. Only you can see them. Deleting a case also deletes its counterfactual scenarios and reports."
        actions={<button type="button" onClick={load} className="ui-btn-secondary"><span className="material-symbols-outlined text-[18px]" aria-hidden="true">refresh</span>Refresh</button>} />
      {error && <div className="mb-3"><ErrorAlert onRetry={load}>{error}</ErrorAlert></div>}
      {!cases && !error && <LoadingState label="Loading your cases…" />}
      {cases && !cases.length && (
        <EmptyState icon="folder_open" title="No saved cases yet" action={<Link to="/dashboard" className="ui-btn-primary">Run a diagnosis</Link>}>
          Every diagnosis you run is saved to your account and appears here.
        </EmptyState>
      )}
      {cases && cases.length > 0 && (
        <div className="ui-card overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead className="bg-slate-50 text-left text-ink-muted">
              <tr>
                <th className="px-4 py-2.5 font-semibold">Case</th>
                <th className="px-4 py-2.5 font-semibold">Created</th>
                <th className="px-4 py-2.5 font-semibold">Origin</th>
                <th className="px-4 py-2.5 font-semibold">Findings</th>
                <th className="px-4 py-2.5 font-semibold">Top candidate</th>
                <th className="px-4 py-2.5 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.case_id} className="border-t border-line align-middle">
                  <td className="px-4 py-2.5 font-mono text-[12px] text-ink">{c.case_id}</td>
                  <td className="px-4 py-2.5 text-ink-muted whitespace-nowrap">{new Date(c.created_at).toLocaleString()}</td>
                  <td className="px-4 py-2.5"><span className="ui-chip-neutral">{ORIGIN[c.origin] || c.origin}</span></td>
                  <td className="px-4 py-2.5">{c.n_findings}</td>
                  <td className="px-4 py-2.5 max-w-[22rem] truncate" title={c.top_candidate || ''}>
                    {c.top_candidate || <span className="text-ink-muted">not ranked</span>}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex justify-end gap-1.5">
                      <Link to={`/digital-twin?case=${encodeURIComponent(c.case_id)}`} className="ui-btn-secondary py-1">Open in Digital Twin</Link>
                      {confirm === c.case_id ? (
                        <>
                          <button type="button" disabled={busy === c.case_id} onClick={() => remove(c.case_id)} className="ui-btn py-1 bg-danger text-white hover:bg-danger/90">
                            {busy === c.case_id ? 'Deleting…' : 'Confirm delete'}
                          </button>
                          <button type="button" onClick={() => setConfirm(null)} className="ui-btn-ghost py-1">Cancel</button>
                        </>
                      ) : (
                        <button type="button" onClick={() => setConfirm(c.case_id)} className="ui-btn-ghost py-1 text-danger" aria-label={`Delete case ${c.case_id}`}>
                          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">delete</span>
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
