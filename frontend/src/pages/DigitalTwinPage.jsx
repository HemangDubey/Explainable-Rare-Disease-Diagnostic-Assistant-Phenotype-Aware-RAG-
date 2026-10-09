// Phase 7R.5 — Clinical Digital Twin Studio. Visualises ONE of the signed-in user's stored cases: NER findings -> HPO -> clinician
// review -> anatomical regions, the ranked candidates, gene-level reference evidence, the evidence network and hypothetical scenarios.
// All clinical content comes from the backend (/api/twin/*, /api/counterfactual/scenario*); this page holds view state only.
import React, { Component, Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useWorkspace } from '../app/WorkspaceContext';
import { getTwinCase, getTwinCases, reviewTwinFindings } from '../api/client';
import { STATE_STYLE, hasWebGL, prefersReducedMotion } from '../components/twin/twinTheme';
import { MANIFEST_URL, buildMarkers } from '../components/twin/twinModel';
import EvidenceNetwork from '../components/twin/EvidenceNetwork';
import GenomicPanel from '../components/twin/GenomicPanel';
import CounterfactualTwin from '../components/twin/CounterfactualTwin';

const TwinCanvas = lazy(() => import('../components/twin/TwinScene'));

const FILTERS = [
  ['all', 'All'], ['confirmed', 'Confirmed'], ['unverified', 'Unverified'], ['uncertain', 'Uncertain'], ['pending', 'Pending'],
  ['negated', 'Absent'], ['relative_finding', 'Relative'], ['unmapped', 'No HPO'],
];
const LAYERS = [['skin', 'Skin'], ['skeleton', 'Skeleton'], ['organs', 'Organs'], ['nervous', 'Nervous']];

class SceneBoundary extends Component {
  constructor(props) { super(props); this.state = { failed: false }; }
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { /* no clinical data or stack is logged */ }
  render() { return this.state.failed ? this.props.fallback('The 3D anatomy asset could not be loaded.') : this.props.children; }
}

// Shown when WebGL or the asset is unavailable. It is a list, explicitly not an anatomical model.
function RegionListFallback({ reason, markers, onSelect }) {
  return (
    <div className="absolute inset-0 overflow-auto p-6 text-slate-200">
      <p className="text-sm font-semibold text-amber-200">{reason}</p>
      <p className="text-xs text-slate-400 mb-3">Fallback view: findings grouped by body region. This is a list, not an anatomical model.</p>
      <ul className="grid sm:grid-cols-2 gap-2">
        {markers.map((m) => (
          <li key={m.region}>
            <button type="button" onClick={() => onSelect(m.region)} className="w-full text-left rounded border border-cyan-500/30 px-3 py-2 hover:border-cyan-300">
              <span className="inline-block w-2 h-2 rounded-full mr-2" style={{ background: (STATE_STYLE[m.state] || {}).color }} />
              <strong className="text-sm">{m.label}</strong>
              <span className="block text-[11px] text-slate-400">{m.items.map((i) => i.hpo_label || i.text).join(', ')}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StateChip({ state, children }) {
  const st = STATE_STYLE[state] || STATE_STYLE.pending;
  return <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-medium ${st.chip}`}>{children || st.label}</span>;
}

function Card({ title, dark, right, children, className = '', id }) {
  return (
    <section id={id} className={`scroll-mt-20 rounded-xl border ${dark ? 'bg-[#071a2e] border-cyan-500/20 text-slate-100' : 'bg-white border-line text-ink shadow-[0_1px_2px_rgba(10,37,64,0.04)]'} p-3 flex flex-col gap-2 min-w-0 ${className}`}>
      <div className="flex items-center gap-2">
        <h2 className={`text-xs font-bold uppercase tracking-wider ${dark ? 'text-cyan-200' : 'text-primary'}`}>{title}</h2>
        <div className="ml-auto flex items-center gap-1">{right}</div>
      </div>
      {children}
    </section>
  );
}

function sentenceAround(text, start, end) {
  if (!text || typeof start !== 'number') return null;
  const a = Math.max(text.lastIndexOf('.', start - 1) + 1, start - 160);
  let b = text.indexOf('.', end);
  b = b === -1 ? Math.min(text.length, end + 160) : Math.min(b + 1, end + 160);
  return { pre: text.slice(a, start).trimStart(), hit: text.slice(start, end), post: text.slice(end, b) };
}

function Inspector({ sel, twin, onClose }) {
  if (!sel || !twin) {
    return <p className="text-xs text-on-surface-variant">Select a body region, finding, candidate or network node to inspect its evidence.</p>;
  }
  const findingById = (id) => twin.findings.find((f) => f.finding_id === id);
  if (sel.kind === 'region') {
    const cat = twin.mapping.region_catalogue[sel.region] || {};
    const fs = twin.findings.filter((f) => f.regions.some((r) => r.region === sel.region));
    return (
      <div className="text-xs flex flex-col gap-1.5">
        <div className="flex items-center"><strong className="text-sm text-primary">{cat.label || sel.region}</strong><button type="button" onClick={onClose} className="ml-auto text-on-surface-variant" aria-label="Close inspector"><span className="material-symbols-outlined text-[16px]" aria-hidden="true">close</span></button></div>
        <p className="text-on-surface-variant">System: {cat.system}{cat.note ? ` · ${cat.note}` : ''}</p>
        {!fs.length && <p className="text-on-surface-variant">No finding of this case maps to this region.</p>}
        {fs.map((f) => {
          const r = f.regions.find((x) => x.region === sel.region);
          return (
            <div key={f.finding_id} className="border border-outline-variant/40 rounded p-1.5">
              <div className="flex items-center gap-1"><StateChip state={f.display_state} /><span className="font-semibold">“{f.text_span}”</span></div>
              <div className="font-mono text-[11px] mt-0.5">{f.hpo_label} · {f.hpo_id}</div>
              <div className="text-[10px] text-on-surface-variant">Mapped via HPO ancestor “{r.via_hpo_name}” ({r.via_hpo_id}) — {r.rule}</div>
            </div>
          );
        })}
      </div>
    );
  }
  if (sel.kind === 'finding') {
    const f = findingById(sel.id);
    if (!f) return null;
    const ctx = sentenceAround(twin.case.clinical_text, f.start, f.end);
    return (
      <div className="text-xs flex flex-col gap-1.5">
        <div className="flex items-center gap-1"><StateChip state={f.display_state} /><button type="button" onClick={onClose} className="ml-auto text-on-surface-variant" aria-label="Close inspector"><span className="material-symbols-outlined text-[16px]" aria-hidden="true">close</span></button></div>
        <strong className="text-sm text-primary">“{f.text_span}”</strong>
        {ctx && <p className="text-on-surface-variant bg-surface-container-low rounded p-1.5">…{ctx.pre}<mark className="bg-secondary-fixed px-0.5">{ctx.hit}</mark>{ctx.post}…</p>}
        <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
          <dt className="text-on-surface-variant">HPO</dt><dd className="font-mono">{f.hpo_id ? `${f.hpo_label} · ${f.hpo_id}` : 'not mapped'}</dd>
          <dt className="text-on-surface-variant">Normalisation</dt><dd>{f.normalization.status}{f.normalization.method ? ` · ${f.normalization.method}` : ''}{typeof f.normalization.score === 'number' ? ` · ${f.normalization.score.toFixed(2)}` : ''}</dd>
          <dt className="text-on-surface-variant">NER confidence</dt><dd>{typeof f.ner_confidence === 'number' ? f.ner_confidence.toFixed(2) : '—'}</dd>
          <dt className="text-on-surface-variant">Status</dt><dd>{f.status} ({f.status_source}){f.verified ? ' · clinician-verified' : ' · not verified'}</dd>
          <dt className="text-on-surface-variant">Assertion</dt><dd>{f.assertion.method}{f.assertion.subject === 'relative' ? ` · subject: relative (${f.assertion.relationship || 'family member'})` : ''}</dd>
          <dt className="text-on-surface-variant">Regions</dt><dd>{f.regions.length ? f.regions.map((r) => r.label).join(', ') : f.hpo_id ? 'unassigned (no organ-system ancestor in the mapping table)' : '—'}</dd>
          <dt className="text-on-surface-variant">Provenance</dt><dd>{f.provenance.ner} → {f.provenance.normalizer}</dd>
        </dl>
      </div>
    );
  }
  if (sel.kind === 'candidate') {
    const c = twin.candidates.find((x) => String(x.disease_id) === String(sel.id));
    if (!c) return null;
    return (
      <div className="text-xs flex flex-col gap-1.5">
        <div className="flex items-center"><strong className="text-sm text-primary">#{c.rank} {c.disease_name}</strong><button type="button" onClick={onClose} className="ml-auto text-on-surface-variant" aria-label="Close inspector"><span className="material-symbols-outlined text-[16px]" aria-hidden="true">close</span></button></div>
        <p className="text-on-surface-variant">{c.disease_id} · {c.label || 'no evidence label'} · {c.score_note}</p>
        <dl className="grid grid-cols-[auto_1fr] gap-x-2 font-mono text-[11px]">
          <dt className="text-on-surface-variant font-sans">Final</dt><dd>{Number(c.final_score).toFixed(3)}</dd>
          <dt className="text-on-surface-variant font-sans">Phenotype</dt><dd>{c.phenotype_score != null ? Number(c.phenotype_score).toFixed(3) : '—'}</dd>
          <dt className="text-on-surface-variant font-sans">Retrieval</dt><dd>{c.retrieval_score != null ? Number(c.retrieval_score).toFixed(3) : '—'}</dd>
          <dt className="text-on-surface-variant font-sans">Population</dt><dd>{c.population_contribution != null ? Number(c.population_contribution).toFixed(3) : '—'}</dd>
        </dl>
        <div><span className="font-semibold">Patient findings matching this disease</span> ({c.matched_hpo.length})
          <ul className="pl-3 list-disc">{c.matched_hpo.map((m) => <li key={m.hpo_id}>{m.name} <span className="font-mono text-[10px]">{m.hpo_id}</span></li>)}</ul>
        </div>
        {c.disease_annotations_not_in_record.length > 0 && (
          <div className="border-l-2 border-amber-400 pl-2">
            <span className="font-semibold">Disease annotations — not patient findings</span>
            <p className="text-[10px] text-on-surface-variant">Phenotypes annotated to this disease that are not recorded for this patient. They are not shown on the body.</p>
            <ul className="pl-3 list-disc">{c.disease_annotations_not_in_record.slice(0, 8).map((m, i) => <li key={i}>{typeof m === 'string' ? m : `${m.name || ''} ${m.hpo_id || ''}`}</li>)}</ul>
          </div>
        )}
        {c.evidence.length > 0 && (
          <div><span className="font-semibold">Evidence ({c.evidence.length})</span>
            <ul className="max-h-32 overflow-auto">{c.evidence.map((e) => <li key={e.id} className="text-[11px]"><span className="font-mono text-secondary">{e.id}</span> {e.text}</li>)}</ul>
          </div>
        )}
      </div>
    );
  }
  if (sel.kind === 'node' || sel.kind === 'edge') {
    const x = sel.data;
    return (
      <div className="text-xs flex flex-col gap-1">
        <div className="flex items-center"><strong className="text-sm text-primary">{sel.kind === 'node' ? x.label : x.label}</strong><button type="button" onClick={onClose} className="ml-auto text-on-surface-variant" aria-label="Close inspector"><span className="material-symbols-outlined text-[16px]" aria-hidden="true">close</span></button></div>
        {sel.kind === 'edge' && <p>{x.source} → {x.target}{x.evidence_id ? ` · evidence ${x.evidence_id}` : ''}</p>}
        <pre className="text-[10px] bg-surface-container-low rounded p-1.5 whitespace-pre-wrap break-words max-h-40 overflow-auto">{JSON.stringify(sel.kind === 'node' ? x.detail : x.detail, null, 1)}</pre>
      </div>
    );
  }
  return null;
}

export default function DigitalTwinPage() {
  const [params, setParams] = useSearchParams();
  const { hash } = useLocation();
  const navigate = useNavigate();
  const { caseData: activeCase } = useWorkspace();
  const caseId = params.get('case');
  const [cases, setCases] = useState(null);
  const [twin, setTwin] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [manifest, setManifest] = useState(null);
  const [manifestError, setManifestError] = useState(null);
  const [filter, setFilter] = useState('all');
  const [sel, setSel] = useState(null);
  const [viewMode, setViewMode] = useState('anatomy');
  const [layers, setLayers] = useState({ skin: true, skeleton: true, organs: true, nervous: true });
  const [preset, setPreset] = useState('front');
  const [zoom, setZoom] = useState('body');
  const [resetToken, setResetToken] = useState(0);
  const [reduced, setReduced] = useState(prefersReducedMotion());
  const [autoRotate, setAutoRotate] = useState(!prefersReducedMotion());
  const [lowPower, setLowPower] = useState(false);
  const [hidden, setHidden] = useState(typeof document !== 'undefined' && document.hidden);
  const [scenario, setScenario] = useState(null);
  const [changes, setChanges] = useState([]);
  const [overlay, setOverlay] = useState(true);
  const [cfBusy, setCfBusy] = useState(false);
  const stageRef = useRef(null);
  const webgl = useMemo(() => hasWebGL(), []);

  useEffect(() => {
    const onVis = () => setHidden(document.hidden);
    document.addEventListener('visibilitychange', onVis);
    let mq;
    try { mq = window.matchMedia('(prefers-reduced-motion: reduce)'); } catch (e) { mq = null; }
    const onMq = (e) => { setReduced(e.matches); if (e.matches) setAutoRotate(false); };
    if (mq && mq.addEventListener) mq.addEventListener('change', onMq);
    return () => { document.removeEventListener('visibilitychange', onVis); if (mq && mq.removeEventListener) mq.removeEventListener('change', onMq); };
  }, []);

  useEffect(() => {
    fetch(MANIFEST_URL).then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setManifest).catch(() => setManifestError('Anatomy asset manifest not found — the 3D model has not been provisioned (see scripts/build_anatomy_asset.py).'));
  }, []);

  useEffect(() => {
    getTwinCases().then((d) => setCases(d.cases)).catch((e) => setError(e.message));
  }, []);

  // No case in the URL: open the workspace's active case if it is one of the user's saved cases, else the most recent one. The
  // #section is kept so sidebar deep links (verification, genomic evidence, network) still scroll to their section.
  useEffect(() => {
    if (caseId || !cases || !cases.length) return;
    const pick = activeCase && cases.some((c) => c.case_id === activeCase.case_id) ? activeCase.case_id : cases[0].case_id;
    navigate({ search: `?case=${encodeURIComponent(pick)}`, hash }, { replace: true });
  }, [caseId, cases]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(async (id, quiet = false) => {
    if (!id) return;
    if (!quiet) setLoading(true);
    setError(null);
    try {
      setTwin(await getTwinCase(id));
    } catch (e) {
      setTwin(null);
      setError(e.httpStatus === 404 ? 'Case not found. It may have been deleted, or it belongs to another account.' : e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setSel(null); setScenario(null); setChanges([]); setFilter('all');
    load(caseId);
  }, [caseId, load]);

  const review = async (updates) => {
    setSaving(true);
    try {
      await reviewTwinFindings(twin.case.case_id, updates);
      await load(twin.case.case_id, true);
    } catch (e) {
      setError(`Review not saved: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const findings = twin ? twin.findings : [];
  const removedIds = new Set(changes.filter((c) => c.op === 'removed').map((c) => c.hpo_id));
  const baseMarkers = useMemo(() => buildMarkers(findings), [twin]); // eslint-disable-line react-hooks/exhaustive-deps
  const mainMarkers = useMemo(() => buildMarkers(findings, overlay ? changes : []), [twin, changes, overlay]); // eslint-disable-line react-hooks/exhaustive-deps
  const hypoMarkers = useMemo(() => buildMarkers(findings.filter((f) => !removedIds.has(f.hpo_id)), changes.filter((c) => c.op === 'added')),
    [twin, changes]); // eslint-disable-line react-hooks/exhaustive-deps
  const shownFindings = findings.filter((f) => filter === 'all' || f.display_state === filter);
  const notPlaced = findings.filter((f) => !f.regions.length);
  const selRegion = sel && sel.kind === 'region' ? sel.region : sel && sel.kind === 'finding' ? ((findings.find((f) => f.finding_id === sel.id) || {}).regions || [])[0]?.region : null;
  const graphSelected = sel ? (sel.kind === 'finding' ? `f:${sel.id}` : sel.kind === 'candidate' ? `d:${sel.id}` : sel.kind === 'node' ? sel.data.id : null) : null;
  const graphHighlight = sel && sel.kind === 'region' ? findings.filter((f) => f.regions.some((r) => r.region === sel.region)).map((f) => `f:${f.finding_id}`) : [];
  const focusGenes = sel && sel.kind === 'candidate' ? ((twin.candidates.find((c) => String(c.disease_id) === String(sel.id)) || {}).genes || []) : [];
  const motionOn = !reduced && !hidden;
  const counts = (twin && twin.case.state_counts) || {};
  const unverifiedPresent = findings.filter((f) => f.display_state === 'unverified');

  useEffect(() => {
    if (!hash || !twin) return;
    const el = document.getElementById(hash.slice(1));
    if (el) el.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
  }, [hash, twin && twin.case.case_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const onSelectRegion = useCallback((region) => setSel(region ? { kind: 'region', region } : null), []);
  const fullscreen = () => {
    const el = stageRef.current;
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen && document.exitFullscreen();
    else el.requestFullscreen && el.requestFullscreen().catch(() => {});
  };
  const goPreset = (p) => { setAutoRotate(false); setPreset(p); };
  const resetView = () => { setAutoRotate(false); setPreset('front'); setZoom('body'); setViewMode('anatomy'); setLayers({ skin: true, skeleton: true, organs: true, nervous: true }); setResetToken((t) => t + 1); setSel(null); };

  const fallback = (reason) => <RegionListFallback reason={reason} markers={mainMarkers} onSelect={onSelectRegion} />;
  const btn = (active) => `px-2 py-1 rounded text-[11px] border ${active ? 'bg-cyan-400/20 border-cyan-300 text-cyan-50' : 'border-cyan-500/25 text-slate-300 hover:border-cyan-400/60'}`;

  return (
    <div className="flex flex-col gap-3 font-body-md text-on-surface">
        {/* Header */}
        <header className="flex flex-wrap items-center gap-3">
          <div>
            <h1 className="text-[22px] leading-7 font-semibold text-ink tracking-tight">Clinical Digital Twin</h1>
            <p className="mt-1 text-[14px] text-ink-muted">Your stored case, visualised from the existing NER → HPO → ranking pipeline. Research prototype — not a diagnosis.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 ml-auto">
            <label className="text-[11px] text-on-surface-variant" htmlFor="twin-case">Case</label>
            <select id="twin-case" value={caseId || ''} onChange={(e) => setParams({ case: e.target.value })}
              className="border border-outline-variant rounded px-2 py-1 text-xs bg-white max-w-[20rem]" disabled={!cases || !cases.length}>
              {!cases && <option>Loading cases…</option>}
              {cases && !cases.length && <option value="">No saved cases</option>}
              {(cases || []).map((c) => (
                <option key={c.case_id} value={c.case_id}>
                  {c.case_id} · {new Date(c.created_at).toLocaleDateString()} · {c.n_findings} findings{c.top_candidate ? ` · top: ${c.top_candidate.slice(0, 28)}` : ''}
                </option>
              ))}
            </select>
            {twin && (
              <span className="flex flex-wrap gap-1">
                {['confirmed', 'unverified', 'uncertain', 'pending', 'negated'].filter((s) => counts[s]).map((s) => (
                  <StateChip key={s} state={s}>{counts[s]} {FILTERS.find((f) => f[0] === s)[1].toLowerCase()}</StateChip>
                ))}
              </span>
            )}
            <span className="flex gap-1 border-l border-outline-variant/50 pl-2" aria-label="Motion controls">
              <button type="button" onClick={() => setAutoRotate((v) => !v)} disabled={reduced}
                className="px-2 py-1 rounded border border-outline-variant text-[11px] disabled:opacity-40">{autoRotate && !reduced ? 'Pause rotation' : 'Rotate'}</button>
              <button type="button" onClick={() => { setReduced((v) => !v); setAutoRotate(false); }} aria-pressed={reduced}
                className={`px-2 py-1 rounded border text-[11px] ${reduced ? 'bg-secondary-fixed border-secondary' : 'border-outline-variant'}`}>Reduce motion</button>
              <button type="button" onClick={() => setLowPower((v) => !v)} aria-pressed={lowPower}
                className={`px-2 py-1 rounded border text-[11px] ${lowPower ? 'bg-secondary-fixed border-secondary' : 'border-outline-variant'}`}>Low-power</button>
            </span>
          </div>
        </header>

        {error && <div className="rounded-lg bg-error-container text-on-error-container text-sm px-3 py-2" role="alert">{error}</div>}
        {cases && !cases.length && (
          <div className="rounded-xl border border-outline-variant/40 bg-surface-container-lowest p-6 text-sm">
            You have no saved cases yet. <Link to="/dashboard" className="text-secondary underline">Run a diagnosis in the workspace</Link> — the case is saved to your account and appears here.
          </div>
        )}

        {(twin || loading) && (
          <div className="grid gap-3 lg:grid-cols-[280px_minmax(0,1fr)] 2xl:grid-cols-[300px_minmax(0,1fr)_330px]">
            {/* Phenotypes */}
            <Card id="twin-phenotypes" title="Patient phenotypes" right={saving && <span className="text-[10px] text-on-surface-variant">saving…</span>} className="lg:max-h-[720px]">
              <div className="flex flex-wrap gap-1">
                {FILTERS.map(([k, l]) => (
                  <button key={k} type="button" onClick={() => setFilter(k)}
                    className={`px-1.5 py-0.5 rounded text-[10px] border ${filter === k ? 'bg-secondary text-white border-secondary' : 'border-outline-variant text-on-surface-variant'}`}>
                    {l}{k !== 'all' && counts[k] ? ` ${counts[k]}` : ''}
                  </button>
                ))}
              </div>
              {unverifiedPresent.length > 0 && (
                <button type="button" disabled={saving} onClick={() => review(unverifiedPresent.map((f) => ({ finding_id: f.finding_id, verified: true })))}
                  className="self-start text-[11px] px-2 py-0.5 rounded border border-teal-400 text-teal-800 bg-teal-50 disabled:opacity-40">
                  Verify all {unverifiedPresent.length} present findings
                </button>
              )}
              <ul className="flex flex-col gap-1 overflow-auto pr-1">
                {loading && <li className="text-xs text-on-surface-variant">Loading case…</li>}
                {twin && !shownFindings.length && <li className="text-xs text-on-surface-variant">No findings in this filter.</li>}
                {shownFindings.map((f) => (
                  <li key={f.finding_id}
                    className={`rounded-lg border p-1.5 text-xs ${sel && sel.kind === 'finding' && sel.id === f.finding_id ? 'border-secondary bg-secondary-fixed/30' : 'border-outline-variant/40'}`}>
                    <button type="button" className="w-full text-left" onClick={() => setSel({ kind: 'finding', id: f.finding_id })}>
                      <div className="flex items-start gap-1.5">
                        <span className={`mt-1 inline-block w-2.5 h-2.5 rounded-full shrink-0 ${f.display_state === 'negated' ? 'border-2 bg-transparent' : ''}`}
                          style={f.display_state === 'negated' ? { borderColor: STATE_STYLE.negated.color } : { background: (STATE_STYLE[f.display_state] || {}).color }} />
                        <span className="min-w-0">
                          <span className={`font-semibold ${f.display_state === 'negated' ? 'line-through text-on-surface-variant' : ''}`}>{f.text_span}</span>
                          <span className="block font-mono text-[10px] text-on-surface-variant truncate">{f.hpo_id ? `${f.hpo_label} · ${f.hpo_id}` : 'no HPO mapping'}</span>
                        </span>
                      </div>
                    </button>
                    <div className="flex flex-wrap items-center gap-1 mt-1 pl-4">
                      <StateChip state={f.display_state} />
                      {f.regions.map((r) => <span key={r.region} className="text-[10px] px-1 rounded bg-surface-container text-on-surface-variant">{r.label}</span>)}
                      {f.hpo_id && (
                        <span className="ml-auto flex items-center gap-1">
                          <select value={f.status} disabled={saving} onChange={(e) => review([{ finding_id: f.finding_id, status: e.target.value }])}
                            className="text-[10px] border border-outline-variant rounded bg-white" aria-label={`Status of ${f.text_span}`}>
                            <option value="present">present</option><option value="negated">absent</option>
                            <option value="uncertain">uncertain</option><option value="pending">pending</option>
                          </select>
                          <label className="inline-flex items-center gap-0.5 text-[10px]">
                            <input type="checkbox" checked={f.verified} disabled={saving} onChange={(e) => review([{ finding_id: f.finding_id, verified: e.target.checked }])} />verified
                          </label>
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
              {twin && notPlaced.length > 0 && (
                <div className="border-t border-outline-variant/40 pt-1.5">
                  <h3 className="text-[11px] font-semibold text-on-surface-variant">Not placed on the body ({notPlaced.length})</h3>
                  <p className="text-[10px] text-on-surface-variant">No HPO mapping, or no organ-system ancestor in the mapping table. Never guessed.</p>
                  <ul className="text-[11px]">
                    {notPlaced.map((f) => (
                      <li key={f.finding_id}><button type="button" className="hover:underline text-left" onClick={() => setSel({ kind: 'finding', id: f.finding_id })}>
                        {f.text_span} <span className="text-on-surface-variant">— {f.hpo_id ? `${f.hpo_label} (unassigned)` : 'unmapped'}</span>
                      </button></li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>

            {/* 3D stage */}
            <section ref={stageRef} className="relative rounded-xl overflow-hidden border border-cyan-500/20 min-h-[520px] lg:h-[720px] bg-[radial-gradient(ellipse_at_50%_35%,#0d3a5c_0%,#071a2e_55%,#030b16_100%)]">
              <div className="absolute top-2 left-2 right-2 z-10 flex flex-wrap gap-1 items-center">
                {[['anatomy', 'Anatomy'], ['systems', 'Systems'], ['skeleton', 'Skeleton']].map(([k, l]) => (
                  <button key={k} type="button" className={btn(viewMode === k)} onClick={() => setViewMode(k)}>{l}</button>
                ))}
                <span className="w-px h-5 bg-cyan-500/30 mx-1" />
                {[['front', 'Front'], ['back', 'Back'], ['left', 'Left'], ['right', 'Right']].map(([k, l]) => (
                  <button key={k} type="button" className={btn(preset === k && !autoRotate)} onClick={() => goPreset(k)}>{l}</button>
                ))}
                <span className="w-px h-5 bg-cyan-500/30 mx-1" />
                {[['body', 'Full body'], ['torso', 'Torso'], ['head', 'Head']].map(([k, l]) => (
                  <button key={k} type="button" className={btn(zoom === k)} onClick={() => setZoom(k)}>{l}</button>
                ))}
                <span className="ml-auto flex gap-1">
                  <button type="button" className={btn(false)} onClick={resetView}>Reset</button>
                  <button type="button" className={btn(false)} onClick={fullscreen} aria-label="Toggle fullscreen"><span className="material-symbols-outlined text-[16px] leading-none" aria-hidden="true">fullscreen</span></button>
                </span>
              </div>
              <div className="absolute top-10 left-2 z-10 flex flex-wrap gap-1">
                {LAYERS.map(([k, l]) => (
                  <label key={k} className="inline-flex items-center gap-1 text-[10px] text-slate-300 bg-slate-950/50 rounded px-1.5 py-0.5 cursor-pointer">
                    <input type="checkbox" className="accent-cyan-400" checked={layers[k]} onChange={() => setLayers((s) => ({ ...s, [k]: !s[k] }))} />{l}
                  </label>
                ))}
                {changes.length > 0 && (
                  <label className="inline-flex items-center gap-1 text-[10px] text-fuchsia-200 bg-fuchsia-950/60 rounded px-1.5 py-0.5 cursor-pointer">
                    <input type="checkbox" className="accent-fuchsia-400" checked={overlay} onChange={() => setOverlay((v) => !v)} />HYPOTHETICAL overlay
                  </label>
                )}
              </div>
              {!webgl ? fallback('3D view unavailable: this browser does not support WebGL.')
                : manifestError ? fallback(manifestError)
                  : manifest && twin ? (
                    <SceneBoundary fallback={fallback}>
                      <Suspense fallback={<div className="absolute inset-0 grid place-items-center text-cyan-100 text-xs">Loading 3D engine…</div>}>
                        <div className="absolute inset-0">
                          <TwinCanvas manifest={manifest} catalogue={twin.mapping.region_catalogue} markers={mainMarkers} viewMode={viewMode} layers={layers}
                            selectedRegion={selRegion} onSelectRegion={onSelectRegion} autoRotate={autoRotate} reducedMotion={reduced} lowPower={lowPower}
                            preset={preset} zoom={zoom} resetToken={resetToken} paused={!motionOn} />
                        </div>
                      </Suspense>
                    </SceneBoundary>
                  ) : <div className="absolute inset-0 grid place-items-center text-cyan-100 text-xs" role="status">Loading…</div>}
              <div className="absolute bottom-2 left-2 right-2 z-10 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-slate-300 pointer-events-none">
                {['confirmed', 'unverified', 'uncertain', 'pending', 'negated', ...(changes.length ? ['hypothetical'] : [])].map((s) => (
                  <span key={s} className="inline-flex items-center gap-1">
                    <span className={`inline-block w-2 h-2 rounded-full ${s === 'negated' ? 'border' : ''}`} style={s === 'negated' ? { borderColor: STATE_STYLE[s].color } : { background: STATE_STYLE[s].color }} />
                    {STATE_STYLE[s].label}
                  </span>
                ))}
                <span className="ml-auto text-slate-500">Anatomy: BodyParts3D © DBCLS, CC BY-SA 2.1 JP (modified)</span>
              </div>
            </section>

            {/* Candidates + inspector */}
            <div className="flex flex-col gap-3 min-w-0 lg:col-span-2 lg:grid lg:grid-cols-2 2xl:col-span-1 2xl:flex">
              <Card title="Disease candidates" right={<span className="text-[10px] text-on-surface-variant">rank-based score, not a probability</span>}>
                {twin && !twin.candidates.length && <p className="text-xs text-on-surface-variant">This case has no stored ranking (e.g. a scribe draft). Run the diagnosis in the workspace to rank candidates.</p>}
                <ol className="flex flex-col gap-1">
                  {twin && twin.candidates.map((c) => {
                    const active = sel && sel.kind === 'candidate' && String(sel.id) === String(c.disease_id);
                    const top = twin.candidates[0].final_score || 1;
                    return (
                      <li key={c.disease_id}>
                        <button type="button" onClick={() => setSel({ kind: 'candidate', id: c.disease_id })}
                          className={`w-full text-left rounded-lg border p-1.5 ${active ? 'border-secondary bg-secondary-fixed/30' : 'border-outline-variant/40 hover:border-secondary/60'}`}>
                          <div className="flex items-baseline gap-1.5 text-xs">
                            <span className="font-bold text-secondary">#{c.rank}</span>
                            <span className="font-semibold truncate" title={c.disease_name}>{c.disease_name}</span>
                            <span className="ml-auto font-mono text-[11px]">{Number(c.final_score).toFixed(3)}</span>
                          </div>
                          <div className="h-1 rounded bg-surface-container mt-1"><div className="h-1 rounded bg-secondary" style={{ width: `${Math.max(4, (c.final_score / top) * 100)}%` }} /></div>
                          <div className="flex flex-wrap gap-1 mt-1 text-[10px] text-on-surface-variant">
                            <span>{c.matched_hpo.length} matched finding{c.matched_hpo.length === 1 ? '' : 's'}</span>
                            {c.label && <span>· {c.label}</span>}
                            {c.genes.slice(0, 3).map((g) => <span key={g} className="font-mono px-1 rounded bg-surface-container">{g}</span>)}
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ol>
              </Card>
              <Card title="Inspector" className="flex-1 2xl:max-h-[360px] overflow-auto">
                <Inspector sel={sel} twin={twin} onClose={() => setSel(null)} />
              </Card>
            </div>
          </div>
        )}

        {twin && (
          <div className="grid gap-3 2xl:grid-cols-[minmax(0,1fr)_420px]">
            <Card id="twin-network" title="Evidence network" dark right={<span className="text-[10px] text-slate-400">drag to pan · wheel to zoom · click to inspect</span>}>
              <EvidenceNetwork graph={twin.graph} selectedId={graphSelected} highlightIds={graphHighlight} animate={motionOn}
                onSelect={(x) => {
                  if (!x) return setSel(null);
                  if (x.edge) return setSel({ kind: 'edge', data: x.edge });
                  const n = x.node;
                  if (n.type === 'finding') return setSel({ kind: 'finding', id: n.id.slice(2) });
                  if (n.type === 'disease') return setSel({ kind: 'candidate', id: n.id.slice(2) });
                  return setSel({ kind: 'node', data: n });
                }} />
            </Card>
            <Card id="twin-genomic" title="Genomic evidence (reference)" dark>
              <GenomicPanel genomic={twin.genomic} animate={motionOn} focusGenes={focusGenes} />
            </Card>
          </div>
        )}

        {twin && (
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <Card id="twin-counterfactual" title="Counterfactual twin">
              {twin.candidates.length ? (
                <CounterfactualTwin caseId={twin.case.case_id} findings={twin.findings} scenarios={twin.scenarios} result={scenario} busy={cfBusy} setBusy={setCfBusy}
                  onResult={(res, ch) => { setScenario(res); setChanges(ch); setOverlay(true); load(twin.case.case_id, true); }}
                  onReset={() => { setScenario(null); setChanges([]); }} />
              ) : <p className="text-xs text-on-surface-variant">Counterfactual ranking needs a ranked case.</p>}
            </Card>
            <Card title="Baseline vs hypothetical" dark>
              {!scenario ? (
                <p className="text-xs text-slate-400">Run or reopen a hypothetical scenario to compare the baseline twin with the hypothetical twin side by side.</p>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {[['Baseline (recorded)', baseMarkers, false], ['HYPOTHETICAL', hypoMarkers, true]].map(([label, mk, hyp]) => (
                    <div key={label} className={`relative h-[300px] rounded-lg border ${hyp ? 'border-fuchsia-400/50' : 'border-cyan-500/20'} bg-[radial-gradient(ellipse_at_50%_35%,#0d3a5c_0%,#030b16_100%)]`}>
                      <span className={`absolute top-1 left-1 z-10 text-[10px] font-bold px-1.5 py-0.5 rounded ${hyp ? 'bg-fuchsia-500/30 text-fuchsia-100' : 'bg-cyan-500/20 text-cyan-100'}`}>{label}</span>
                      <ul className="absolute bottom-1 left-1 right-1 z-10 text-[10px] text-slate-300">
                        {(hyp ? changes : []).map((c, i) => <li key={i} className="text-fuchsia-200">{c.op === 'added' ? '+' : '−'} {c.name}{c.regions.length ? ` → ${c.regions.map((r) => r.label).join(', ')}` : ' (not placed: no region)'}</li>)}
                        <li>Top candidate: {hyp ? ((scenario.counterfactual_ranking || [])[0] || {}).disease_name || '—' : ((scenario.baseline_ranking || [])[0] || {}).disease_name || '—'}</li>
                      </ul>
                      {webgl && manifest && !manifestError && (
                        <SceneBoundary fallback={(r) => <p className="p-3 text-xs text-amber-200">{r}</p>}>
                          <Suspense fallback={null}>
                            <div className="absolute inset-0">
                              <TwinCanvas compact manifest={manifest} catalogue={twin.mapping.region_catalogue} markers={mk} viewMode={viewMode} layers={layers}
                                reducedMotion={reduced} lowPower paused={!motionOn} />
                            </div>
                          </Suspense>
                        </SceneBoundary>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}

        {twin && <p className="text-[10px] text-on-surface-variant">{twin.disclaimer} Region mapping: {twin.mapping.rule}.</p>}
    </div>
  );
}
