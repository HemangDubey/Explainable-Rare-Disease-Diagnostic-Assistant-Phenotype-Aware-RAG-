// Evidence network: patient findings -> HPO concepts -> disease candidates -> genes. Every node and edge comes from the backend
// `graph` payload (built from the stored case); nothing is added here. Layout is a one-off d3-force pass (no continuous simulation).
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from 'd3-force';
import { STATE_STYLE } from './twinTheme';

const W = 960;
const H = 360;
const COLUMN = { finding: 0.07, hpo: 0.33, disease: 0.6, gene: 0.94 };
const TYPE_LABEL = { finding: 'Patient findings', hpo: 'HPO concepts', disease: 'Disease candidates', gene: 'Genes (knowledge base)' };
const EDGE_STYLE = {
  normalized_to: { color: '#38bdf8', label: 'finding normalised to HPO' },
  annotated_to: { color: '#14b8a6', label: 'HPO term annotated to disease (matched evidence)' },
  gene_association: { color: '#a78bfa', label: 'disease–gene association' },
};
const ORDER = ['finding', 'hpo', 'disease', 'gene'];
const trunc = (s, n) => (s && s.length > n ? `${s.slice(0, n - 1)}…` : s || '');

function layout(graph) {
  const nodes = graph.nodes.map((n) => ({ ...n }));
  const ids = new Set(nodes.map((n) => n.id));
  const links = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => ({ ...e }));
  const counts = {};
  nodes.forEach((n) => {
    counts[n.type] = (counts[n.type] || 0) + 1;
    n.x = COLUMN[n.type] * W;
    n.y = (H / ((graph.nodes.filter((m) => m.type === n.type).length) + 1)) * counts[n.type];
  });
  const sim = forceSimulation(nodes)
    .force('link', forceLink(links).id((d) => d.id).distance(90).strength(0.15))
    .force('charge', forceManyBody().strength(-60))
    .force('x', forceX((d) => COLUMN[d.type] * W).strength(1))
    .force('y', forceY(H / 2).strength(0.04))
    .force('collide', forceCollide(21))
    .stop();
  for (let i = 0; i < 220; i += 1) sim.tick();
  nodes.forEach((n) => { n.y = Math.max(16, Math.min(H - 16, n.y)); });
  return { nodes, links };
}

function NodeShape({ n, active, dim }) {
  const fill = n.type === 'finding' ? (STATE_STYLE[n.state] || STATE_STYLE.pending).color
    : n.type === 'hpo' ? '#0ea5e9' : n.type === 'disease' ? '#0f766e' : '#7c3aed';
  const common = { fill, stroke: active ? '#ecfeff' : 'rgba(255,255,255,0.35)', strokeWidth: active ? 2.5 : 1, opacity: dim ? 0.25 : 1 };
  if (n.type === 'finding') {
    return n.state === 'negated'
      ? <circle r={8} {...common} fill="transparent" stroke={fill} strokeWidth={2.2} />
      : <circle r={8} {...common} />;
  }
  if (n.type === 'hpo') return <rect x={-9} y={-7} width={18} height={14} rx={3} {...common} />;
  if (n.type === 'disease') return <rect x={-11} y={-8} width={22} height={16} rx={8} {...common} />;
  return <rect x={-7} y={-7} width={14} height={14} transform="rotate(45)" {...common} />;
}

export default function EvidenceNetwork({ graph, selectedId, onSelect, highlightIds = [], animate = true }) {
  const [types, setTypes] = useState({ finding: true, hpo: true, disease: true, gene: true });
  const [hideNegated, setHideNegated] = useState(false);
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const [revealed, setRevealed] = useState(animate ? 0 : ORDER.length);
  const drag = useRef(null);
  const svgRef = useRef(null);

  const lay = useMemo(() => (graph && graph.nodes.length ? layout(graph) : { nodes: [], links: [] }), [graph]);

  // Progressive construction: findings, then HPO, then candidates, then genes. Static when motion is reduced.
  useEffect(() => {
    if (!animate) { setRevealed(ORDER.length); return undefined; }
    setRevealed(0);
    const timers = ORDER.map((_, i) => setTimeout(() => setRevealed(i + 1), 250 + i * 380));
    return () => timers.forEach(clearTimeout);
  }, [graph, animate]);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      e.preventDefault();
      setView((v) => ({ ...v, k: Math.max(0.5, Math.min(3, v.k * (e.deltaY < 0 ? 1.12 : 0.89))) }));
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  if (!graph) return null;
  if (!graph.nodes.length) {
    return <p className="text-sm text-slate-400 p-4">No evidence network: this case has no extracted findings.</p>;
  }

  const visibleType = (t) => types[t] && ORDER.indexOf(t) < revealed;
  const shown = new Set(lay.nodes.filter((n) => visibleType(n.type) && !(hideNegated && n.type === 'finding' && n.state === 'negated')).map((n) => n.id));
  const hl = new Set(highlightIds);
  const neighbours = new Set();
  if (selectedId) {
    neighbours.add(selectedId);
    lay.links.forEach((l) => {
      if (l.source.id === selectedId) neighbours.add(l.target.id);
      if (l.target.id === selectedId) neighbours.add(l.source.id);
    });
  }
  const dimNode = (id) => (selectedId ? !neighbours.has(id) : hl.size ? !hl.has(id) : false);
  const nCounts = ORDER.map((t) => [t, lay.nodes.filter((n) => n.type === t).length]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        {nCounts.map(([t, c]) => (
          <label key={t} className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-slate-600 text-slate-200 cursor-pointer">
            <input type="checkbox" checked={types[t]} onChange={() => setTypes((s) => ({ ...s, [t]: !s[t] }))} className="accent-cyan-400" />
            {TYPE_LABEL[t]} ({c})
          </label>
        ))}
        <label className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-slate-600 text-slate-200 cursor-pointer">
          <input type="checkbox" checked={hideNegated} onChange={() => setHideNegated((v) => !v)} className="accent-cyan-400" /> Hide absent findings
        </label>
        <span className="ml-auto flex gap-1">
          <button type="button" className="px-2 py-0.5 rounded border border-slate-600 text-slate-200 hover:border-cyan-400" onClick={() => setView((v) => ({ ...v, k: Math.min(3, v.k * 1.2) }))} aria-label="Zoom in">+</button>
          <button type="button" className="px-2 py-0.5 rounded border border-slate-600 text-slate-200 hover:border-cyan-400" onClick={() => setView((v) => ({ ...v, k: Math.max(0.5, v.k / 1.2) }))} aria-label="Zoom out">−</button>
          <button type="button" className="px-2 py-0.5 rounded border border-slate-600 text-slate-200 hover:border-cyan-400" onClick={() => { setView({ k: 1, x: 0, y: 0 }); onSelect && onSelect(null); }}>Reset</button>
        </span>
      </div>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full h-[300px] rounded-lg bg-slate-950/60 border border-cyan-500/15 touch-none select-none"
        role="img" aria-label="Evidence network: findings, HPO concepts, disease candidates and genes"
        onPointerDown={(e) => { if (e.target === svgRef.current || e.target.dataset.bg) drag.current = { x: e.clientX, y: e.clientY, v: view }; }}
        onPointerMove={(e) => {
          if (!drag.current) return;
          const s = W / svgRef.current.clientWidth;
          setView({ ...drag.current.v, x: drag.current.v.x + (e.clientX - drag.current.x) * s, y: drag.current.v.y + (e.clientY - drag.current.y) * s });
        }}
        onPointerUp={() => { drag.current = null; }} onPointerLeave={() => { drag.current = null; }}>
        <rect data-bg="1" x={0} y={0} width={W} height={H} fill="transparent" />
        {ORDER.map((t) => (
          <text key={t} x={COLUMN[t] * W} y={11} textAnchor="middle" className="fill-slate-500" fontSize={10}>{TYPE_LABEL[t]}</text>
        ))}
        <g transform={`translate(${view.x + (W / 2) * (1 - view.k)} ${view.y + (H / 2) * (1 - view.k)}) scale(${view.k})`}>
          {lay.links.filter((l) => shown.has(l.source.id) && shown.has(l.target.id)).map((l, i) => {
            const st = EDGE_STYLE[l.type] || EDGE_STYLE.normalized_to;
            const dim = selectedId ? !(neighbours.has(l.source.id) && neighbours.has(l.target.id)) : false;
            const negatedSrc = l.source.type === 'finding' && l.source.state === 'negated';
            return (
              <line key={i} x1={l.source.x} y1={l.source.y} x2={l.target.x} y2={l.target.y} stroke={st.color} strokeWidth={1.3}
                strokeDasharray={negatedSrc ? '4 3' : undefined} opacity={dim ? 0.12 : 0.7} className="twin-edge cursor-pointer"
                onClick={(e) => { e.stopPropagation(); onSelect && onSelect({ edge: { type: l.type, label: st.label, source: l.source.label, target: l.target.label, evidence_id: l.evidence_id, detail: l.detail } }); }}>
                <title>{st.label}{l.evidence_id ? ` · ${l.evidence_id}` : ''}</title>
              </line>
            );
          })}
          {lay.nodes.filter((n) => shown.has(n.id)).map((n) => (
            <g key={n.id} transform={`translate(${n.x} ${n.y})`} className="cursor-pointer twin-node" tabIndex={0} role="button"
              aria-label={`${n.type}: ${n.label}`}
              onClick={(e) => { e.stopPropagation(); onSelect && onSelect({ node: n }); }}
              onKeyDown={(e) => { if (e.key === 'Enter') onSelect && onSelect({ node: n }); }}>
              <NodeShape n={n} active={n.id === selectedId || hl.has(n.id)} dim={dimNode(n.id)} />
              <text x={n.type === 'gene' ? -12 : 13} y={4} fontSize={10} textAnchor={n.type === 'gene' ? 'end' : 'start'}
                className="fill-slate-200" opacity={dimNode(n.id) ? 0.3 : 1}>
                {n.type === 'disease' ? `#${n.rank} ` : ''}{trunc(n.label, n.type === 'finding' ? 22 : n.type === 'disease' ? 30 : 24)}
              </text>
            </g>
          ))}
        </g>
      </svg>
      <div className="flex flex-wrap gap-3 text-[10px] text-slate-400">
        {Object.entries(EDGE_STYLE).map(([k, v]) => (
          <span key={k} className="inline-flex items-center gap-1"><span className="inline-block w-4 h-0.5" style={{ background: v.color }} />{v.label}</span>
        ))}
        <span className="inline-flex items-center gap-1"><span className="inline-block w-4 border-t border-dashed border-slate-400" />absent (negated) finding</span>
        <span className="ml-auto italic">{graph.literature && graph.literature.note}</span>
      </div>
    </div>
  );
}
