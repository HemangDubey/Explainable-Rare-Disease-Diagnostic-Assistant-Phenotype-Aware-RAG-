import React from 'react';
import { Link } from 'react-router-dom';
import Navbar from '../components/Navbar';
import BrandLogo from '../components/BrandLogo';

export default function DashboardPage() {
  return (
    <>
      <Navbar />
      <main className="w-full pt-20 bg-surface min-h-screen">
        <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop py-space-3xl">
          <div className="flex flex-col items-center justify-center text-center gap-space-xl min-h-[60vh]">
            {/* Brand Emblem */}
            <div className="w-24 h-24 rounded-2xl bg-surface-container-lowest shadow-[0_8px_32px_rgba(0,104,116,0.12)] flex items-center justify-center p-space-sm">
              <BrandLogo className="w-full h-full object-contain" />
            </div>

            {/* Status Badge */}
            <div className="inline-flex items-center gap-space-xs px-space-md py-space-2xs rounded-full bg-secondary-fixed/30 shadow-sm">
              <span className="w-2 h-2 rounded-full bg-secondary animate-pulse"></span>
              <span className="font-label-sm text-label-sm text-secondary tracking-wider font-semibold uppercase">
                Under Construction
              </span>
            </div>

            {/* Heading */}
            <div className="max-w-2xl">
              <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight mb-space-md">
                Diagnostic Assistant Workspace
              </h1>
              <p className="font-body-lg text-body-lg text-on-surface-variant">
                The interactive clinical diagnostic workspace is currently being developed. This dashboard will provide phenotype extraction, knowledge retrieval, population-aware re-ranking, and explainable diagnostic insights — all in one unified interface.
              </p>
            </div>

            {/* Feature Preview Chips */}
            <div className="flex flex-wrap items-center justify-center gap-space-sm">
              {[
                { icon: 'psychology_alt', label: 'Phenotype NER' },
                { icon: 'manage_search', label: 'Knowledge RAG' },
                { icon: 'tune', label: 'Population Prior' },
                { icon: 'fact_check', label: 'Explainable Cards' },
              ].map((f) => (
                <div
                  key={f.label}
                  className="px-space-md py-space-xs rounded-lg bg-surface-container-lowest shadow-sm flex items-center gap-space-xs"
                >
                  <span className="material-symbols-outlined text-secondary text-[18px]">{f.icon}</span>
                  <span className="font-label-md text-label-md text-primary">{f.label}</span>
                </div>
              ))}
            </div>

            {/* API Endpoint Info */}
            <div className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm max-w-lg w-full">
              <div className="flex items-center gap-space-xs mb-space-sm">
                <span className="material-symbols-outlined text-secondary text-[18px]">api</span>
                <span className="font-title-md text-title-md text-primary">API Endpoints Available</span>
              </div>
              <div className="flex flex-col gap-space-xs">
                <div className="flex items-center justify-between p-space-xs rounded bg-surface-container-low">
                  <span className="font-code-metric text-label-sm text-secondary">POST /api/retrieve</span>
                  <span className="px-space-xs py-space-3xs rounded bg-secondary-fixed/40 font-label-sm text-label-sm text-on-secondary-fixed-variant font-semibold">Phase 2</span>
                </div>
                <div className="flex items-center justify-between p-space-xs rounded bg-surface-container-low">
                  <span className="font-code-metric text-label-sm text-secondary">POST /api/rank</span>
                  <span className="px-space-xs py-space-3xs rounded bg-primary-fixed/40 font-label-sm text-label-sm text-on-primary-fixed font-semibold">Phase 3</span>
                </div>
              </div>
            </div>

            {/* Back Link */}
            <Link
              to="/"
              className="inline-flex items-center justify-center gap-space-xs px-space-lg py-space-sm rounded-lg font-label-md text-label-md text-on-surface bg-surface-container hover:bg-surface-container-high transition-colors mt-space-md"
            >
              <span className="material-symbols-outlined text-[18px]">arrow_back</span>
              <span>Return to Landing Page</span>
            </Link>
          </div>
        </div>
      </main>
    </>
  );
}
