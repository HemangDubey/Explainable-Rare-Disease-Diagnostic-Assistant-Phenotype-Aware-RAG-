import React from 'react';

export default function ArchitectureSection() {
  return (
    <section className="w-full py-space-3xl" id="technology">
      <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop">
        <div className="max-w-3xl mb-space-2xl">
          <span className="font-label-sm text-label-sm text-secondary font-semibold uppercase tracking-wider block mb-space-2xs">
            Architectural Blueprint
          </span>
          <h2 className="font-headline-lg text-headline-lg text-primary tracking-tight">
            An AI pipeline designed for transparency.
          </h2>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-space-xs">
            Each inferential transition operates as a discrete, inspectable stage. No black-box generative jumps without traceable biological provenance.
          </p>
        </div>

        {/* Node Architecture Diagram */}
        <div className="bg-surface-container-lowest rounded-2xl p-space-xl shadow-[0_4px_30px_rgba(9,30,58,0.04)] overflow-x-auto">
          <div className="min-w-[840px] flex flex-col gap-space-lg">
            {/* Layer 1: Ingestion & NER */}
            <div className="flex items-center justify-between gap-space-md">
              <div className="flex-1 bg-surface-container-low p-space-md rounded-lg shadow-sm">
                <div className="flex items-center justify-between mb-space-2xs">
                  <span className="font-headline-sm text-headline-sm text-primary">Unstructured EHR</span>
                  <span className="font-code-metric text-label-sm text-on-surface-variant">Input: raw_str</span>
                </div>
                <p className="font-body-sm text-body-sm text-on-surface-variant">Multimodal clinical notes, discharge summaries &amp; clinical observations.</p>
              </div>
              <span className="material-symbols-outlined text-secondary text-[24px]">arrow_forward</span>
              <div className="flex-1 bg-surface-container-low p-space-md rounded-lg shadow-sm">
                <div className="flex items-center justify-between mb-space-2xs">
                  <span className="font-headline-sm text-headline-sm text-primary">BiomedBERT NER</span>
                  <span className="px-space-2xs py-space-3xs rounded bg-surface-container font-code-metric text-label-sm text-secondary">dim=768</span>
                </div>
                <p className="font-body-sm text-body-sm text-on-surface-variant">Token-level classification &amp; biomedical entity span identification.</p>
              </div>
              <span className="material-symbols-outlined text-secondary text-[24px]">arrow_forward</span>
              <div className="flex-1 bg-surface-container-low p-space-md rounded-lg shadow-sm">
                <div className="flex items-center justify-between mb-space-2xs">
                  <span className="font-headline-sm text-headline-sm text-primary">HPO Normalizer</span>
                  <span className="font-code-metric text-label-sm text-secondary font-semibold">Ontology Linker</span>
                </div>
                <p className="font-body-sm text-body-sm text-on-surface-variant">Maps string phenotypes to canonical [HP:xxxxxxx] term identifiers.</p>
              </div>
            </div>

            {/* Connecting Visual Pipe */}
            <div className="flex justify-center items-center py-space-2xs text-secondary">
              <span className="material-symbols-outlined text-[28px]">south</span>
            </div>

            {/* Layer 2: Retrieval & Prior Fusion */}
            <div className="flex items-center justify-between gap-space-md">
              <div className="flex-1 bg-surface-container-low p-space-md rounded-lg shadow-sm">
                <div className="flex items-center justify-between mb-space-2xs">
                  <span className="font-headline-sm text-headline-sm text-primary">S-PubMedBERT + FAISS</span>
                  <span className="px-space-2xs py-space-3xs rounded bg-secondary-fixed/40 text-on-secondary-fixed font-code-metric text-label-sm">RAG Engine</span>
                </div>
                <p className="font-body-sm text-body-sm text-on-surface-variant">Multi-vector index matching phenotypic profiles to known syndrome corpora.</p>
              </div>
              <span className="material-symbols-outlined text-secondary text-[24px]">add</span>
              <div className="flex-1 bg-surface-container-low p-space-md rounded-lg shadow-sm">
                <div className="flex items-center justify-between mb-space-2xs">
                  <span className="font-headline-sm text-headline-sm text-primary">IndiGen Prior Engine</span>
                  <span className="px-space-2xs py-space-3xs rounded bg-primary-fixed/40 text-on-primary-fixed font-code-metric text-label-sm">Population Prior</span>
                </div>
                <p className="font-body-sm text-body-sm text-on-surface-variant">Allele frequency adjustments calculated across Indian sub-population cohorts.</p>
              </div>
              <span className="material-symbols-outlined text-secondary text-[24px]">arrow_forward</span>
              <div className="flex-1 bg-surface-container-low p-space-md rounded-lg shadow-sm">
                <div className="flex items-center justify-between mb-space-2xs">
                  <span className="font-headline-sm text-headline-sm text-primary">Bayesian Re-Ranker</span>
                  <span className="font-code-metric text-label-sm text-secondary font-semibold">P(D | Pheno, Pop)</span>
                </div>
                <p className="font-body-sm text-body-sm text-on-surface-variant">Calibrates posterior candidate disease distribution using combined priors.</p>
              </div>
            </div>

            {/* Connecting Visual Pipe */}
            <div className="flex justify-center items-center py-space-2xs text-secondary">
              <span className="material-symbols-outlined text-[28px]">south</span>
            </div>

            {/* Layer 3: Explainable Generation */}
            <div className="w-full bg-primary-container text-on-primary p-space-lg rounded-xl shadow-md flex flex-col md:flex-row items-center justify-between gap-space-lg">
              <div className="flex items-start gap-space-md">
                <span className="material-symbols-outlined text-secondary-fixed text-[36px]">auto_stories</span>
                <div>
                  <h3 className="font-headline-sm text-headline-sm text-on-primary mb-space-3xs">Transparent AI Explanation Engine</h3>
                  <p className="font-body-sm text-body-sm text-on-primary-container max-w-2xl">
                    Synthesizes retrieved clinical literature citations, HPO similarity metrics, and Indian population priors into structured, audit-ready clinical notes.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-space-sm shrink-0">
                <div className="text-right">
                  <span className="block font-code-metric text-label-sm text-secondary-fixed">LATENCY / STEP</span>
                  <span className="block font-code-metric text-headline-sm text-on-primary">~180ms</span>
                </div>
                <div className="w-2 h-10 bg-secondary-fixed rounded-full"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
