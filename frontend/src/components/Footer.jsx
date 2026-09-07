import React from 'react';
import BrandLogo from './BrandLogo';

export default function Footer() {
  return (
    <footer className="w-full bg-surface-container-low py-space-2xl mt-space-3xl">
      <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop flex flex-col gap-space-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-lg">
          <div className="flex items-center gap-space-sm">
            <BrandLogo className="h-8 w-auto object-contain" />
            <div>
              <p className="font-headline-sm text-headline-sm text-primary leading-tight">Explainable Rare-Disease Diagnostic Assistant</p>
              <p className="font-body-sm text-body-sm text-on-surface-variant">Phenotype-Aware RAG with Indian Population Priors</p>
            </div>
          </div>
          <nav className="flex flex-wrap items-center gap-space-md">
            <a className="transition-colors text-on-surface font-semibold" href="#platform">Platform</a>
            <a className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors" href="#research">Research</a>
            <a className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors" href="#technology">Technology</a>
            <a className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors" href="#evidence">Evidence</a>
            <a className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors" href="#">Dashboard</a>
            <a className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors" href="#">Documentation</a>
            <a className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors" href="#">GitHub</a>
          </nav>
        </div>
        <div className="flex flex-col md:flex-row items-center justify-between gap-space-sm pt-space-md text-on-surface-variant">
          <p className="font-body-sm text-body-sm">© 2024 Genomic Intelligence &amp; Computational Phenomics Lab. All rights reserved.</p>
          <p className="font-label-sm text-label-sm text-secondary uppercase tracking-wide">Research &amp; Clinical Decision Support Prototype — Not a substitute for professional medical diagnosis.</p>
        </div>
      </div>
    </footer>
  );
}
