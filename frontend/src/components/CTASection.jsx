import React from 'react';
import { Link } from 'react-router-dom';

export default function CTASection() {
  return (
    <section className="w-full py-space-2xl">
      <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop">
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-primary-container via-primary to-primary-container p-space-2xl text-on-primary shadow-[0_12px_40px_rgba(10,37,64,0.25)]">
          {/* Ambient radial shine */}
          <div className="absolute top-0 right-0 w-96 h-96 bg-secondary opacity-20 rounded-full blur-3xl pointer-events-none"></div>
          <div className="relative z-10 max-w-2xl">
            <span className="font-label-sm text-label-sm text-secondary-fixed uppercase tracking-wider font-semibold block mb-space-xs">
              Open Research Workspace
            </span>
            <h2 className="font-headline-lg text-headline-lg text-on-primary mb-space-md tracking-tight">
              Explore rare-disease intelligence with evidence at every step.
            </h2>
            <p className="font-body-lg text-body-lg text-on-primary-container mb-space-xl">
              Transform unstructured clinical observations into structured, retrievable, and explainable biomedical insights tailored to population realities.
            </p>
            <div className="flex flex-wrap items-center gap-space-md">
              <Link
                to="/dashboard"
                className="inline-flex items-center justify-center gap-space-xs px-space-lg py-space-sm rounded-lg font-label-md text-label-md text-primary bg-secondary-fixed hover:bg-on-secondary transition-all shadow-[0_2px_8px_rgba(0,0,0,0.1)]"
              >
                <span>Launch Diagnostic Assistant</span>
                <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
              </Link>
              <a
                href="#technology"
                className="inline-flex items-center justify-center gap-space-xs px-space-lg py-space-sm rounded-lg font-label-md text-label-md text-on-primary bg-surface-container-lowest/10 hover:bg-surface-container-lowest/20 transition-colors"
              >
                <span>View Research Architecture</span>
                <span className="material-symbols-outlined text-[18px]">architecture</span>
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
