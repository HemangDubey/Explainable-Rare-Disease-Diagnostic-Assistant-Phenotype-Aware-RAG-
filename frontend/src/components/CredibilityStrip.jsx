import React from 'react';

export default function CredibilityStrip() {
  return (
    <section className="w-full bg-surface-container-low py-space-lg">
      <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop">
        <div className="flex flex-col md:flex-row items-center justify-between gap-space-md">
          <span className="font-label-md text-label-md text-on-surface-variant font-semibold uppercase tracking-wider text-center md:text-left">
            Built around structured biomedical knowledge and evidence retrieval
          </span>
          <div className="flex flex-wrap items-center justify-center gap-space-sm">
            <div className="px-space-md py-space-xs rounded-lg bg-surface-container-lowest shadow-sm flex items-center gap-space-xs text-primary font-headline-sm text-headline-sm font-semibold">
              <span className="text-secondary font-code-metric text-label-md">HPO</span>
              <span className="font-body-sm text-body-sm text-on-surface-variant hidden sm:inline">Human Phenotype</span>
            </div>
            <div className="px-space-md py-space-xs rounded-lg bg-surface-container-lowest shadow-sm flex items-center gap-space-xs text-primary font-headline-sm text-headline-sm font-semibold">
              <span className="text-secondary font-code-metric text-label-md">OMIM</span>
              <span className="font-body-sm text-body-sm text-on-surface-variant hidden sm:inline">Mendelian Inheritance</span>
            </div>
            <div className="px-space-md py-space-xs rounded-lg bg-surface-container-lowest shadow-sm flex items-center gap-space-xs text-primary font-headline-sm text-headline-sm font-semibold">
              <span className="text-secondary font-code-metric text-label-md">Orphanet</span>
            </div>
            <div className="px-space-md py-space-xs rounded-lg bg-surface-container-lowest shadow-sm flex items-center gap-space-xs text-primary font-headline-sm text-headline-sm font-semibold">
              <span className="text-secondary font-code-metric text-label-md">PMC</span>
              <span className="font-body-sm text-body-sm text-on-surface-variant hidden sm:inline">Literature</span>
            </div>
            <div className="px-space-md py-space-xs rounded-lg bg-surface-container-lowest shadow-sm flex items-center gap-space-xs text-primary font-headline-sm text-headline-sm font-semibold">
              <span className="text-secondary font-code-metric text-label-md">IndiGen</span>
              <span className="font-body-sm text-body-sm text-on-surface-variant hidden sm:inline">Genome Variation</span>
            </div>
            <div className="px-space-md py-space-xs rounded-lg bg-surface-container-lowest shadow-sm flex items-center gap-space-xs text-primary font-headline-sm text-headline-sm font-semibold">
              <span className="text-secondary font-code-metric text-label-md">gnomAD</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
