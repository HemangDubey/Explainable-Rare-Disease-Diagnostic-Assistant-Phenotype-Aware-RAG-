import React, { useState, useEffect } from 'react';
import { validateClinicalInput, enhanceClinicalText } from '../api/client';

export default function ClinicalInputSection({
  inputText,
  setInputText,
  onRunDiagnosis,
  isLoading,
  sampleCases = []
}) {
  const [validation, setValidation] = useState(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isEnhancing, setIsEnhancing] = useState(false);
  const [enhancementResult, setEnhancementResult] = useState(null);
  const [editableEnhancedText, setEditableEnhancedText] = useState('');
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [validationError, setValidationError] = useState(null);

  // Debounced input validation
  useEffect(() => {
    if (!inputText || !inputText.trim()) {
      setValidation(null);
      setValidationError(null);
      return;
    }

    const timer = setTimeout(async () => {
      setIsValidating(true);
      try {
        const res = await validateClinicalInput({ text: inputText });
        setValidation(res);
        setValidationError(null);
      } catch (err) {
        console.error('Validation error:', err);
      } finally {
        setIsValidating(false);
      }
    }, 400);

    return () => clearTimeout(timer);
  }, [inputText]);

  const handleEnhance = async () => {
    if (!inputText.trim()) return;
    setIsEnhancing(true);
    setValidationError(null);
    try {
      // Step 1: Validate input first
      const val = await validateClinicalInput({ text: inputText });
      setValidation(val);

      if (!val.is_valid_clinical) {
        // DO NOT OPEN ENHANCEMENT REVIEW MODAL FOR NON-CLINICAL / INAPPROPRIATE INPUT!
        if (val.status === 'INAPPROPRIATE') {
          setValidationError("Please enter relevant clinical information to continue.");
        } else {
          setValidationError("Clinical information required. Please enter symptoms, physical examination findings, developmental observations, medical history, or relevant genetic observations.");
        }
        return;
      }

      // Step 2: Call backend enhancement endpoint
      const res = await enhanceClinicalText({ text: inputText });
      
      if (res.status === 'NON_CLINICAL' || res.status === 'INAPPROPRIATE' || res.status === 'INSUFFICIENT') {
        // Do NOT open modal
        setValidationError(res.reason || "Clinical information required.");
        return;
      }

      if (res.status === 'ENHANCEMENT_UNAVAILABLE') {
        setValidationError("AI enhancement is temporarily unavailable. You can continue with the original clinical text.");
        return;
      }

      setEnhancementResult(res);
      setEditableEnhancedText(res.enhanced_text || inputText);
      setShowReviewModal(true);
    } catch (err) {
      console.error('Enhancement error:', err);
      setValidationError('AI enhancement is temporarily unavailable. You can continue with the original clinical text.');
    } finally {
      setIsEnhancing(false);
    }
  };

  const handleApplyEnhanced = () => {
    setInputText(editableEnhancedText);
    setShowReviewModal(false);
    setEnhancementResult(null);
  };

  const handleKeepOriginal = () => {
    setShowReviewModal(false);
    setEnhancementResult(null);
  };

  const handleRunSubmit = () => {
    setValidationError(null);
    if (!inputText.trim()) {
      setValidationError('Clinical input area is empty. Please enter clinical observations.');
      return;
    }

    if (validation && !validation.is_valid_clinical) {
      if (validation.status === 'INAPPROPRIATE') {
        setValidationError("Please enter relevant clinical information to continue.");
      } else {
        setValidationError("Clinical information required. Please enter symptoms, physical examination findings, developmental observations, medical history, or relevant genetic observations.");
      }
      return;
    }

    onRunDiagnosis(inputText);
  };

  return (
    <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30 mb-space-md">
      {/* Title & Sample Selection */}
      <div className="flex flex-wrap items-center justify-between gap-space-xs mb-space-xs">
        <label className="font-title-sm text-primary font-bold flex items-center gap-space-2xs">
          <span className="material-symbols-outlined text-secondary text-[20px]">clinical_notes</span>
          Patient Clinical Presentation & Physical Exam Findings:
        </label>
        {sampleCases.length > 0 && (
          <div className="flex items-center gap-space-2xs">
            <span className="text-[11px] text-on-surface-variant font-medium">Load sample:</span>
            {sampleCases.map((sc, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setInputText(sc.text);
                  setValidationError(null);
                  onRunDiagnosis(sc.text);
                }}
                className="text-[11px] px-space-xs py-0.5 rounded bg-surface-container hover:bg-secondary-fixed/30 hover:text-on-secondary-fixed text-on-surface font-semibold transition-colors"
              >
                Case #{idx + 1}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Main Textarea */}
      <div className="relative">
        <textarea
          rows={4}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Enter unstructured patient signs, symptoms, physical exam findings, or genetic observations..."
          className="w-full p-space-md pb-12 rounded-xl bg-surface border border-outline-variant text-body-md text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary leading-relaxed"
        />

        {/* Secondary Action: ✨ Enhance with AI */}
        <div className="absolute bottom-3 right-3 flex items-center gap-space-xs">
          {validation && (
            <span className={`text-[11px] px-space-xs py-0.5 rounded-full font-bold flex items-center gap-1 ${
              validation.status === 'VALID_CLINICAL'
                ? 'bg-accent-sage/20 text-accent-sage'
                : validation.status === 'NEEDS_ENHANCEMENT'
                ? 'bg-secondary-fixed/50 text-on-secondary-fixed'
                : validation.status === 'INAPPROPRIATE'
                ? 'bg-error-container text-on-error-container'
                : 'bg-surface-container text-on-surface-variant'
            }`}>
              <span className="material-symbols-outlined text-[13px]">
                {validation.status === 'VALID_CLINICAL' ? 'check_circle' : validation.status === 'NEEDS_ENHANCEMENT' ? 'auto_awesome' : 'info'}
              </span>
              <span>{validation.status.replace('_', ' ')}</span>
            </span>
          )}

          <button
            type="button"
            onClick={handleEnhance}
            disabled={isEnhancing || !inputText.trim()}
            className="inline-flex items-center gap-1 px-space-sm py-1 rounded-lg bg-surface-container-high hover:bg-secondary-fixed/40 text-primary font-label-sm font-semibold transition-all border border-outline-variant/40 shadow-xs disabled:opacity-40"
            title="Refine clinical grammar and expand abbreviations without altering medical facts"
          >
            <span className="material-symbols-outlined text-[16px] text-secondary">
              {isEnhancing ? 'progress_activity' : 'auto_awesome'}
            </span>
            <span>{isEnhancing ? 'Enhancing...' : 'Enhance with AI'}</span>
          </button>
        </div>
      </div>

      {/* Inline Quality / Validation Warning Banner */}
      {validationError && (
        <div className="mt-space-xs p-space-sm rounded-xl bg-error-container/80 text-on-error-container font-label-md flex items-center gap-space-xs border border-error/30">
          <span className="material-symbols-outlined text-[20px] shrink-0">warning</span>
          <div>
            <strong className="block font-bold">Clinical Information Required</strong>
            <span>{validationError}</span>
          </div>
        </div>
      )}

      {/* Bottom Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-space-sm mt-space-sm pt-space-xs border-t border-outline-variant/20">
        <div className="flex items-center gap-space-xs text-label-sm text-on-surface-variant">
          <span className="material-symbols-outlined text-[16px] text-secondary">memory</span>
          <span>End-to-End: BiomedBERT NER → HPO → FAISS → IndiGen Priors → Evidence Fusion → Explainable AI</span>
        </div>

        <button
          onClick={handleRunSubmit}
          disabled={isLoading || !inputText.trim()}
          className="inline-flex items-center gap-space-xs px-space-lg py-space-sm rounded-xl bg-primary text-on-primary font-label-lg font-bold hover:bg-primary/90 transition-all shadow-md disabled:opacity-50"
        >
          <span className="material-symbols-outlined text-[20px]">
            {isLoading ? 'progress_activity' : 'psychology_alt'}
          </span>
          <span>{isLoading ? 'Processing Pipeline...' : 'Run Diagnostic Prioritization'}</span>
        </button>
      </div>

      {/* AI Enhancement Review Modal (Shown ONLY for Valid Clinical Text Enhancement) */}
      {showReviewModal && enhancementResult && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-space-md">
          <div className="bg-surface-container-lowest rounded-2xl max-w-2xl w-full p-space-xl shadow-2xl border border-outline-variant/40 animate-fade-in flex flex-col gap-space-md">
            
            {/* Modal Header */}
            <div className="flex items-center justify-between pb-space-xs border-b border-outline-variant/20">
              <h3 className="font-title-lg text-primary font-bold flex items-center gap-space-2xs">
                <span className="material-symbols-outlined text-secondary text-[22px]">auto_awesome</span>
                AI-Enhanced Clinical Input Review
              </h3>
              <button
                onClick={handleKeepOriginal}
                className="text-on-surface-variant hover:text-on-surface p-1 rounded-full hover:bg-surface-container"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>

            <p className="text-body-sm text-on-surface-variant">
              Review and edit the AI-refined clinical text below before applying it to your case diagnosis. Original medical facts have been preserved.
            </p>

            {/* Comparison Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
              {/* Original Text */}
              <div className="p-space-md rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col">
                <span className="font-label-sm font-bold text-primary mb-1 uppercase tracking-wider">
                  Original Input:
                </span>
                <p className="text-body-sm text-on-surface-variant leading-relaxed italic whitespace-pre-wrap">
                  "{enhancementResult.original_text}"
                </p>
              </div>

              {/* Enhanced Text (Editable) */}
              <div className="p-space-md rounded-xl bg-surface border border-secondary/40 shadow-xs flex flex-col">
                <span className="font-label-sm font-bold text-secondary mb-1 uppercase tracking-wider flex items-center gap-1">
                  <span className="material-symbols-outlined text-[14px]">edit</span>
                  AI-Enhanced Text (Editable):
                </span>
                <textarea
                  rows={4}
                  value={editableEnhancedText}
                  onChange={(e) => setEditableEnhancedText(e.target.value)}
                  className="w-full p-space-xs rounded-lg bg-surface border border-outline-variant text-body-sm text-on-surface focus:outline-none focus:ring-1 focus:ring-secondary leading-relaxed"
                />
              </div>
            </div>

            {/* Applied Normalization Changes */}
            {(() => {
              const displayChanges = (enhancementResult.changes || [])
                .filter(ch => ch && ch.trim().toLowerCase() !== 'none');

              return (
                <div className="p-space-sm rounded-xl bg-surface-container-low border border-outline-variant/20">
                  <span className="font-label-xs font-bold text-primary uppercase block mb-1">
                    Applied Refinements:
                  </span>
                  {displayChanges.length > 0 ? (
                    <ul className="list-disc list-inside text-body-xs text-on-surface-variant space-y-0.5">
                      {displayChanges.map((ch, idx) => (
                        <li key={idx}>{ch}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-body-xs text-on-surface-variant italic">No changes were necessary.</p>
                  )}
                </div>
              );
            })()}

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-space-sm pt-space-xs border-t border-outline-variant/20">
              <button
                onClick={handleKeepOriginal}
                className="px-space-md py-space-xs rounded-xl bg-surface-container hover:bg-surface-container-high text-on-surface font-label-md font-semibold transition-colors"
              >
                Keep Original Text
              </button>
              <button
                onClick={handleApplyEnhanced}
                className="px-space-lg py-space-xs rounded-xl bg-secondary text-on-secondary font-label-md font-bold hover:bg-secondary/90 transition-all shadow-md flex items-center gap-space-2xs"
              >
                <span className="material-symbols-outlined text-[18px]">check</span>
                <span>Use Enhanced Text</span>
              </button>
            </div>

          </div>
        </div>
      )}
    </div>
  );

}
