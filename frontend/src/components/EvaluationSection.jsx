import React from 'react';

export default function EvaluationSection() {
  return (
    <section className="w-full py-space-3xl">
      <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop">
        <div className="max-w-2xl mb-space-2xl">
          <span className="font-label-sm text-label-sm text-secondary font-semibold uppercase tracking-wider block mb-space-2xs">
            System Validation
          </span>
          <h2 className="font-headline-lg text-headline-lg text-primary tracking-tight">
            Measure every layer of the pipeline.
          </h2>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-space-xs">
            Modular evaluation metrics across Named Entity Recognition (NER), vector retrieval precision, and downstream clinical candidate ranking.
          </p>
        </div>

        {/* Evaluation Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-space-lg mb-space-xl">
          {/* NER Performance */}
          <div className="bg-surface-container-lowest p-space-xl rounded-xl shadow-sm">
            <div className="flex items-center justify-between mb-space-md">
              <h3 className="font-title-md text-title-md text-primary">NER Extraction (HPO)</h3>
              <span className="material-symbols-outlined text-secondary text-[20px]">token</span>
            </div>
            <div className="grid grid-cols-3 gap-space-xs text-center mb-space-lg">
              <div className="p-space-xs bg-surface-container-low rounded-lg">
                <span className="block font-headline-sm text-headline-sm text-primary font-bold">0.719</span>
                <span className="font-label-sm text-label-sm text-on-surface-variant">Precision</span>
              </div>
              <div className="p-space-xs bg-surface-container-low rounded-lg">
                <span className="block font-headline-sm text-headline-sm text-primary font-bold">0.721</span>
                <span className="font-label-sm text-label-sm text-on-surface-variant">Recall</span>
              </div>
              <div className="p-space-xs bg-surface-container-low rounded-lg">
                <span className="block font-headline-sm text-headline-sm text-secondary font-bold">0.720</span>
                <span className="font-label-sm text-label-sm text-on-surface-variant">F1 Score</span>
              </div>
            </div>
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              BiomedBERT, held-out test split (227 observations) of the BioCreative VIII Track 3 physical-exam corpus.
            </p>
          </div>

          {/* Retrieval Performance */}
          <div className="bg-surface-container-lowest p-space-xl rounded-xl shadow-sm">
            <div className="flex items-center justify-between mb-space-md">
              <h3 className="font-title-md text-title-md text-primary">Retrieval Accuracy</h3>
              <span className="material-symbols-outlined text-secondary text-[20px]">search_check</span>
            </div>
            <div className="grid grid-cols-3 gap-space-xs text-center mb-space-lg">
              <div className="p-space-xs bg-surface-container-low rounded-lg">
                <span className="block font-headline-sm text-headline-sm text-primary font-bold">0.942</span>
                <span className="font-label-sm text-label-sm text-on-surface-variant">Recall@5</span>
              </div>
              <div className="p-space-xs bg-surface-container-low rounded-lg">
                <span className="block font-headline-sm text-headline-sm text-primary font-bold">0.980</span>
                <span className="font-label-sm text-label-sm text-on-surface-variant">Recall@10</span>
              </div>
              <div className="p-space-xs bg-surface-container-low rounded-lg">
                <span className="block font-headline-sm text-headline-sm text-secondary font-bold">0.868</span>
                <span className="font-label-sm text-label-sm text-on-surface-variant">MRR</span>
              </div>
            </div>
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              S-PubMedBERT HPO-level retrieval over 12,880 HPO-annotated diseases. Simulated patients (4 phenotypes sampled from a disease's own annotations, 500 queries), not real patients.
            </p>
          </div>

          {/* Ranking Comparison Analysis */}
          <div className="bg-surface-container-lowest p-space-xl rounded-xl shadow-sm">
            <div className="flex items-center justify-between mb-space-md">
              <h3 className="font-title-md text-title-md text-primary">Population-Aware Ranking</h3>
              <span className="material-symbols-outlined text-secondary text-[20px]">insights</span>
            </div>
            <div className="mb-space-md p-space-sm bg-surface-container-low rounded-lg text-center">
              <span className="font-code-metric text-on-surface-variant">Pending evaluation</span>
            </div>
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              Not evaluated. The population weight is 0, so population evidence does not alter the ranking, and no improvement from population evidence is claimed. IndiGen is unavailable.
            </p>
          </div>
        </div>

        <div className="w-full text-center">
          <span className="font-label-sm text-label-sm text-on-surface-variant bg-surface-container-low px-space-md py-space-xs rounded-full">
            Measured on a research prototype. Not clinical validation.
          </span>
        </div>
      </div>
    </section>
  );
}
