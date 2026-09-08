import React, { useState } from 'react';
import { runScribe } from '../api/client';

const SAMPLE_CLINICAL_NOTE = "Patient is a 7-year-old child with developmental delay since infancy, hypotonia, short stature and recurrent seizures. No known family history.";

export default function ClinicalScribeView({ onSendToDiagnosis }) {
  const [inputText, setInputText] = useState(SAMPLE_CLINICAL_NOTE);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [scribeResult, setScribeResult] = useState(null);

  const handleAnalyze = async () => {
    if (!inputText.trim()) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await runScribe({ clinical_text: inputText });
      setScribeResult(data);
    } catch (err) {
      console.error('Scribe error:', err);
      setError(err.message || 'Failed to execute Clinical Scribe extraction');
    } finally {
      setIsLoading(false);
    }
  };

  const handleContinue = () => {
    if (!scribeResult) return;
    if (onSendToDiagnosis) {
      onSendToDiagnosis(inputText, scribeResult.case_id);
    }
  };

  const sc = scribeResult?.structured_case;

  return (
    <div className="flex flex-col gap-space-xl">
      {/* Input Card */}
      <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30">
        <div className="flex items-center justify-between mb-space-xs">
          <label className="font-title-sm text-primary font-bold flex items-center gap-space-2xs">
            <span className="material-symbols-outlined text-secondary text-[20px]">edit_note</span>
            Unstructured Clinical Narrative:
          </label>
          <button
            onClick={() => setInputText(SAMPLE_CLINICAL_NOTE)}
            className="text-[12px] px-space-xs py-0.5 rounded bg-surface-container hover:bg-surface-container-high text-primary font-semibold transition-colors"
          >
            Load Sample Narrative
          </button>
        </div>

        <textarea
          rows={4}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Enter clinical observations, signs, symptoms, family history, developmental history..."
          className="w-full p-space-md rounded-xl bg-surface border border-outline-variant text-body-md text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary leading-relaxed"
        />

        <div className="flex items-center justify-between mt-space-md pt-space-xs border-t border-outline-variant/20">
          <span className="text-label-sm text-on-surface-variant">
            Reuses Phase 1 BiomedBERT NER & HPO Normalizer
          </span>

          <button
            onClick={handleAnalyze}
            disabled={isLoading || !inputText.trim()}
            className="inline-flex items-center gap-space-xs px-space-lg py-space-sm rounded-xl bg-primary text-on-primary font-label-lg font-bold hover:bg-primary/90 transition-all shadow-md disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[20px]">
              {isLoading ? 'progress_activity' : 'fact_check'}
            </span>
            <span>{isLoading ? 'Structuring Case...' : 'Analyze Case'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-space-md rounded-xl bg-error-container text-on-error-container font-label-md">
          {error}
        </div>
      )}

      {/* Structured Results Section */}
      {scribeResult && sc && (
        <div className="flex flex-col gap-space-xl">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
            {/* Left Column: Key Case Elements */}
            <div className="lg:col-span-8 bg-surface-container-lowest rounded-2xl p-space-xl shadow-sm border border-outline-variant/30 flex flex-col gap-space-lg">
              <div className="flex items-center justify-between pb-space-xs border-b border-outline-variant/20">
                <h3 className="font-title-lg text-primary font-bold flex items-center gap-space-2xs">
                  <span className="material-symbols-outlined text-secondary text-[22px]">assignment</span>
                  Structured Case Output
                </h3>
                <span className="font-code-metric text-label-sm px-space-xs py-0.5 rounded bg-surface-container text-secondary font-bold">
                  CASE ID: #{scribeResult.case_id}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
                <div className="p-space-md rounded-xl bg-surface-container-low border border-outline-variant/20">
                  <span className="font-bold text-primary block mb-1">Chief Complaint:</span>
                  <p className="text-on-surface">{sc.chief_complaint || 'Not specified'}</p>
                </div>
                <div className="p-space-md rounded-xl bg-surface-container-low border border-outline-variant/20">
                  <span className="font-bold text-primary block mb-1">Patient Demographics:</span>
                  <p className="text-on-surface">{sc.age ? `Age: ${sc.age}` : 'Age unspecified'}</p>
                </div>
                <div className="p-space-md rounded-xl bg-surface-container-low border border-outline-variant/20">
                  <span className="font-bold text-primary block mb-1">Developmental History:</span>
                  <p className="text-on-surface">{sc.developmental_history || 'Not specified'}</p>
                </div>
                <div className="p-space-md rounded-xl bg-surface-container-low border border-outline-variant/20">
                  <span className="font-bold text-primary block mb-1">Family History:</span>
                  <p className="text-on-surface">{sc.family_history || 'Not specified'}</p>
                </div>
              </div>

              {/* Relevant Negatives */}
              <div>
                <h4 className="font-label-md text-primary font-bold mb-space-2xs flex items-center gap-space-3xs">
                  <span className="material-symbols-outlined text-[16px] text-secondary">do_not_disturb_on</span>
                  Relevant Negatives (Negated Phenotypes)
                </h4>
                {sc.relevant_negatives.length > 0 ? (
                  <div className="flex flex-wrap gap-space-xs">
                    {sc.relevant_negatives.map((neg, idx) => (
                      <span key={idx} className="px-space-xs py-space-3xs rounded-md bg-surface-container text-on-surface-variant font-code-metric text-label-sm italic border border-outline-variant/30">
                        "{neg}"
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-body-sm text-on-surface-variant">No explicit negated phenotypes recorded.</p>
                )}
              </div>

              {/* Extracted HPO Terms */}
              <div>
                <h4 className="font-label-md text-primary font-bold mb-space-2xs flex items-center gap-space-3xs">
                  <span className="material-symbols-outlined text-[16px] text-secondary">schema</span>
                  Normalized HPO Terms ({scribeResult.hpo_terms.length})
                </h4>
                <div className="flex flex-wrap gap-space-xs">
                  {scribeResult.hpo_terms.map((hp) => (
                    <span key={hp.hpo_id} className="inline-flex items-center gap-space-3xs px-space-sm py-space-xs rounded-lg bg-secondary-fixed/50 text-on-secondary-fixed font-code-metric text-label-sm font-bold shadow-sm">
                      <span>{hp.hpo_id}</span>
                      <span className="font-medium text-on-surface">({hp.name})</span>
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Right Column: Missing Information & Action */}
            <div className="lg:col-span-4 flex flex-col gap-space-lg">
              <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30">
                <h4 className="font-label-md text-primary font-bold mb-space-xs flex items-center gap-space-3xs">
                  <span className="material-symbols-outlined text-[18px] text-tertiary">warning</span>
                  Unstated / Missing Information
                </h4>
                <p className="text-body-sm text-on-surface-variant mb-space-sm">
                  The following fields were not stated in the narrative and remain unpopulated (no assumptions made):
                </p>
                <ul className="list-disc list-inside text-body-sm text-on-surface-variant space-y-1">
                  {scribeResult.missing_information.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className="bg-primary text-on-primary rounded-2xl p-space-lg shadow-md flex flex-col justify-between">
                <div>
                  <h4 className="font-title-md font-bold mb-space-2xs text-on-primary">
                    Ready for Diagnostic Analysis?
                  </h4>
                  <p className="font-body-sm text-slate-300 mb-space-md">
                    Pass this structured clinical case into the Phase 1–4 Diagnostic Prioritization Pipeline.
                  </p>
                </div>

                <button
                  onClick={handleContinue}
                  className="w-full py-space-sm px-space-md rounded-xl bg-secondary hover:bg-secondary/90 text-on-secondary font-label-lg font-bold transition-all shadow-md flex items-center justify-center gap-space-xs"
                >
                  <span>Continue to Diagnostic Analysis</span>
                  <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
