import React from 'react';
import { Link } from 'react-router-dom';
import BrandLogo from './BrandLogo';

export default function Navbar() {
  return (
    <header className="fixed top-0 w-full z-50 bg-surface/85 backdrop-blur-md shadow-[0_1px_8px_rgba(0,0,0,0.04)]">
      <div className="h-20 max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop flex items-center justify-between">
        <Link to="/" className="flex items-center gap-space-sm">
          <BrandLogo />
          <div className="flex flex-col">
            <span className="font-headline-sm text-headline-sm text-primary leading-tight tracking-tight">
              Explainable Rare-Disease Diagnostic Assistant
            </span>
            <span className="font-label-sm text-label-sm text-secondary uppercase tracking-wider font-semibold">
              Phenotype-Aware RAG
            </span>
          </div>
        </Link>

        <nav className="hidden xl:flex items-center gap-space-md">
          <a
            className="px-space-xs py-space-2xs transition-colors bg-surface-container-high text-on-surface font-semibold rounded-lg"
            href="#platform"
          >
            Platform
          </a>
          <a
            className="px-space-xs py-space-2xs text-on-surface-variant font-label-md text-label-md transition-colors hover:text-on-surface hover:bg-surface-container-high rounded-lg"
            href="#how-it-works"
          >
            How It Works
          </a>
          <a
            className="px-space-xs py-space-2xs text-on-surface-variant font-label-md text-label-md transition-colors hover:text-on-surface hover:bg-surface-container-high rounded-lg"
            href="#research"
          >
            Research
          </a>
          <a
            className="px-space-xs py-space-2xs text-on-surface-variant font-label-md text-label-md transition-colors hover:text-on-surface hover:bg-surface-container-high rounded-lg"
            href="#technology"
          >
            Technology
          </a>
          <a
            className="px-space-xs py-space-2xs text-on-surface-variant font-label-md text-label-md transition-colors hover:text-on-surface hover:bg-surface-container-high rounded-lg"
            href="#evidence"
          >
            Evidence
          </a>
        </nav>

        <div className="flex items-center gap-space-sm">
          <a
            className="hidden sm:inline-flex items-center justify-center px-space-md py-space-2xs rounded-lg font-label-md text-label-md text-primary bg-surface-container-lowest shadow-[0_1px_3px_rgba(9,30,58,0.05)] hover:bg-surface-container transition-colors"
            href="#research"
          >
            Research Portal
          </a>
          <Link
            to="/dashboard"
            className="inline-flex items-center justify-center px-space-md py-space-2xs rounded-lg font-label-md text-label-md text-on-primary bg-primary-container hover:bg-primary shadow-[0_2px_8px_rgba(10,37,64,0.15)] transition-all"
          >
            Launch Diagnostic Assistant
          </Link>
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center ml-space-2xs">
            <span className="material-symbols-outlined text-on-primary text-[18px]">
              person
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
