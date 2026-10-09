// Collapsible left navigation. Desktop: a fixed rail (256 px expanded, 64 px collapsed, icons + tooltips). Below lg: an overlay drawer
// with a backdrop, closed by the close button, Escape, the backdrop or any navigation. Items come from app/navigation.js.
import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import BrandLogo from '../components/BrandLogo';
import { NAV_GROUPS, activeItem, itemHref } from './navigation';

function NavItem({ item, active, collapsed, location, onTip }) {
  // staying on the same page (e.g. Digital Twin sections): keep the query string so the open case is preserved
  const to = item.path === location.pathname ? { pathname: item.path, search: location.search, hash: item.hash || '' } : itemHref(item);
  return (
    <li>
      <Link to={to} aria-current={active ? 'page' : undefined} aria-label={collapsed ? item.label : undefined}
        onMouseEnter={collapsed ? (e) => onTip(item.label, e.currentTarget) : undefined} onMouseLeave={collapsed ? () => onTip(null) : undefined}
        onFocus={collapsed ? (e) => onTip(item.label, e.currentTarget) : undefined} onBlur={collapsed ? () => onTip(null) : undefined}
        title={collapsed ? undefined : item.description}
        className={`group relative flex items-center gap-3 rounded-lg mx-2 px-2.5 py-2 text-[13px] font-medium outline-none transition-colors
          focus-visible:ring-2 focus-visible:ring-ocean/40
          ${active ? 'bg-ocean-soft text-ocean' : 'text-ink-muted hover:bg-slate-50 hover:text-ink'}`}>
        {active && <span className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r bg-ocean -ml-2" aria-hidden="true" />}
        <span className="material-symbols-outlined text-[20px] shrink-0" aria-hidden="true">{item.icon}</span>
        {!collapsed && (
          <span className="min-w-0">
            <span className="block truncate">{item.label}</span>
            {active && item.description && <span className="block text-[11px] font-normal text-ink-muted/80 leading-snug">{item.description}</span>}
          </span>
        )}
      </Link>
    </li>
  );
}

function NavGroup({ group, current, collapsed, location, onTip }) {
  const containsActive = group.items.some((i) => current && i.id === current.id);
  const [open, setOpen] = useState(true);
  const shown = open || containsActive;
  const listId = `nav-group-${group.id}`;
  return (
    <div className="py-1">
      {collapsed ? (
        <div className="mx-4 my-2 border-t border-line" aria-hidden="true" />
      ) : (
        <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={shown} aria-controls={listId}
          className="w-full flex items-center justify-between px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-muted/80
            hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-ocean/40 rounded">
          {group.label}
          <span className={`material-symbols-outlined text-[16px] transition-transform ${shown ? '' : '-rotate-90'}`} aria-hidden="true">expand_more</span>
        </button>
      )}
      {(shown || collapsed) && (
        <ul id={listId} className="flex flex-col gap-0.5" aria-label={group.label}>
          {group.items.map((item) => (
            <NavItem key={item.id} item={item} active={!!current && current.id === item.id} collapsed={collapsed} location={location} onTip={onTip} />
          ))}
        </ul>
      )}
    </div>
  );
}

function SidebarBody({ collapsed, onToggleCollapsed, onClose, mobile }) {
  const location = useLocation();
  const current = activeItem(location.pathname, location.hash);
  // Collapsed rail: one floating tooltip, fixed-positioned so the scrolling nav cannot clip it (shown on hover and keyboard focus).
  const [tip, setTip] = useState(null);
  const onTip = (label, el) => setTip(label && el ? { label, top: el.getBoundingClientRect().top + el.offsetHeight / 2 } : null);
  useEffect(() => { setTip(null); }, [location.pathname, location.hash, collapsed]);
  const closeRef = useRef(null);
  useEffect(() => { if (mobile && closeRef.current) closeRef.current.focus(); }, [mobile]);
  return (
    <div className="flex h-full flex-col">
      <div className={`flex h-14 shrink-0 items-center border-b border-line ${collapsed ? 'justify-center px-2' : 'gap-2.5 px-4'}`}>
        <Link to="/dashboard" className="flex items-center gap-2.5 min-w-0 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ocean/40"
          aria-label="Diagnostic Workspace home">
          <BrandLogo className="h-8 w-8 object-contain shrink-0" alt="" />
          {!collapsed && (
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-[13px] font-bold text-ink">Rare-Disease Assistant</span>
              <span className="block truncate text-[10px] font-semibold uppercase tracking-wider text-secondary">Research workspace</span>
            </span>
          )}
        </Link>
        {mobile && (
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close navigation"
            className="ml-auto ui-btn-ghost px-2 py-1.5"><span className="material-symbols-outlined text-[20px]" aria-hidden="true">close</span></button>
        )}
      </div>
      <nav className="flex-1 overflow-y-auto overflow-x-hidden py-2" aria-label="Main navigation">
        {NAV_GROUPS.map((g) => <NavGroup key={g.id} group={g} current={current} collapsed={collapsed} location={location} onTip={onTip} />)}
      </nav>
      {collapsed && tip && (
        <div role="tooltip" style={{ top: tip.top }}
          className="pointer-events-none fixed left-[72px] z-50 -translate-y-1/2 whitespace-nowrap rounded-md bg-ink px-2 py-1 text-[12px] font-medium text-white shadow-md">
          {tip.label}
        </div>
      )}
      {!mobile && (
        <div className="shrink-0 border-t border-line p-2">
          <button type="button" onClick={onToggleCollapsed} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!collapsed}
            className={`ui-btn-ghost w-full ${collapsed ? 'px-0' : 'justify-start'}`}>
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true">{collapsed ? 'left_panel_open' : 'left_panel_close'}</span>
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      )}
    </div>
  );
}

export default function Sidebar({ collapsed, onToggleCollapsed, mobileOpen, onCloseMobile }) {
  useEffect(() => {
    if (!mobileOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onCloseMobile(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mobileOpen, onCloseMobile]);
  return (
    <>
      <aside className={`hidden lg:block fixed inset-y-0 left-0 z-40 bg-white border-r border-line transition-[width] duration-200 ease-out
        ${collapsed ? 'w-16' : 'w-64'}`} aria-label="Sidebar">
        <SidebarBody collapsed={collapsed} onToggleCollapsed={onToggleCollapsed} />
      </aside>
      {mobileOpen && (
        <div className="lg:hidden">
          <div className="fixed inset-0 z-40 bg-ink/40" onClick={onCloseMobile} aria-hidden="true" />
          <aside className="fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] bg-white shadow-xl" role="dialog" aria-modal="true" aria-label="Navigation">
            <SidebarBody collapsed={false} onClose={onCloseMobile} mobile />
          </aside>
        </div>
      )}
    </>
  );
}
