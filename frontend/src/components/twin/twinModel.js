// Pure helpers for the Digital Twin (no three.js import, so the page can use them without loading the 3D chunk).
// Region keys and their mesh tags come from the backend (`mapping.region_catalogue`); marker anchors are derived from the asset manifest.

export const MANIFEST_URL = '/models/anatomy/anatomy_manifest.json';
export const ASSET_URL = '/models/anatomy/bodyparts3d_anatomy.glb';

// Highest first. A region with any non-negated finding is tinted; a region with only negated findings gets a hollow marker and no tint.
export const STATE_PRIORITY = ['hypothetical', 'confirmed', 'unverified', 'uncertain', 'pending', 'relative_finding', 'negated'];
export const TINT_STATES = new Set(['hypothetical', 'confirmed', 'unverified', 'uncertain', 'pending']);

export function dominantState(states) {
  for (const s of STATE_PRIORITY) if (states.includes(s)) return s;
  return null;
}

// Where a region's marker sits. `side` keeps one limb (x sign) so the marker lands on a limb instead of between the legs.
const ANCHOR_RULES = {
  brain: { tags: ['brain'] }, eyes: { tags: ['eyes'] }, ears: { tags: ['ears'] }, heart: { tags: ['heart'] }, lungs: { tags: ['lungs'] },
  liver: { tags: ['liver'] }, abdomen: { tags: ['abdomen'] }, kidneys: { tags: ['kidneys'] }, skull: { tags: ['skull'] },
  head: { tags: ['skull'], yBias: -0.03 }, spine: { tags: ['spine'] }, limbs: { tags: ['lower_limbs'], side: -1 },
  skeleton: { tags: ['thorax'] }, musculature: { tags: ['upper_limbs'], side: 1 }, skin: { tags: ['upper_limbs'], side: -1, yBias: 0.12 },
};

export function regionAnchors(manifest) {
  const parts = (manifest && manifest.parts) || [];
  const out = {};
  for (const [region, rule] of Object.entries(ANCHOR_RULES)) {
    const sel = parts.filter((p) => rule.tags.includes(p.region) && (!rule.side || Math.sign(p.center[0]) === rule.side));
    if (!sel.length) continue;
    const mn = [Infinity, Infinity, Infinity];
    const mx = [-Infinity, -Infinity, -Infinity];
    sel.forEach((p) => p.bounds[0].forEach((v, i) => { mn[i] = Math.min(mn[i], v); mx[i] = Math.max(mx[i], p.bounds[1][i]); }));
    out[region] = [(mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2 + (rule.yBias || 0), (mn[2] + mx[2]) / 2];
  }
  out.systemic = [0, 0.02, 0];
  return out;
}

// Markers: one per backend region that has findings (and per hypothetical region). Pure function of the backend payload.
export function buildMarkers(findings, hypothetical = []) {
  const byRegion = {};
  for (const f of findings || []) {
    for (const r of f.regions || []) {
      const m = (byRegion[r.region] = byRegion[r.region] || { region: r.region, label: r.label, items: [] });
      m.items.push({ id: f.finding_id, text: f.text_span, hpo_id: f.hpo_id, hpo_label: f.hpo_label, state: f.display_state, via: r.via_hpo_name });
    }
  }
  for (const h of hypothetical || []) {
    for (const r of h.regions || []) {
      const m = (byRegion[r.region] = byRegion[r.region] || { region: r.region, label: r.label, items: [] });
      m.items.push({ id: `hyp:${h.op}:${h.hpo_id}`, text: h.name, hpo_id: h.hpo_id, hpo_label: h.name, state: 'hypothetical', op: h.op, via: r.via_hpo_name });
    }
  }
  return Object.values(byRegion).map((m) => {
    const states = m.items.map((i) => i.state);
    const tintStates = states.filter((s) => TINT_STATES.has(s) || s === 'hypothetical');
    return { ...m, state: dominantState(states), tint: tintStates.length ? dominantState(tintStates) : null, onlyNegated: states.every((s) => s === 'negated') };
  });
}

// Callout labels to the left/right of the body, spread vertically so they never overlap.
export function layoutCallouts(markers, anchors, { x = 0.7, gap = 0.14, top = 1.78, bottom = 0.08 } = {}) {
  const placed = markers.filter((m) => anchors[m.region]).map((m) => ({ ...m, anchor: anchors[m.region] }));
  const left = [];
  const right = [];
  [...placed].sort((a, b) => b.anchor[1] - a.anchor[1]).forEach((m) => {
    const ax = m.anchor[0];
    if (ax > 0.04) right.push(m);
    else if (ax < -0.04) left.push(m);
    else (left.length <= right.length ? left : right).push(m);
  });
  const spread = (list, sx) => {
    let y = top + gap;
    return list.map((m) => {
      y = Math.max(bottom, Math.min(m.anchor[1], y - gap));
      return { ...m, labelPos: [sx, y, m.anchor[2]] };
    });
  };
  return [...spread(left, -x), ...spread(right, x)];
}

// Which backend region does a clicked mesh belong to (mesh tags are finer than regions for the skeleton).
export const MESH_TAG_TO_REGION = {
  brain: 'brain', eyes: 'eyes', ears: 'ears', heart: 'heart', lungs: 'lungs', liver: 'liver', abdomen: 'abdomen', kidneys: 'kidneys',
  skull: 'skull', spine: 'spine', thorax: 'skeleton', upper_limbs: 'limbs', lower_limbs: 'limbs', skin: 'skin',
};

export function parseNodeName(name) {
  const [layer, tag, fma] = String(name || '').split('__');
  return fma ? { layer, tag, fma } : null;
}
