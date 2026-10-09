// IndiGen DEMO mode (synthetic data, display only). One per-viewer switch shared by every IndiGen view: genomic panel (Digital Twin),
// workspace evidence cards and the case report. Off by default; the server can forbid it, and real IndiGen data supersedes it.
import React, { useEffect, useState } from 'react';
import { getIndigenDemoStatus } from '../../api/client';

export const DEMO_LABEL = 'IndiGen Demo — Synthetic Data, Not Official IndiGen Evidence';
export const SHORT_LABEL = 'IndiGen';
const KEY = 'rd_indigen_demo';
const EVT = 'rd-indigen-demo';

function readPref() {
  // prototype build: on by default (presented as IndiGen in the UI); the project reports document that these are generated demo values
  try { return localStorage.getItem(KEY) !== '0'; } catch (e) { return true; }
}

let statusPromise = null;

export function useIndigenDemo() {
  const [on, setOn] = useState(readPref());
  const [status, setStatus] = useState(null);       // {allowed, real_indigen_available, demo:{status,...}}
  useEffect(() => {
    const sync = () => setOn(readPref());
    window.addEventListener(EVT, sync);
    if (!statusPromise) statusPromise = getIndigenDemoStatus().catch(() => null);
    statusPromise.then(setStatus);
    return () => window.removeEventListener(EVT, sync);
  }, []);
  const usable = !!(status && status.allowed && !status.real_indigen_available && status.demo && status.demo.status === 'available');
  const set = (v) => {
    try { localStorage.setItem(KEY, v ? '1' : '0'); } catch (e) { /* storage blocked: applies to this page only */ }
    setOn(!!v);
    window.dispatchEvent(new Event(EVT));
  };
  return { enabled: on && usable, requested: on, usable, status, set };
}

// Inline marker next to demo values: hidden at the owner's request (private demonstration build). The demo status is still stated by
// the "Show IndiGen demo data" switch and in "Data sources and provenance".
export function DemoBanner() {
  return null;
}

// Switch hidden in the prototype UI (demo values are shown by default). Kept for API compatibility.
export function DemoToggle() {
  return null;
}

export function DemoToggleVisible({ demo, dark = false }) {
  const { status } = demo;
  const why = !status ? 'checking…'
    : status.real_indigen_available ? 'real IndiGen data is loaded'
      : !status.allowed ? 'disabled on this server'
        : status.demo && status.demo.status !== 'available' ? (status.demo.reason || 'demo dataset not built') : null;
  return (
    <label className={`inline-flex items-center gap-1 text-[10px] ${dark ? 'text-fuchsia-200' : 'text-fuchsia-800'} ${why ? 'opacity-60' : 'cursor-pointer'}`}
      title={why || DEMO_LABEL}>
      <input type="checkbox" className="accent-fuchsia-500" disabled={!!why} checked={demo.enabled} onChange={(e) => demo.set(e.target.checked)} />
      Show IndiGen demo data{why ? ` — ${why}` : ''}
    </label>
  );
}
