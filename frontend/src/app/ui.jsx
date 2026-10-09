// Shared page building blocks for the internal app (page header, empty / loading / error states).
import React from 'react';
import { Link } from 'react-router-dom';

export function PageHeader({ title, description, actions, children }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
      <div className="min-w-0">
        <h1 className="text-[22px] leading-7 font-semibold text-ink tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-[14px] text-ink-muted max-w-3xl">{description}</p>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ icon = 'inbox', title, children, action }) {
  return (
    <div className="ui-card px-6 py-10 text-center">
      <span className="material-symbols-outlined text-[40px] text-ocean/70" aria-hidden="true">{icon}</span>
      <h2 className="mt-2 text-[16px] font-semibold text-ink">{title}</h2>
      {children && <div className="mt-1 text-[14px] text-ink-muted max-w-lg mx-auto">{children}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function NeedsCase({ what }) {
  return (
    <EmptyState icon="assignment_add" title="No active case"
      action={<Link to="/dashboard" className="ui-btn-primary">Go to Diagnostic Workspace</Link>}>
      {what} needs a diagnosed case. Run a diagnosis in the Diagnostic Workspace first; the case stays active while you move between modules.
    </EmptyState>
  );
}

export function LoadingState({ label = 'Loading…' }) {
  return (
    <div className="ui-card px-6 py-8 flex items-center justify-center gap-2 text-[14px] text-ink-muted" role="status">
      <span className="ui-spinner text-ocean" aria-hidden="true" />{label}
    </div>
  );
}

export function ErrorAlert({ children, onRetry }) {
  return (
    <div className="ui-alert-error" role="alert">
      <span className="material-symbols-outlined text-[18px]" aria-hidden="true">error</span>
      <div className="flex-1">{children}</div>
      {onRetry && <button type="button" onClick={onRetry} className="ui-btn-secondary py-1">Retry</button>}
    </div>
  );
}
