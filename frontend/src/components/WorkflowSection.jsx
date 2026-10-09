import React from 'react';

export default function WorkflowSection() {
  return (
    <section className="w-full bg-surface-container-low py-space-3xl" id="how-it-works">
      <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop">
        <div className="max-w-2xl mb-space-2xl">
          <span className="font-label-sm text-label-sm text-secondary font-semibold uppercase tracking-wider block mb-space-2xs">
            System Workflow
          </span>
          <h2 className="font-headline-lg text-headline-lg text-primary tracking-tight">
            From clinical narrative to explainable insight.
          </h2>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-space-xs">
            A sequential, deterministic multi-agent pipeline anchored by biomedical ontology norms and population-frequency evidence.
          </p>
        </div>

        {/* 5-Step Connected Flow Grid */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-space-md relative">
          {/* Step 1 */}
          <div className="bg-surface-container-lowest p-space-md rounded-xl shadow-sm flex flex-col justify-between relative group hover:shadow-md transition-shadow">
            <div>
              <div className="flex items-center justify-between mb-space-md">
                <span className="w-8 h-8 rounded-full bg-primary text-on-primary font-code-metric text-label-sm flex items-center justify-center font-bold">01</span>
                <span className="material-symbols-outlined text-on-surface-variant text-[20px]">mic</span>
              </div>
              <h4 className="font-title-md text-title-md text-primary mb-space-2xs">Clinical Ingestion</h4>
              <p className="font-body-sm text-body-sm text-on-surface-variant mb-space-sm">
                Multimodal case capture across raw text, dictation, pathology lab reports, or referral letters.
              </p>
            </div>
            <div className="bg-surface-container p-space-2xs rounded text-center font-code-metric text-label-sm text-secondary">
              Text • Audio • PDF
            </div>
          </div>

          {/* Step 2 */}
          <div className="bg-surface-container-lowest p-space-md rounded-xl shadow-sm flex flex-col justify-between relative group hover:shadow-md transition-shadow">
            <div>
              <div className="flex items-center justify-between mb-space-md">
                <span className="w-8 h-8 rounded-full bg-primary text-on-primary font-code-metric text-label-sm flex items-center justify-center font-bold">02</span>
                <span className="material-symbols-outlined text-secondary text-[20px]">psychology_alt</span>
              </div>
              <h4 className="font-title-md text-title-md text-primary mb-space-2xs">Phenotype NER</h4>
              <p className="font-body-sm text-body-sm text-on-surface-variant mb-space-sm">
                Transformer-based entity recognition mapping lay terminology into standardized HPO identifiers.
              </p>
            </div>
            <div className="bg-surface-container p-space-2xs rounded text-center font-code-metric text-label-sm text-secondary">
              HPO Concept Matching
            </div>
          </div>

          {/* Step 3 */}
          <div className="bg-surface-container-lowest p-space-md rounded-xl shadow-sm flex flex-col justify-between relative group hover:shadow-md transition-shadow">
            <div>
              <div className="flex items-center justify-between mb-space-md">
                <span className="w-8 h-8 rounded-full bg-primary text-on-primary font-code-metric text-label-sm flex items-center justify-center font-bold">03</span>
                <span className="material-symbols-outlined text-secondary text-[20px]">manage_search</span>
              </div>
              <h4 className="font-title-md text-title-md text-primary mb-space-2xs">Knowledge RAG</h4>
              <p className="font-body-sm text-body-sm text-on-surface-variant mb-space-sm">
                Dense vector retrieval spanning Orphanet graphs, PubMed vectors, and curated rare-syndrome ontologies.
              </p>
            </div>
            <div className="bg-surface-container p-space-2xs rounded text-center font-code-metric text-label-sm text-secondary">
              HPO + Vector Hops
            </div>
          </div>

          {/* Step 4 */}
          <div className="bg-surface-container-lowest p-space-md rounded-xl shadow-sm flex flex-col justify-between relative group hover:shadow-md transition-shadow">
            <div>
              <div className="flex items-center justify-between mb-space-md">
                <span className="w-8 h-8 rounded-full bg-secondary text-on-secondary font-code-metric text-label-sm flex items-center justify-center font-bold">04</span>
                <span className="material-symbols-outlined text-secondary text-[20px]">tune</span>
              </div>
              <h4 className="font-title-md text-title-md text-primary mb-space-2xs">Population Prior</h4>
              <p className="font-body-sm text-body-sm text-on-surface-variant mb-space-sm">
                gnomAD global and South Asian frequency evidence per gene, reported separately. IndiGen is unavailable; the population weight is 0, so ranking is unchanged.
              </p>
            </div>
            <div className="bg-surface-container p-space-2xs rounded text-center font-code-metric text-label-sm text-secondary">
              Frequency Evidence
            </div>
          </div>

          {/* Step 5 */}
          <div className="bg-surface-container-lowest p-space-md rounded-xl shadow-sm flex flex-col justify-between relative group hover:shadow-md transition-shadow">
            <div>
              <div className="flex items-center justify-between mb-space-md">
                <span className="w-8 h-8 rounded-full bg-primary-container text-on-primary font-code-metric text-label-sm flex items-center justify-center font-bold">05</span>
                <span className="material-symbols-outlined text-secondary text-[20px]">fact_check</span>
              </div>
              <h4 className="font-title-md text-title-md text-primary mb-space-2xs">Explainable Card</h4>
              <p className="font-body-sm text-body-sm text-on-surface-variant mb-space-sm">
                Deterministic evidence synthesis with point-by-point provenance links, match bars, and literature PMIDs.
              </p>
            </div>
            <div className="bg-surface-container p-space-2xs rounded text-center font-code-metric text-label-sm text-secondary">
              Cited Evidence Trails
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
