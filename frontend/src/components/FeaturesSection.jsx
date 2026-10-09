import React from 'react';

export default function FeaturesSection() {
  return (
    <section className="w-full bg-surface-container-low py-space-3xl" id="platform">
      <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop">
        <div className="text-center max-w-2xl mx-auto mb-space-2xl">
          <span className="font-label-sm text-label-sm text-secondary font-semibold uppercase tracking-wider block mb-space-2xs">
            System Capabilities
          </span>
          <h2 className="font-headline-lg text-headline-lg text-primary tracking-tight">
            Built as a research platform, not a black box.
          </h2>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-space-xs">
            Designed specifically for clinical geneticists, medical researchers, and diagnostic laboratories.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-space-lg">
          {/* Feature 1 */}
          <div className="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col justify-between">
            <div>
              <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-secondary mb-space-md">
                <span className="material-symbols-outlined text-[20px]">cognition</span>
              </div>
              <h3 className="font-title-md text-title-md text-primary mb-space-xs">01 Phenotype-aware NLP</h3>
              <p className="font-body-sm text-body-sm text-on-surface-variant">
                Fine-tuned biomedical transformer models extract phenotypic descriptions directly from clinical consultation notes into standardized HPO identifiers.
              </p>
            </div>
            <div className="mt-space-md pt-space-xs font-code-metric text-label-sm text-secondary">
              BiomedBERT + Clinical NER
            </div>
          </div>

          {/* Feature 2 */}
          <div className="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col justify-between">
            <div>
              <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-secondary mb-space-md">
                <span className="material-symbols-outlined text-[20px]">travel_explore</span>
              </div>
              <h3 className="font-title-md text-title-md text-primary mb-space-xs">02 Grounded Retrieval</h3>
              <p className="font-body-sm text-body-sm text-on-surface-variant">
                Structured multi-hop retrieval connects clinical findings to Orphanet knowledge graphs, PubMed Central papers, and OMIM curated records.
              </p>
            </div>
            <div className="mt-space-md pt-space-xs font-code-metric text-label-sm text-secondary">
              Dense Vector + Graph RAG
            </div>
          </div>

          {/* Feature 3 */}
          <div className="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col justify-between">
            <div>
              <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-secondary mb-space-md">
                <span className="material-symbols-outlined text-[20px]">groups</span>
              </div>
              <h3 className="font-title-md text-title-md text-primary mb-space-xs">03 Population Priors</h3>
              <p className="font-body-sm text-body-sm text-on-surface-variant">
                Reports gnomAD (global and South Asian) allele-frequency evidence for each candidate's genes. IndiGen is unavailable and the population weight is 0, so this evidence is shown but does not change the ranking.
              </p>
            </div>
            <div className="mt-space-md pt-space-xs font-code-metric text-label-sm text-secondary">
              gnomAD evidence (IndiGen unavailable)
            </div>
          </div>

          {/* Feature 4 */}
          <div className="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col justify-between">
            <div>
              <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-secondary mb-space-md">
                <span className="material-symbols-outlined text-[20px]">fact_check</span>
              </div>
              <h3 className="font-title-md text-title-md text-primary mb-space-xs">04 Explainable Output</h3>
              <p className="font-body-sm text-body-sm text-on-surface-variant">
                Every diagnostic suggestion is paired with specific phenotype overlap metrics, scientific literature citations, and transparent score breakdowns.
              </p>
            </div>
            <div className="mt-space-md pt-space-xs font-code-metric text-label-sm text-secondary">
              Traceable Provenance Cards
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
