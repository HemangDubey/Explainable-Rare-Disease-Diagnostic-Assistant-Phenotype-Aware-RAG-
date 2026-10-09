import React from 'react';

export default function ProblemSection() {
  return (
    <section className="w-full py-space-3xl" id="problem">
      <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop">
        <div className="max-w-2xl mb-space-2xl">
          <span className="font-label-sm text-label-sm text-secondary font-semibold uppercase tracking-wider block mb-space-2xs">
            Diagnostic Bottleneck
          </span>
          <h2 className="font-headline-lg text-headline-lg text-primary tracking-tight">
            Rare-disease diagnosis is a knowledge retrieval problem.
          </h2>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-space-xs">
            Over 7,000 recognized rare conditions often take years to pinpoint. Clinicians navigate incomplete phenotyping, silod datasets, and population biases that obscure rare variants.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-lg mb-space-2xl">
          {/* Card 01 */}
          <div className="bg-surface-container-lowest rounded-xl p-space-xl shadow-[0_4px_20px_rgba(9,30,58,0.03)] flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-lg bg-surface-container flex items-center justify-center text-primary mb-space-lg">
                <span className="material-symbols-outlined text-[24px]">clinical_notes</span>
              </div>
              <span className="font-code-metric text-label-sm text-secondary block mb-space-2xs">CHALLENGE 01</span>
              <h3 className="font-headline-sm text-headline-sm text-primary mb-space-xs">Clinical Complexity</h3>
              <p className="font-body-md text-body-md text-on-surface-variant">
                Clinical cases contain scattered phenotype observations, inconsistent non-standardized terminology, and fragmented symptom chronologies that evade generic LLM parsers.
              </p>
            </div>
            <div className="mt-space-lg pt-space-sm flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-error"></span> Unstructured Electronic Health Records
            </div>
          </div>

          {/* Card 02 */}
          <div className="bg-surface-container-lowest rounded-xl p-space-xl shadow-[0_4px_20px_rgba(9,30,58,0.03)] flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-lg bg-surface-container flex items-center justify-center text-secondary mb-space-lg">
                <span className="material-symbols-outlined text-[24px]">schema</span>
              </div>
              <span className="font-code-metric text-label-sm text-secondary block mb-space-2xs">CHALLENGE 02</span>
              <h3 className="font-headline-sm text-headline-sm text-primary mb-space-xs">Knowledge Fragmentation</h3>
              <p className="font-body-md text-body-md text-on-surface-variant">
                Relevant clinical evidence is distributed across phenotype ontologies, genetic databases, disconnected case reports, and rapidly multiplying biomedical literature.
              </p>
            </div>
            <div className="mt-space-lg pt-space-sm flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-error"></span> High Cross-Ontology Disconnect
            </div>
          </div>

          {/* Card 03 */}
          <div className="bg-surface-container-lowest rounded-xl p-space-xl shadow-[0_4px_20px_rgba(9,30,58,0.03)] flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-lg bg-surface-container flex items-center justify-center text-on-tertiary-container mb-space-lg">
                <span className="material-symbols-outlined text-[24px]">public</span>
              </div>
              <span className="font-code-metric text-label-sm text-secondary block mb-space-2xs">CHALLENGE 03</span>
              <h3 className="font-headline-sm text-headline-sm text-primary mb-space-xs">Population Underrepresentation</h3>
              <p className="font-body-md text-body-md text-on-surface-variant">
                Reference resources are weighted towards some ancestries, so allele frequencies can be unrepresentative for others. This project reports South Asian (gnomAD) frequencies next to global ones; Indian-specific data (IndiGen) are not available to it.
              </p>
            </div>
            <div className="mt-space-lg pt-space-sm flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-error"></span> Global Reference Baseline Skew
            </div>
          </div>
        </div>

        {/* Transformation banner */}
        <div className="w-full bg-surface-container rounded-xl p-space-lg flex flex-col sm:flex-row items-center justify-between gap-space-md shadow-sm">
          <div className="flex items-center gap-space-md">
            <span className="material-symbols-outlined text-secondary text-[32px]">sync_alt</span>
            <div>
              <p className="font-title-md text-title-md text-primary font-semibold">The Cognitive Transformation</p>
              <p className="font-body-sm text-body-sm text-on-surface-variant">Converting chaotic diagnostic journeys into verifiable computational paths.</p>
            </div>
          </div>
          <div className="font-code-metric text-body-sm text-secondary bg-surface-container-lowest px-space-md py-space-xs rounded-lg shadow-sm font-semibold">
            Clinical Narrative ──→ Structured Biomedical Intelligence
          </div>
        </div>
      </div>
    </section>
  );
}
