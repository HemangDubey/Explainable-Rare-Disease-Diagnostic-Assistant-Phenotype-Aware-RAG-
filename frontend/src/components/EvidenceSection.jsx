import React from 'react';

export default function EvidenceSection() {
  return (
    <section className="w-full bg-surface-container-low py-space-3xl" id="evidence">
      <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop">
        <div className="max-w-2xl mb-space-2xl">
          <span className="font-label-sm text-label-sm text-secondary font-semibold uppercase tracking-wider block mb-space-2xs">
            Clinical Transparency
          </span>
          <h2 className="font-headline-lg text-headline-lg text-primary tracking-tight">
            Don't just show the result. Show the evidence behind it.
          </h2>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-space-xs">
            Interactive simulation of the clinical decision dashboard. Clinicians verify matching phenotypes, literature sources, and population adjustments directly.
          </p>
        </div>

        {/* Realistic Mock Diagnostic Insight Panel */}
        <div className="bg-surface-container-lowest rounded-2xl p-space-xl shadow-[0_8px_32px_rgba(9,30,58,0.06)]">
          {/* Top Metadata Ribbon */}
          <div className="flex flex-wrap items-center justify-between gap-space-sm pb-space-md mb-space-lg border-b-0 bg-surface-container-low p-space-sm rounded-lg">
            <div className="flex items-center gap-space-md">
              <span className="font-code-metric text-label-sm text-primary font-bold">CASE: #IND-2024-8891</span>
              <span className="w-1 h-1 rounded-full bg-outline-variant"></span>
              <span className="font-label-sm text-label-sm text-on-surface-variant">Cohort: Pediatric Neurogenetics</span>
              <span className="w-1 h-1 rounded-full bg-outline-variant"></span>
              <span className="font-label-sm text-label-sm text-secondary font-semibold">Population evidence: reported only (weight 0)</span>
            </div>
            <span className="px-space-xs py-space-3xs rounded-full bg-surface-container text-on-surface-variant font-code-metric text-label-sm">
              DEMO MODE — ILLUSTRATIVE ONLY
            </span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-xl">
            {/* Left: Detected Phenotypes (col-span-4) */}
            <div className="lg:col-span-4 flex flex-col">
              <span className="font-label-sm text-label-sm text-on-surface-variant uppercase font-semibold tracking-wider mb-space-sm flex items-center gap-space-2xs">
                <span className="material-symbols-outlined text-secondary text-[16px]">bubble_chart</span>
                Detected HPO Phenotypes (04)
              </span>
              <div className="flex flex-col gap-space-xs">
                {[
                  { name: 'Developmental Delay', hpo: 'HP:0001263', weight: '0.94' },
                  { name: 'Generalized Hypotonia', hpo: 'HP:0001252', weight: '0.89' },
                  { name: 'Short Stature', hpo: 'HP:0004322', weight: '0.72' },
                  { name: 'Refractory Seizures', hpo: 'HP:0001250', weight: '0.85' },
                ].map((p) => (
                  <div key={p.hpo} className="p-space-sm rounded-lg bg-surface-container flex items-center justify-between">
                    <div>
                      <span className="block font-title-md text-title-md text-primary">{p.name}</span>
                      <span className="font-code-metric text-label-sm text-secondary">{p.hpo}</span>
                    </div>
                    <span className="px-space-xs py-space-3xs rounded bg-surface-container-highest text-on-surface font-label-sm text-label-sm font-semibold">
                      Weight: {p.weight}
                    </span>
                  </div>
                ))}
              </div>
              <div className="mt-space-md p-space-sm rounded-lg bg-surface-container-low text-on-surface-variant font-body-sm text-body-sm">
                Extracted via Biomedical Transformer from unstructured neurological consult notes.
              </div>
            </div>

            {/* Middle: Candidate Disease & Match Meters (col-span-4) */}
            <div className="lg:col-span-4 flex flex-col justify-between">
              <div>
                <span className="font-label-sm text-label-sm text-on-surface-variant uppercase font-semibold tracking-wider mb-space-sm flex items-center gap-space-2xs">
                  <span className="material-symbols-outlined text-secondary text-[16px]">search_insights</span>
                  Prioritized Candidate Explanation
                </span>
                <div className="bg-surface-container p-space-md rounded-xl mb-space-md">
                  <div className="mb-space-xs inline-block px-space-xs py-0.5 rounded bg-tertiary-fixed text-on-tertiary-fixed font-label-sm font-bold">
                    ILLUSTRATIVE MOCK-UP — not a real patient, not a computed result; values are placeholders
                  </div>
                  <div className="flex items-start justify-between mb-space-2xs">
                    <h4 className="font-headline-sm text-headline-sm text-primary">Congenital Myasthenic Syndrome</h4>
                    <span className="px-space-xs py-space-3xs rounded-full bg-secondary-fixed/50 text-on-secondary-fixed font-code-metric text-label-sm">ORPHA:589</span>
                  </div>
                  <p className="font-body-sm text-body-sm text-on-surface-variant mb-space-md">
                    MIM #608930 • Mitochondrial &amp; Neuromuscular Junction Pathology
                  </p>
                  {/* Confidence Meters */}
                  <div className="flex flex-col gap-space-sm">
                    {[
                      { label: 'Phenotype Overlap (HPO)', value: 92, color: 'bg-secondary' },
                      { label: 'Biomedical Literature Support', value: 84, color: 'bg-primary' },
                      { label: 'Population evidence (gnomAD; IndiGen unavailable)', value: 71, color: 'bg-on-tertiary-container' },
                    ].map((m) => (
                      <div key={m.label}>
                        <div className="flex justify-between font-label-sm text-label-sm text-primary mb-space-3xs">
                          <span>{m.label}</span>
                          <span className="font-bold">example</span>
                        </div>
                        <div className="w-full h-2 rounded-full bg-surface-container-highest overflow-hidden">
                          <div className={`h-full ${m.color} rounded-full`} style={{ width: `${m.value}%` }}></div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              {/* Provenance tags */}
              <div className="flex flex-wrap gap-space-xs">
                <span className="px-space-xs py-space-3xs rounded-full bg-surface-container-high text-primary font-code-metric text-label-sm">PMID: (example)</span>
                <span className="px-space-xs py-space-3xs rounded-full bg-surface-container-high text-primary font-code-metric text-label-sm">gnomAD v4.1 (IndiGen unavailable)</span>
                <span className="px-space-xs py-space-3xs rounded-full bg-surface-container-high text-primary font-code-metric text-label-sm">Orphadata</span>
              </div>
            </div>

            {/* Right: Why this Candidate? Narrative Reasoning (col-span-4) */}
            <div className="lg:col-span-4 flex flex-col justify-between bg-surface-container-low p-space-md rounded-xl">
              <div>
                <span className="font-label-sm text-label-sm text-secondary uppercase font-semibold tracking-wider mb-space-sm flex items-center gap-space-2xs">
                  <span className="material-symbols-outlined text-[16px]">visibility</span>
                  Evidence-Linked Synthesis
                </span>
                <h4 className="font-title-md text-title-md text-primary mb-space-xs">Why this candidate?</h4>
                <p className="font-body-sm text-body-sm text-on-surface-variant mb-space-md leading-relaxed">
                  Illustrative text only. In the live workspace this panel shows an explanation generated from the case's own recorded evidence, each statement citing numbered evidence items, with unverified findings labelled as unverified.
                </p>
                <div className="p-space-sm bg-surface-container-lowest rounded-lg mb-space-sm">
                  <span className="font-label-sm text-label-sm text-primary font-semibold block mb-space-3xs">Tests and treatment:</span>
                  <span className="font-body-sm text-body-sm text-on-surface-variant">Not generated: the application does not recommend tests or treatment.</span>
                </div>
              </div>
              {/* Mandatory Research Disclaimer Box */}
              <div className="p-space-xs rounded bg-surface-container text-on-surface-variant font-label-sm text-label-sm flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-[16px] text-secondary">verified_user</span>
                <span>Illustrative interface demonstration — not a final clinical diagnosis.</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
