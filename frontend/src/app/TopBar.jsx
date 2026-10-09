// Compact header for the internal app: navigation toggle, breadcrumbs, real backend status, the active case and the account menu.
import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../components/AuthContext';
import { activeItem } from './navigation';
import { useWorkspace } from './WorkspaceContext';

function StatusPill({ status }) {
  if (!status) return <span className="ui-chip-neutral" role="status"><span className="ui-spinner w-3 h-3" aria-hidden="true" />Checking backend</span>;
  if (status.status !== 'healthy') return <span className="ui-chip-warn" role="status">Backend unavailable</span>;
  const llm = status.llm?.status === 'healthy';
  return (
    <span className={llm ? 'ui-chip-success' : 'ui-chip-warn'} role="status"
      title={llm ? 'NER, retrieval and ranking ready; AI explanations available'
        : `Pipeline ready; AI explanations ${String(status.llm?.status || 'unavailable').replace(/_/g, ' ')} (labelled fallback is used)`}>
      <span className={`w-1.5 h-1.5 rounded-full ${llm ? 'bg-success' : 'bg-warn'}`} aria-hidden="true" />
      {llm ? 'Pipeline ready' : 'Pipeline ready · AI fallback'}
    </span>
  );
}

function AccountMenu() {
  const { session, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey); };
  }, [open]);
  const email = session?.user?.email || '';
  const name = session?.user?.display_name || email;
  const initials = (name || '?').split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((s) => s[0].toUpperCase()).join('');
  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-haspopup="menu" aria-expanded={open} aria-label="Account menu"
        className="flex items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-ocean-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-ocean/40">
        <span className="w-8 h-8 rounded-full bg-ink text-white text-[12px] font-semibold flex items-center justify-center" aria-hidden="true">{initials}</span>
        <span className="hidden md:block max-w-[160px] truncate text-[13px] text-ink">{name}</span>
        <span className="material-symbols-outlined text-[18px] text-ink-muted" aria-hidden="true">expand_more</span>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 mt-1 w-64 ui-card p-1.5 z-50">
          <div className="px-2.5 py-2 border-b border-line mb-1">
            <p className="text-[13px] font-semibold text-ink truncate">{name}</p>
            {email && email !== name && <p className="text-[12px] text-ink-muted truncate">{email}</p>}
          </div>
          <Link role="menuitem" to="/cases" onClick={() => setOpen(false)} className="ui-btn-ghost w-full justify-start">
            <span className="material-symbols-outlined text-[18px]" aria-hidden="true">folder_open</span>My saved cases
          </Link>
          <button role="menuitem" type="button" onClick={logout} className="ui-btn-ghost w-full justify-start text-danger hover:text-danger">
            <span className="material-symbols-outlined text-[18px]" aria-hidden="true">logout</span>Log out
          </button>
        </div>
      )}
    </div>
  );
}

export default function TopBar({ onToggleNav, collapsed }) {
  const { pathname, hash } = useLocation();
  const item = activeItem(pathname, hash);
  const { caseData, backendStatus } = useWorkspace();
  return (
    <header className="sticky top-0 z-30 h-14 bg-white/95 backdrop-blur border-b border-line">
      <div className="h-full flex items-center gap-3 px-3 lg:px-5">
        <button type="button" onClick={onToggleNav} className="ui-btn-ghost px-2 py-1.5"
          aria-label={typeof collapsed === 'boolean' ? (collapsed ? 'Expand sidebar' : 'Collapse sidebar') : 'Open navigation'}>
          <span className="material-symbols-outlined text-[22px]" aria-hidden="true">menu</span>
        </button>
        <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
          <ol className="flex items-center gap-1.5 text-[13px] min-w-0">
            <li className="hidden sm:block text-ink-muted"><Link to="/dashboard" className="hover:text-ink">Home</Link></li>
            {item && <li className="hidden sm:block text-ink-muted/60" aria-hidden="true">/</li>}
            {item && <li className="hidden md:block text-ink-muted">{item.group}</li>}
            {item && <li className="hidden md:block text-ink-muted/60" aria-hidden="true">/</li>}
            {item && <li className="font-semibold text-ink truncate" aria-current="page">{item.label}</li>}
          </ol>
        </nav>
        <div className="flex items-center gap-2 shrink-0">
          <span className="hidden lg:inline-flex"><StatusPill status={backendStatus} /></span>
          {caseData?.case_id && (
            <Link to={`/digital-twin?case=${encodeURIComponent(caseData.case_id)}`} className="hidden sm:inline-flex ui-chip-info hover:bg-white"
              title="Active case in this session — open it in the Digital Twin">
              <span className="material-symbols-outlined text-[14px]" aria-hidden="true">assignment</span>
              Case {caseData.case_id}
            </Link>
          )}
          <AccountMenu />
        </div>
      </div>
    </header>
  );
}
