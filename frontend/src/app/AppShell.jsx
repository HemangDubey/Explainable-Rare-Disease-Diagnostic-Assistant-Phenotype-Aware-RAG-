// Internal application shell: sidebar + top bar + routed content. The sidebar's collapsed state is a non-sensitive UI preference
// kept in localStorage; the mobile drawer closes on every navigation. Content width adapts to the sidebar without layout jumps.
import React, { useCallback, useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import { activeItem } from './navigation';

const PREF = 'rd_sidebar_collapsed';
const WIDE_ROUTES = ['/digital-twin'];

function readCollapsed() {
  try { return localStorage.getItem(PREF) === '1'; } catch (e) { return false; }
}

function useIsDesktop() {
  const q = '(min-width: 1024px)';
  const [d, setD] = useState(() => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(q).matches : true));
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const m = window.matchMedia(q);
    const on = (e) => setD(e.matches);
    m.addEventListener ? m.addEventListener('change', on) : m.addListener(on);
    return () => (m.removeEventListener ? m.removeEventListener('change', on) : m.removeListener(on));
  }, []);
  return d;
}

export default function AppShell() {
  const { pathname, hash } = useLocation();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const desktop = useIsDesktop();

  const toggleCollapsed = useCallback(() => {
    setCollapsed((v) => {
      try { localStorage.setItem(PREF, v ? '0' : '1'); } catch (e) { /* preference not saved; works for this page */ }
      return !v;
    });
  }, []);
  const closeMobile = useCallback(() => setMobileOpen(false), []);

  useEffect(() => { setMobileOpen(false); }, [pathname, hash]);
  useEffect(() => { if (desktop) setMobileOpen(false); }, [desktop]);
  useEffect(() => {
    const item = activeItem(pathname, hash);
    document.title = `${item ? item.label : 'Workspace'} · Explainable Rare-Disease Diagnostic Assistant`;
  }, [pathname, hash]);

  const wide = WIDE_ROUTES.includes(pathname);
  return (
    <div className="app-shell min-h-screen bg-[#f3f7fa] text-ink">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] ui-btn-primary">Skip to content</a>
      <Sidebar collapsed={collapsed} onToggleCollapsed={toggleCollapsed} mobileOpen={mobileOpen} onCloseMobile={closeMobile} />
      <div className={`min-w-0 flex flex-col min-h-screen transition-[padding] duration-200 ease-out ${collapsed ? 'lg:pl-16' : 'lg:pl-64'}`}>
        <TopBar onToggleNav={desktop ? toggleCollapsed : () => setMobileOpen(true)} collapsed={desktop ? collapsed : undefined} />
        <main id="main-content" tabIndex={-1} className={`flex-1 w-full mx-auto px-3 sm:px-5 lg:px-6 py-5 focus:outline-none ${wide ? 'max-w-[1720px]' : 'max-w-[1320px]'}`}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
