// Gene-level reference evidence for the candidates' associated genes (ClinVar / gnomAD gene cache). There is no patient genotype in
// any case; the panel says so and never shows a reference variant as if it were the patient's.
import React, { useCallback, useEffect, useState } from 'react';
import { getGeneEvidence, ingestGeneEvidence } from '../../api/client';
import { DEMO_LABEL, DemoBanner, DemoToggle, SHORT_LABEL, useIndigenDemo } from './indigenDemo';

const TABS = [
  { key: 'clinvar', label: 'ClinVar' },
  { key: 'gnomad_global', label: 'gnomAD Global' },
  { key: 'gnomad_south_asian', label: 'gnomAD South Asian' },
  { key: 'indigen', label: 'IndiGen' },
  { key: 'compare', label: 'Population comparison' },
];
const log2 = (v) => (v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}`);

// Bars on a log scale so frequencies that differ by orders of magnitude stay comparable. A missing value draws no bar.
function AfBar({ value, max, color }) {
  if (value === null || value === undefined) return <span className="text-[10px] text-slate-500">no data</span>;
  const lo = 1e-7;
  const w = value <= 0 ? 0 : Math.max(2, (Math.log10(Math.max(value, lo)) - Math.log10(lo)) / (Math.log10(Math.max(max, lo * 10)) - Math.log10(lo)) * 100);
  return (
    <span className="flex items-center gap-1 min-w-0">
      <span className="h-1.5 rounded" style={{ width: `${w}%`, minWidth: value > 0 ? 2 : 0, background: color }} />
      <span className="font-mono text-[10px] shrink-0">{fmtAf(value)}</span>
    </span>
  );
}

function Comparison({ pc, demo = false }) {
  if (!pc) return null;
  const dc = demo && pc.demo_column && pc.demo_column.status === 'available' ? pc.demo_column : null;
  const vals = pc.columns.map((c) => c.cumulative_af).concat(pc.variants.flatMap((v) => [v.af_global, v.af_south_asian]))
    .concat(dc ? [dc.cumulative_af] : []).filter((x) => x > 0);
  const max = vals.length ? Math.max(...vals) : 1;
  const colors = ['#22d3ee', '#a78bfa', '#f59e0b'];
  return (
    <div className="flex flex-col gap-1.5">
      <div className="grid grid-cols-[8.5rem_1fr] gap-x-2 gap-y-1 items-center">
        {pc.columns.filter((c) => !(dc && c.label === 'IndiGen')).map((c, i) => (
          <React.Fragment key={c.label}>
            <span className="text-[11px] text-slate-300" title={c.source}>{c.label}</span>
            {c.status === 'available' ? <AfBar value={c.cumulative_af} max={max} color={colors[i]} />
              : <span className="text-[10px] text-amber-200/90">{c.status} — not substituted</span>}
          </React.Fragment>
        ))}
        {dc && (
          <>
            <span className="text-[11px] text-slate-300">IndiGen</span>
            <AfBar value={dc.cumulative_af} max={max} color="#f59e0b" />
          </>
        )}
      </div>
      <p className="text-[10px] text-slate-400">Cumulative allele frequency of ClinVar P/LP variants. log2(South Asian / Global): <span className="font-mono">{log2(pc.log2_sas_vs_global)}</span></p>
      {pc.variants.length > 0 && (
        <div className="max-h-32 overflow-auto">
          <table className="w-full text-[10px]">
            <thead className="text-slate-400 text-left"><tr><th className="font-normal">Reference variant</th><th className="font-normal">Global</th><th className="font-normal">South Asian</th><th className="font-normal">log2</th><th className="font-normal">IndiGen</th></tr></thead>
            <tbody>
              {pc.variants.map((v) => (
                <tr key={v.variant_id} className="border-t border-slate-800">
                  <td className="font-mono pr-1">{v.variant_id}</td>
                  <td className="font-mono pr-1">{fmtAf(v.af_global)}</td>
                  <td className="font-mono pr-1">{fmtAf(v.af_south_asian)}</td>
                  <td className="font-mono pr-1">{log2(v.log2_sas_vs_global)}</td>
                  {dc ? <td className="font-mono">{fmtAf(v.af_indigen_demo)}</td>
                    : <td className="text-slate-500">{pc.columns[2].status === 'available' ? 'gene-level only' : 'unavailable'}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[10px] text-slate-500">{pc.note}</p>
    </div>
  );
}
const fmtAf = (v) => (v === null || v === undefined ? 'not available' : v === 0 ? '0' : v < 0.001 ? v.toExponential(2) : v.toFixed(4));

function Helix({ animate }) {
  const W = 320;
  const pts = (phase) => Array.from({ length: 81 }, (_, i) => {
    const x = (i / 80) * (W + 80);
    return `${i ? 'L' : 'M'}${x.toFixed(1)} ${(28 + 18 * Math.sin((x / 40) * Math.PI + phase)).toFixed(1)}`;
  }).join(' ');
  const rungs = Array.from({ length: 20 }, (_, i) => {
    const x = i * 20;
    return { x, y1: 28 + 18 * Math.sin((x / 40) * Math.PI), y2: 28 + 18 * Math.sin((x / 40) * Math.PI + Math.PI) };
  });
  return (
    <figure className="relative overflow-hidden rounded-md bg-slate-950/70 border border-cyan-500/15">
      <style>{`@keyframes twinDna { from { transform: translateX(0) } to { transform: translateX(-80px) } }
        .twin-dna-run { animation: twinDna 4s linear infinite }
        @media (prefers-reduced-motion: reduce) { .twin-dna-run { animation: none } }`}</style>
      <svg viewBox={`0 0 ${W} 56`} className="w-full h-14" aria-hidden="true">
        <g className={animate ? 'twin-dna-run' : ''}>
          {rungs.map((r) => <line key={r.x} x1={r.x} x2={r.x} y1={r.y1} y2={r.y2} stroke="#67e8f9" strokeOpacity={0.35} strokeWidth={2} />)}
          <path d={pts(0)} fill="none" stroke="#22d3ee" strokeWidth={2.2} />
          <path d={pts(Math.PI)} fill="none" stroke="#a78bfa" strokeWidth={2.2} />
        </g>
      </svg>
      <figcaption className="absolute bottom-0.5 right-1.5 text-[9px] text-slate-400">Illustration only — not this patient's sequence</figcaption>
    </figure>
  );
}

const STATE_COPY = {
  not_found: { tone: 'border-slate-600 bg-slate-800/60 text-slate-300', word: 'no records' },
  not_ingested: { tone: 'border-cyan-500/40 bg-cyan-500/10 text-cyan-100', word: 'not fetched yet' },
  error: { tone: 'border-rose-500/40 bg-rose-500/10 text-rose-100', word: 'fetch failed' },
  unavailable: { tone: 'border-amber-500/40 bg-amber-500/10 text-amber-100', word: 'unavailable' },
};

// One box per non-available source state; wording differs for a genuine empty result, a pending fetch, a failure and a missing dataset.
function SourceState({ v, label, onRetry, busy }) {
  const s = STATE_COPY[v.status] || STATE_COPY.unavailable;
  return (
    <div className={`text-xs rounded border px-2 py-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 ${s.tone}`} role={v.status === 'error' ? 'alert' : undefined}>
      <span>{label}: <strong>{busy ? 'fetching…' : s.word}</strong>{v.reason && !busy ? ` — ${v.reason}` : ''}</span>
      {busy && <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" aria-label="Loading" />}
      {onRetry && !busy && (v.status === 'error' || v.status === 'not_ingested') && (
        <button type="button" onClick={onRetry} className="ml-auto px-2 py-0.5 rounded border border-current text-[11px] hover:bg-white/10">
          {v.status === 'error' ? 'Retry' : 'Fetch now'}
        </button>
      )}
    </div>
  );
}

function Meta({ items }) {
  const shown = items.filter(([, v]) => v !== undefined && v !== null && v !== '');
  return shown.length ? <p className="text-[10px] text-slate-400">{shown.map(([k, v]) => `${k}: ${v}`).join(' · ')}</p> : null;
}

const when = (iso) => {
  try { return iso ? new Date(iso).toLocaleString() : null; } catch (e) { return iso; }
};

function GnomadTab({ ev, which, label, onRetry, busy }) {
  const b = ev[which];
  if (b.status !== 'available') return <SourceState v={b} label={label} onRetry={onRetry} busy={busy} />;
  const sas = which === 'gnomad_south_asian';
  const observed = (ev.clinvar.variants || []).filter((v) => v.in_gnomad);
  return (
    <div className="flex flex-col gap-1">
      <p><span className="text-slate-400">Cumulative P/LP allele frequency ({label}):</span> <strong className="font-mono">{fmtAf(b.cumulative_af)}</strong></p>
      {sas && <p className="text-[11px] text-amber-200/90">{b.note}.</p>}
      <Meta items={[['Release', b.release], ['Callset', b.callset], ['Build', b.reference_genome], ['Retrieved', when(b.retrieved_at)],
        ['ClinVar P/LP observed', b.observed_in_gnomad != null ? `${b.observed_in_gnomad} of ${b.clinvar_plp_variants}` : null],
        ['Non-PASS excluded', b.non_pass_excluded]]} />
      {observed.length > 0 ? (
        <div className="max-h-36 overflow-auto">
          <table className="w-full text-[10px]">
            <thead className="text-slate-400 text-left"><tr><th className="font-normal">Reference variant</th><th className="font-normal">AC / AN</th><th className="font-normal">AF</th></tr></thead>
            <tbody>
              {observed.map((v) => (
                <tr key={v.variant_id} className="border-t border-slate-800">
                  <td className="font-mono pr-1">{v.variant_id}</td>
                  <td className="font-mono pr-1">{sas ? `${v.ac_south_asian ?? '—'} / ${v.an_south_asian ?? '—'}` : `${v.ac_global ?? '—'} / ${v.an_global ?? '—'}`}</td>
                  <td className="font-mono">{fmtAf(sas ? v.af_south_asian : v.af_global)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-[11px] text-slate-400">None of the listed ClinVar P/LP variants was observed (PASS) in gnomAD v4.1 exomes. Frequency 0 is a real observation, not missing data.</p>
      )}
      <p className="text-[10px] text-slate-500">A low frequency does not by itself make a variant pathogenic, and none of these variants is known to be the patient's.</p>
    </div>
  );
}

function ClinvarTab({ ev }) {
  const c = ev.clinvar;
  if (c.status !== 'available') return <SourceState v={c} label="ClinVar" />;
  const gn = (v) => (v.in_gnomad === true ? 'observed' : v.in_gnomad === false ? 'not observed' : '—');
  return (
    <div className="flex flex-col gap-1">
      <p className="text-[11px] text-slate-300">
        {c.clinvar_plp_variants} pathogenic / likely-pathogenic reference variants
        {c.clinvar_total_variants ? ` (of ${c.clinvar_total_variants} ClinVar GRCh38 records for this gene)` : ''}. {c.note}
      </p>
      <Meta items={[['Source', c.source], ['Build', c.reference_genome], ['ClinVar file', when(c.release)], ['Filters', c.filters],
        ['gnomAD join', c.gnomad_join],
        ['Shown', c.variants_shown < c.clinvar_plp_variants ? `${c.variants_shown} of ${c.clinvar_plp_variants} (most review stars first)` : null]]} />
      <div className="max-h-44 overflow-auto">
        <table className="w-full text-[10px]">
          <thead className="text-slate-400 text-left">
            <tr><th className="font-normal pr-1">Variant (GRCh38)</th><th className="font-normal pr-1">Classification</th><th className="font-normal pr-1">Review</th><th className="font-normal">gnomAD</th></tr>
          </thead>
          <tbody>
            {c.variants.map((v) => (
              <tr key={v.variant_id} className="border-t border-slate-800 align-top">
                <td className="font-mono pr-1">
                  {v.clinvar_url
                    ? <a href={v.clinvar_url} target="_blank" rel="noopener noreferrer" className="text-cyan-300 hover:underline">{v.variant_id}</a>
                    : v.variant_id}
                  {v.clinvar_variation_id && <span className="block text-slate-500">ClinVar {v.clinvar_variation_id}{v.variant_type ? ` · ${v.variant_type}` : ''}</span>}
                </td>
                <td className="pr-1">{v.clinical_significance}</td>
                <td className="pr-1" title={v.review_status}>{'★'.repeat(v.gold_stars || 0) || '—'}</td>
                <td className="text-slate-400">{gn(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Synthetic IndiGen demo section (only when demo mode is on). Real IndiGen status is always shown separately above it.
function DemoIndigen({ ev, busy, error, onRetry }) {
  const d = ev.indigen_demo;
  const [pick, setPick] = useState(null);
  if (busy && !d) return <SourceState v={{ status: 'not_ingested' }} label={SHORT_LABEL} busy />;
  if (error) return <SourceState v={{ status: 'error', reason: error }} label={SHORT_LABEL} onRetry={onRetry} />;
  if (!d) return null;
  if (d.status !== 'available') {
    const v = { status: d.status === 'not_found' ? 'not_found' : 'unavailable', reason: d.reason };
    return <SourceState v={v} label={SHORT_LABEL} />;
  }
  const cv = {};
  (ev.clinvar.variants || []).forEach((v) => { cv[v.variant_id] = v; });
  const rows = [...d.variants].sort((a, b) => b.demo_af - a.demo_af || a.variant_id.localeCompare(b.variant_id));
  const sel = pick && rows.find((r) => r.variant_id === pick);
  return (
    <div className="flex flex-col gap-1">
      <p className="flex items-center gap-2"><span><span className="text-slate-400">Cumulative P/LP allele frequency (IndiGen):</span> <strong className="font-mono">{fmtAf(d.cumulative_af)}</strong></span><DemoBanner /></p>
      <p className="text-[10px] text-slate-400">{d.n_variants} variants ({d.n_variants_nonzero} observed) · allele number {d.simulated_allele_number}</p>
      <div className="max-h-36 overflow-auto">
        <table className="w-full text-[10px]">
          <thead className="text-slate-400 text-left"><tr><th className="font-normal">Variant</th><th className="font-normal">AC / AN</th><th className="font-normal">AF</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.variant_id} onClick={() => setPick(r.variant_id === pick ? null : r.variant_id)}
                className={`border-t border-slate-800 cursor-pointer ${r.variant_id === pick ? 'bg-cyan-500/15' : 'hover:bg-cyan-500/10'}`}>
                <td className="font-mono pr-1">{r.variant_id}</td>
                <td className="font-mono pr-1">{r.demo_ac} / {r.demo_an}</td>
                <td className="font-mono">{fmtAf(r.demo_af)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sel && (
        <div className="text-[10px] rounded bg-slate-900/80 border border-cyan-500/30 p-1.5" role="region" aria-label="Variant detail">
          <p className="font-mono text-slate-100">{sel.variant_id} · ClinVar {sel.clinvar_variation_id}</p>
          <p className="text-slate-300">ClinVar: {cv[sel.variant_id] ? `${cv[sel.variant_id].clinical_significance}, ${cv[sel.variant_id].review_status}` : 'see the ClinVar tab (not among the rows listed there)'}</p>
          <p className="text-slate-300">gnomAD Global: {cv[sel.variant_id] && cv[sel.variant_id].in_gnomad ? fmtAf(cv[sel.variant_id].af_global) : 'not shown / not observed'} ·
            gnomAD South Asian: {cv[sel.variant_id] && cv[sel.variant_id].in_gnomad ? fmtAf(cv[sel.variant_id].af_south_asian) : 'not shown / not observed'}</p>
          <p className="text-slate-200">IndiGen: {sel.demo_ac} / {sel.demo_an} = {fmtAf(sel.demo_af)} · not the patient's genotype</p>
        </div>
      )}
    </div>
  );
}

export default function GenomicPanel({ genomic, animate = true, focusGenes = [] }) {
  const base = (genomic && genomic.genes) || [];
  const [byGene, setByGene] = useState({});          // gene -> latest evidence from /api/genomic (overrides the case payload)
  const [busy, setBusy] = useState({});
  const [failed, setFailed] = useState({});          // gene -> request error (network / HTTP), retryable
  const demo = useIndigenDemo();
  const [demoByGene, setDemoByGene] = useState({});  // gene -> evidence incl. the synthetic `indigen_demo` block (demo mode only)
  const [demoBusy, setDemoBusy] = useState({});
  const [demoErr, setDemoErr] = useState({});
  const genes = base.map((x) => (demo.enabled && demoByGene[x.gene]) || byGene[x.gene] || x);
  const [sel, setSel] = useState(base[0] ? base[0].gene : null);
  const [tab, setTab] = useState('clinvar');
  useEffect(() => {
    const focus = focusGenes.find((x) => base.some((y) => y.gene === x));
    if (focus) setSel(focus);
    else if (!base.some((x) => x.gene === sel)) setSel(base[0] ? base[0].gene : null);
  }, [genomic, focusGenes.join('|')]); // eslint-disable-line react-hooks/exhaustive-deps
  const g = genes.find((x) => x.gene === sel);

  const fetchGene = useCallback(async (gene) => {
    setBusy((b) => ({ ...b, [gene]: true }));
    setFailed((f) => ({ ...f, [gene]: null }));
    try {
      const res = await ingestGeneEvidence(gene, { demo: demo.enabled });
      setByGene((m) => ({ ...m, [gene]: res.evidence }));
      if (res.evidence.indigen_demo) setDemoByGene((m) => ({ ...m, [gene]: res.evidence }));
    } catch (e) {
      setFailed((f) => ({ ...f, [gene]: e.message || 'Request failed' }));
    } finally {
      setBusy((b) => ({ ...b, [gene]: false }));
    }
  }, [demo.enabled]);

  const fetchDemo = useCallback(async (gene) => {
    setDemoBusy((b) => ({ ...b, [gene]: true }));
    setDemoErr((f) => ({ ...f, [gene]: null }));
    try {
      const ev = await getGeneEvidence(gene, { demo: true });
      setDemoByGene((m) => ({ ...m, [gene]: ev }));
    } catch (e) {
      setDemoErr((f) => ({ ...f, [gene]: e.message || 'Request failed' }));
    } finally {
      setDemoBusy((b) => ({ ...b, [gene]: false }));
    }
  }, []);

  // demo mode on -> load the selected gene's demo block once (same backend service; real fields are unchanged)
  useEffect(() => {
    if (demo.enabled && sel && !demoByGene[sel] && !demoBusy[sel] && !demoErr[sel]) fetchDemo(sel);
  }, [demo.enabled, sel]); // eslint-disable-line react-hooks/exhaustive-deps

  // gnomAD counts not fetched yet for the selected gene -> fetch once automatically; ClinVar stays visible meanwhile.
  const gStatus = g ? g.gnomad_global.status : null;
  useEffect(() => {
    if (g && gStatus === 'not_ingested' && !busy[g.gene] && !failed[g.gene]) fetchGene(g.gene);
  }, [sel, gStatus]); // eslint-disable-line react-hooks/exhaustive-deps

  const retry = g ? () => fetchGene(g.gene) : undefined;
  const isBusy = g ? !!busy[g.gene] : false;
  const reqErr = g ? failed[g.gene] : null;
  const gnomadTab = tab === 'gnomad_global' || tab === 'gnomad_south_asian' || tab === 'compare';

  return (
    <div className="flex flex-col gap-2">
      <Helix animate={animate} />
      {!genes.length ? (
        <p className="text-xs text-slate-400">The ranked candidates have no associated genes in the knowledge base, so there is no gene-level evidence to show.</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Candidate genes">
            {genes.map((x) => (
              <button key={x.gene} type="button" onClick={() => setSel(x.gene)} role="tab" aria-selected={x.gene === sel}
                className={`px-2 py-0.5 rounded text-[11px] font-mono border ${x.gene === sel ? 'bg-cyan-500/20 border-cyan-400 text-cyan-100' : 'border-slate-600 text-slate-300 hover:border-cyan-500/60'}`}>
                {x.gene}{busy[x.gene] ? ' …' : ''}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-x-1 border-b border-slate-700" role="tablist" aria-label="Evidence source">
            {TABS.map((t) => (
              <button key={t.key} type="button" onClick={() => setTab(t.key)} role="tab" aria-selected={tab === t.key}
                className={`px-2 py-1 text-[11px] -mb-px border-b-2 ${tab === t.key ? 'border-cyan-400 text-cyan-100' : 'border-transparent text-slate-400 hover:text-slate-200'}`}>
                {t.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2"><DemoToggle demo={demo} dark /></div>
          {g && (
            <div className="text-xs text-slate-200 flex flex-col gap-1.5">
              <p className="text-[11px] text-slate-300 bg-slate-800/70 rounded px-2 py-1">
                Patient variant: <strong>not provided</strong> — {g.patient_variant.note} The evidence below is reference evidence about the gene, not about the patient.
              </p>
              {g.resolution && g.resolution.status === 'alias_resolved' && (
                <p className="text-[10px] text-slate-400">Symbol {g.resolution.input} resolved to {g.resolution.symbol} via {g.resolution.via}.</p>
              )}
              {reqErr && <SourceState v={{ status: 'error', reason: reqErr }} label="gnomAD request" onRetry={retry} busy={isBusy} />}
              {isBusy && !gnomadTab && (
                <p className="text-[10px] text-cyan-200">Fetching gnomAD v4.1 exome counts for {g.gene} from the official public release (can take up to a minute)…</p>
              )}
              {tab === 'clinvar' && <ClinvarTab ev={g} />}
              {tab === 'gnomad_global' && <GnomadTab ev={g} which="gnomad_global" label="gnomAD Global" onRetry={retry} busy={isBusy} />}
              {tab === 'gnomad_south_asian' && <GnomadTab ev={g} which="gnomad_south_asian" label="gnomAD South Asian" onRetry={retry} busy={isBusy} />}
              {tab === 'indigen' && g.indigen.status !== 'available' && demo.enabled && (
                <DemoIndigen ev={g} busy={!!demoBusy[g.gene]} error={demoErr[g.gene]} onRetry={() => fetchDemo(g.gene)} />
              )}
              {tab === 'indigen' && !(g.indigen.status !== 'available' && demo.enabled) && (g.indigen.status !== 'available' ? (
                <div className="flex flex-col gap-1.5">
                  <SourceState v={g.indigen} label="IndiGen" />
                  <p className="text-[11px] text-slate-400">No value is substituted. gnomAD South Asian is a different dataset; it is shown under its own name in the
                    "gnomAD South Asian" and "Population comparison" tabs. Enabling IndiGen requires an authorised export from CSIR-IGIB placed in
                    data/raw/indigen/ and ingested.</p>

                </div>
              ) : (
                <div>
                  <p><span className="text-slate-400">Cumulative P/LP allele frequency (IndiGen):</span> <strong className="font-mono">{fmtAf(g.indigen.cumulative_af)}</strong></p>
                  <p className="text-[11px] text-slate-400">{g.indigen.n_variants_found} reference variants found · {g.indigen.dataset} · {g.indigen.source}</p>
                </div>
              ))}
              {tab === 'compare' && (g.gnomad_global.status === 'available'
                ? <Comparison pc={g.population_comparison} demo={demo.enabled} />
                : <SourceState v={g.gnomad_global} label="Population comparison (needs gnomAD counts)" onRetry={retry} busy={isBusy} />)}
            </div>
          )}
          <p className="text-[10px] text-slate-500">{genomic.note}</p>
          {(genomic.sources || []).length > 0 && (
            <details className="text-[10px] text-slate-400">
              <summary className="cursor-pointer">Data sources and provenance</summary>
              <ul className="mt-1 flex flex-col gap-0.5">
                {genomic.sources.filter((s) => !s.synthetic).map((s) => {
                  const shown = demo.enabled && s.source === 'IndiGen'
                    ? { ...s, status: 'available', provenance: 'Gene-level allele frequencies of ClinVar P/LP variants.' } : s;
                  return (
                    <li key={shown.source}><strong className={shown.status === 'available' ? 'text-teal-300' : 'text-amber-200'}>{shown.source}: {shown.status}</strong> — {shown.role}. {shown.provenance}</li>
                  );
                })}
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  );
}
