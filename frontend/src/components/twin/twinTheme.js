// Shared visual vocabulary for the Digital Twin. States come from the backend (`display_state`); nothing is decided here.
export const STATE_STYLE = {
  confirmed: { color: '#14b8a6', label: 'Confirmed (verified, present)', chip: 'bg-teal-100 text-teal-800 border-teal-300' },
  unverified: { color: '#3b82f6', label: 'Present — not yet verified', chip: 'bg-blue-50 text-blue-800 border-blue-300' },
  uncertain: { color: '#f59e0b', label: 'Uncertain', chip: 'bg-amber-50 text-amber-800 border-amber-300' },
  pending: { color: '#8b5cf6', label: 'Pending assessment', chip: 'bg-violet-50 text-violet-800 border-violet-300' },
  negated: { color: '#94a3b8', label: 'Absent (negated in the note)', chip: 'bg-slate-100 text-slate-600 border-slate-300' },
  relative_finding: { color: '#a8a29e', label: "Relative's finding (not the patient)", chip: 'bg-stone-100 text-stone-600 border-stone-300' },
  unmapped: { color: '#cbd5e1', label: 'No HPO mapping', chip: 'bg-slate-50 text-slate-500 border-slate-200' },
  hypothetical: { color: '#d946ef', label: 'HYPOTHETICAL (counterfactual)', chip: 'bg-fuchsia-50 text-fuchsia-800 border-fuchsia-300' },
};

export const LAYER_COLORS = { skin: '#7dd3e6', skeleton: '#e7e2d3', organs: '#d98c7a', nervous: '#f0a693' };
export const REGION_COLORS = {
  heart: '#c2413b', lungs: '#e7a3a3', liver: '#8f3b2c', abdomen: '#d99481', kidneys: '#7f2e2e', eyes: '#eef2f5', ears: '#d9a48f', brain: '#f0a693',
};
export const SYSTEM_COLORS = {
  nervous: '#a78bfa', sensory: '#38bdf8', cardiovascular: '#f43f5e', respiratory: '#fb7185', digestive: '#f59e0b', urinary: '#eab308',
  skeletal: '#e2e8f0', integumentary: '#67e8f9', muscular: '#fb923c', systemic: '#22d3ee',
};
// manifest mesh-region tags -> body system (for the "Systems" view)
export const MESH_REGION_SYSTEM = {
  brain: 'nervous', eyes: 'sensory', ears: 'sensory', heart: 'cardiovascular', lungs: 'respiratory', liver: 'digestive', abdomen: 'digestive',
  kidneys: 'urinary', skull: 'skeletal', spine: 'skeletal', thorax: 'skeletal', upper_limbs: 'skeletal', lower_limbs: 'skeletal', skin: 'integumentary',
};

export function prefersReducedMotion() {
  try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; }
}

export function hasWebGL() {
  try {
    const c = document.createElement('canvas');
    return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')));
  } catch (e) {
    return false;
  }
}
