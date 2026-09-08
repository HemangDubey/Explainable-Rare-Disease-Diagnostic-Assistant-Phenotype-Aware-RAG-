import React from 'react';
import { Link } from 'react-router-dom';
import BrandLogo from './BrandLogo';

export default function HeroSection() {
  return (
    <section className="relative w-full overflow-hidden pb-space-3xl pt-space-xl">
      {/* Ambient biomedical gradient illumination */}
      <div className="absolute -top-32 left-1/4 -z-10 h-96 w-96 rounded-full bg-secondary-fixed opacity-40 blur-3xl pointer-events-none"></div>
      <div className="absolute top-48 right-10 -z-10 h-80 w-80 rounded-full bg-primary-fixed opacity-30 blur-3xl pointer-events-none"></div>
      
      <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-2xl items-center">
          {/* Left Column (Clinical Context & Direct Actions) */}
          <div className="lg:col-span-6 flex flex-col items-start">
            {/* Eyebrow Pill Badge */}
            <div className="inline-flex items-center gap-space-xs px-space-sm py-space-3xs rounded-full bg-secondary-fixed/30 shadow-[0_1px_3px_rgba(9,30,58,0.04)] mb-space-md">
              <span className="w-2 h-2 rounded-full bg-secondary animate-pulse"></span>
              <span className="font-label-sm text-label-sm text-secondary tracking-wider font-semibold uppercase">
                Explainable Biomedical AI
              </span>
            </div>
            
            {/* Editorial Heading */}
            <h1 className="font-display-hero text-display-hero text-primary mb-space-md tracking-tight">
              From Clinical Phenotypes to{" "}
              <span className="text-secondary bg-clip-text text-transparent bg-gradient-to-r from-primary via-secondary to-on-tertiary-container">
                Explainable Rare-Disease Insights.
              </span>
            </h1>
            
            {/* Body Description */}
            <p className="font-body-lg text-body-lg text-on-surface-variant mb-space-xl max-w-xl">
              An evidence-driven diagnostic assistant that extracts clinical phenotypes, retrieves rare-disease knowledge, incorporates Indian population priors, and generates transparent, evidence-linked diagnostic insights.
            </p>
            
            {/* CTAs */}
            <div className="flex flex-wrap items-center gap-space-md mb-space-xl w-full sm:w-auto">
              <Link
                to="/dashboard"
                className="inline-flex items-center justify-center gap-space-xs px-space-lg py-space-sm rounded-lg font-label-md text-label-md text-on-primary bg-primary-container hover:bg-primary shadow-[0_4px_16px_rgba(10,37,64,0.2)] transition-all group"
              >
                <span>Launch Diagnostic Assistant</span>
                <span className="material-symbols-outlined text-[18px] group-hover:translate-x-0.5 transition-transform">
                  arrow_forward
                </span>
              </Link>
              <a
                href="#research"
                className="inline-flex items-center justify-center gap-space-xs px-space-lg py-space-sm rounded-lg font-label-md text-label-md text-on-surface bg-surface-container hover:bg-surface-container-high transition-colors"
              >
                <span>Explore the Research</span>
                <span className="material-symbols-outlined text-[18px] text-on-surface-variant">
                  upload_file
                </span>
              </a>
            </div>
            
            {/* Trust Strip */}
            <div className="pt-space-md border-t-0 flex flex-wrap items-center gap-y-space-xs gap-x-space-md text-on-surface-variant font-label-sm text-label-sm uppercase tracking-wider">
              <span className="inline-flex items-center gap-space-3xs text-secondary font-semibold">
                <span className="material-symbols-outlined text-[14px]">verified</span> Evidence-linked
              </span>
              <span className="w-1 h-1 rounded-full bg-outline-variant"></span>
              <span>Phenotype-aware</span>
              <span className="w-1 h-1 rounded-full bg-outline-variant"></span>
              <span>Population-aware</span>
              <span className="w-1 h-1 rounded-full bg-outline-variant"></span>
              <span>Fully Explainable</span>
            </div>
          </div>

          {/* Right Column (2.5D Molecular Diagram & Translucent Product Demo) */}
          <div className="lg:col-span-6 relative flex flex-col items-center justify-center">
            {/* Central Interactive Genomic Card */}
            <div className="relative w-full rounded-xl p-space-lg bg-surface-container-lowest/80 backdrop-blur-md shadow-[0_8px_32px_rgba(9,30,58,0.06)] flex flex-col items-center shadow-md">
              {/* Orbiting Micro-Tokens Container */}
              <div className="relative w-full max-w-sm h-64 flex items-center justify-center my-space-xs">
                {/* Subtle Orbital Ring SVGs */}
                <svg
                  className="absolute inset-0 w-full h-full text-surface-container-highest"
                  fill="none"
                  viewBox="0 0 400 300"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <circle className="opacity-60" cx="200" cy="150" r="110" stroke="currentColor" strokeDasharray="4 6" strokeWidth="1"></circle>
                  <circle className="opacity-40" cx="200" cy="150" r="70" stroke="currentColor" strokeDasharray="3 3" strokeWidth="1"></circle>
                  <line stroke="currentColor" strokeDasharray="2 4" strokeWidth="1" x1="80" x2="160" y1="70" y2="130"></line>
                  <line stroke="currentColor" strokeDasharray="2 4" strokeWidth="1" x1="320" x2="240" y1="80" y2="130"></line>
                  <line stroke="currentColor" strokeDasharray="2 4" strokeWidth="1" x1="100" x2="170" y1="230" y2="180"></line>
                  <line stroke="currentColor" strokeDasharray="2 4" strokeWidth="1" x1="300" x2="230" y1="220" y2="180"></line>
                </svg>

                {/* Central Emblem DNA Asset */}
                <div className="relative z-10 w-28 h-28 flex items-center justify-center rounded-2xl bg-surface-container p-space-xs shadow-[0_4px_24px_rgba(0,104,116,0.12)]">
                  <img src="/genomic-graph.jpg" className="w-full h-full object-contain" alt="Genomic Graph Structure" />
                </div>

                {/* Orbiting Semantic Badges */}
                <div className="absolute top-2 left-6 px-space-xs py-space-3xs rounded-full bg-surface-container-high text-primary font-code-metric text-label-sm shadow-sm flex items-center gap-space-3xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-secondary"></span> HPO:0001263
                </div>
                <div className="absolute top-6 right-8 px-space-xs py-space-3xs rounded-full bg-secondary-fixed/40 text-on-secondary-fixed-variant font-label-sm text-label-sm font-semibold shadow-sm">
                  Rare Disease
                </div>
                <div className="absolute bottom-6 left-8 px-space-xs py-space-3xs rounded-full bg-primary-fixed/50 text-on-primary-fixed-variant font-label-sm text-label-sm font-semibold shadow-sm">
                  IndiGen Allele Prior
                </div>
                <div className="absolute bottom-4 right-6 px-space-xs py-space-3xs rounded-full bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm shadow-sm flex items-center gap-space-3xs">
                  <span className="material-symbols-outlined text-[12px] text-secondary">database</span> 47 Sources
                </div>
              </div>

              {/* Floating Translucent Preview Panel */}
              <div className="w-full bg-surface-container-low/90 rounded-lg p-space-md shadow-[0_4px_16px_rgba(9,30,58,0.05)] mt-space-sm">
                <div className="flex items-center justify-between pb-space-xs mb-space-sm border-b-0">
                  <div className="flex items-center gap-space-xs">
                    <span className="material-symbols-outlined text-secondary text-[18px]">psychology</span>
                    <span className="font-headline-sm text-headline-sm text-primary">AI Evidence Synthesis</span>
                  </div>
                  <span className="px-space-xs py-space-3xs rounded-full bg-surface-container text-on-surface-variant font-label-sm text-label-sm">
                    ILLUSTRATIVE DEMO
                  </span>
                </div>

                {/* 4-Stat Metric Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-space-xs mb-space-sm">
                  <div className="bg-surface-container-lowest p-space-xs rounded-lg text-center">
                    <span className="block font-headline-md text-headline-md text-primary font-bold">08</span>
                    <span className="block font-label-sm text-label-sm text-on-surface-variant">Phenotypes</span>
                  </div>
                  <div className="bg-surface-container-lowest p-space-xs rounded-lg text-center">
                    <span className="block font-headline-md text-headline-md text-primary font-bold">12</span>
                    <span className="block font-label-sm text-label-sm text-on-surface-variant">Candidates</span>
                  </div>
                  <div className="bg-surface-container-lowest p-space-xs rounded-lg text-center">
                    <span className="block font-headline-md text-headline-md text-primary font-bold">47</span>
                    <span className="block font-label-sm text-label-sm text-on-surface-variant">Evidence Refs</span>
                  </div>
                  <div className="bg-surface-container-lowest p-space-xs rounded-lg text-center flex flex-col justify-center items-center">
                    <span className="inline-flex items-center text-secondary font-label-md text-label-md font-bold gap-space-3xs">
                      <span className="material-symbols-outlined text-[16px]">check_circle</span> 94.2%
                    </span>
                    <span className="block font-label-sm text-label-sm text-on-surface-variant">Confidence</span>
                  </div>
                </div>
                <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm bg-surface-container-high/60 p-space-xs rounded">
                  <span className="material-symbols-outlined text-[14px] text-secondary">info</span>
                  <span>Clinical verification mode: Demonstration telemetry values. Not actual clinical statistics.</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
