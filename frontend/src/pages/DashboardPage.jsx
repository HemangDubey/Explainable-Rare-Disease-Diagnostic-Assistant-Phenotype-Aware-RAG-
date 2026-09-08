import React, { useState, useEffect } from 'react';
import Navbar from '../components/Navbar';
import EvidenceCards from '../components/EvidenceCards';
import DifferentialExplorer from '../components/DifferentialExplorer';
import DoctorCopilot from '../components/DoctorCopilot';
import { diagnoseCase, explainCandidate, askDoctorCopilot, checkBackendHealth } from '../api/client';

const SAMPLE_CASES = [
  {
    title: "Neurodevelopmental & Seizures (IndiGen Focus)",
    text: "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."
  },
  {
    title: "Skeletal Dysplasia & Craniofacial Signs",
    text: "Patient presents with microcephaly, craniosynostosis, syndactyly, intellectual disability and cardiac murmur."
  },
  {
    title: "Metabolic & Muscular Weakness",
    text: "Infant presents with progressive muscle weakness, lactic acidosis, hepatomegaly, failure to thrive and cardiomyopathy."
  }
];

export default function DashboardPage() {
  const [inputText, setInputText] = useState(SAMPLE_CASES[0].text);
  const [activeTab, setActiveTab] = useState('evidence'); // 'evidence' | 'differential' | 'copilot'
  const [isLoading, setIsLoading] = useState(false);
  const [isExplaining, setIsExplaining] = useState(false);
  const [isCopilotLoading, setIsCopilotLoading] = useState(false);
  const [error, setError] = useState(null);
  const [caseData, setCaseData] = useState(null);
  const [explanations, setExplanations] = useState({});
  const [backendStatus, setBackendStatus] = useState(null);

  useEffect(() => {
    checkBackendHealth().then(setBackendStatus);
  }, []);

  const handleAnalyze = async (textToRun) => {
    const text = textToRun || inputText;
    if (!text.trim()) return;

    setIsLoading(true);
    setError(null);

    try {
      const data = await diagnoseCase({ text, top_k: 5 });
      setCaseData(data);
      if (data.top_explanation && data.fused_candidates?.[0]) {
        setExplanations({
          [data.fused_candidates[0].disease_id]: data.top_explanation
        });
      }
    } catch (err) {
      console.error('Diagnosis error:', err);
      setError(err.message || 'Error executing clinical pipeline');
    } finally {
      setIsLoading(false);
    }
  };

  const handleExplain = async (diseaseId) => {
    if (!caseData) return;
    setIsExplaining(true);
    try {
      const exp = await explainCandidate({
        case_id: caseData.case_id,
        disease_id: diseaseId,
        clinical_text: caseData.clinical_text
      });
      setExplanations(prev => ({ ...prev, [diseaseId]: exp }));
    } catch (err) {
      console.error('Explain error:', err);
      alert(`Could not synthesize explanation: ${err.message}`);
    } finally {
      setIsExplaining(false);
    }
  };

  const handleCopilotAsk = async (query) => {
    setIsCopilotLoading(true);
    try {
      const response = await askDoctorCopilot({
        query,
        case_id: caseData?.case_id,
        clinical_text: caseData?.clinical_text || inputText
      });
      return response;
    } finally {
      setIsCopilotLoading(false);
    }
  };

  return (
    <>
      <Navbar />
      <main className="w-full pt-20 bg-surface min-h-screen pb-space-3xl">
        <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop py-space-lg">
          
          {/* Top Clinical Header */}
          <div className="flex flex-wrap items-center justify-between gap-space-md mb-space-lg">
            <div>
              <div className="inline-flex items-center gap-space-xs px-space-xs py-0.5 rounded-full bg-secondary-fixed/40 text-on-secondary-fixed font-label-sm font-semibold mb-1">
                <span className="w-2 h-2 rounded-full bg-secondary animate-pulse"></span>
                <span>Explainable Clinical Decision Support</span>
              </div>
              <h1 className="font-headline-md text-primary font-bold">
                Rare-Disease Diagnostic Assistant Workspace
              </h1>
              <p className="font-body-md text-on-surface-variant">
                Phenotype-Aware RAG with Indian Ancestral Population Priors & Ollama LLM Reasoning
              </p>
            </div>

            {/* Backend Connection Status */}
            <div className="flex items-center gap-space-xs px-space-md py-space-xs rounded-xl bg-surface-container-lowest border border-outline-variant/30 text-body-sm shadow-sm">
              <span className={`w-2.5 h-2.5 rounded-full ${backendStatus?.status === 'healthy' ? 'bg-primary' : 'bg-tertiary'}`}></span>
              <span className="font-medium text-on-surface">
                {backendStatus?.status === 'healthy' ? 'Pipeline Active (Ollama local)' : 'Backend Initializing...'}
              </span>
            </div>
          </div>

          {/* Clinical Observation Input Box */}
          <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30 mb-space-xl">
            <div className="flex items-center justify-between mb-space-xs">
              <label className="font-title-sm text-primary font-bold flex items-center gap-space-2xs">
                <span className="material-symbols-outlined text-secondary text-[20px]">clinical_notes</span>
                Patient Clinical Presentation & Physical Exam Findings:
              </label>
              <div className="flex items-center gap-space-2xs">
                <span className="text-[11px] text-on-surface-variant font-medium">Load sample:</span>
                {SAMPLE_CASES.map((sc, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setInputText(sc.text);
                      handleAnalyze(sc.text);
                    }}
                    className="text-[11px] px-space-xs py-0.5 rounded bg-surface-container hover:bg-secondary-fixed/30 hover:text-on-secondary-fixed text-on-surface font-semibold transition-colors"
                  >
                    Case #{idx + 1}
                  </button>
                ))}
              </div>
            </div>

            <textarea
              rows={3}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="Enter unstructured patient signs, symptoms, physical exam findings, or genetic observations..."
              className="w-full p-space-md rounded-xl bg-surface border border-outline-variant text-body-md text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary leading-relaxed"
            />

            <div className="flex flex-wrap items-center justify-between gap-space-sm mt-space-sm pt-space-xs border-t border-outline-variant/20">
              <div className="flex items-center gap-space-xs text-label-sm text-on-surface-variant">
                <span className="material-symbols-outlined text-[16px] text-secondary">memory</span>
                <span>End-to-End: BiomedBERT NER → HPO → FAISS → IndiGen Priors → Evidence Fusion → Ollama</span>
              </div>

              <button
                onClick={() => handleAnalyze()}
                disabled={isLoading || !inputText.trim()}
                className="inline-flex items-center gap-space-xs px-space-lg py-space-sm rounded-xl bg-primary text-on-primary font-label-lg font-bold hover:bg-primary/90 transition-all shadow-md disabled:opacity-50"
              >
                <span className="material-symbols-outlined text-[20px]">
                  {isLoading ? 'progress_activity' : 'psychology_alt'}
                </span>
                <span>{isLoading ? 'Processing Pipeline...' : 'Run Diagnostic Prioritization'}</span>
              </button>
            </div>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="p-space-md rounded-xl bg-error-container text-on-error-container mb-space-lg flex items-center gap-space-sm">
              <span className="material-symbols-outlined text-[24px]">error</span>
              <p className="font-body-md font-medium">{error}</p>
            </div>
          )}

          {/* Extracted Phenotypes Strip */}
          {caseData?.extracted_phenotypes && caseData.extracted_phenotypes.length > 0 && (
            <div className="mb-space-lg p-space-md rounded-2xl bg-surface-container-low border border-outline-variant/30">
              <span className="font-label-sm font-bold text-primary block mb-space-2xs uppercase tracking-wider">
                Phase 1 BiomedBERT Extracted Phenotypes & HPO Terms:
              </span>
              <div className="flex flex-wrap gap-space-xs">
                {caseData.extracted_phenotypes.map((item, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-1 px-space-sm py-1 rounded-full bg-surface-container-lowest text-on-surface text-body-sm shadow-sm border border-outline-variant/30"
                  >
                    <span className="material-symbols-outlined text-secondary text-[16px]">label</span>
                    <strong className="text-primary">{item.phenotype}</strong>
                    {caseData.hpo_terms?.[idx]?.hpo_id && (
                      <span className="font-code-metric text-[11px] px-1.5 py-0.5 rounded bg-secondary-fixed/40 text-on-secondary-fixed">
                        {caseData.hpo_terms[idx].hpo_id}
                      </span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Tab Navigation */}
          <div className="flex items-center gap-space-xs border-b border-outline-variant/30 mb-space-lg">
            <button
              onClick={() => setActiveTab('evidence')}
              className={`flex items-center gap-space-xs px-space-lg py-space-sm border-b-2 font-title-sm transition-all ${
                activeTab === 'evidence'
                  ? 'border-primary text-primary font-bold'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">fact_check</span>
              <span>Prioritized Candidates & Evidence Fusion</span>
              {caseData?.fused_candidates && (
                <span className="w-5 h-5 rounded-full bg-primary-fixed text-on-primary-fixed text-[11px] flex items-center justify-center font-bold">
                  {caseData.fused_candidates.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab('differential')}
              className={`flex items-center gap-space-xs px-space-lg py-space-sm border-b-2 font-title-sm transition-all ${
                activeTab === 'differential'
                  ? 'border-primary text-primary font-bold'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">balance</span>
              <span>Differential Diagnosis Explorer</span>
            </button>

            <button
              onClick={() => setActiveTab('copilot')}
              className={`flex items-center gap-space-xs px-space-lg py-space-sm border-b-2 font-title-sm transition-all ${
                activeTab === 'copilot'
                  ? 'border-primary text-primary font-bold'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">smart_toy</span>
              <span>Explainable AI Doctor Copilot</span>
            </button>
          </div>

          {/* Tab Content */}
          {activeTab === 'evidence' && (
            <div className="flex flex-col gap-space-md">
              {caseData?.fused_candidates && caseData.fused_candidates.length > 0 ? (
                caseData.fused_candidates.map((cand) => (
                  <EvidenceCards
                    key={cand.disease_id}
                    candidate={cand}
                    onExplain={handleExplain}
                    isExplaining={isExplaining}
                    explanation={explanations[cand.disease_id]}
                  />
                ))
              ) : (
                <div className="p-space-3xl text-center text-on-surface-variant bg-surface-container-lowest rounded-2xl border border-outline-variant/30">
                  <span className="material-symbols-outlined text-[56px] text-secondary mb-space-xs">clinical_notes</span>
                  <h3 className="font-title-lg text-primary font-bold">No Case Analyzed Yet</h3>
                  <p className="font-body-md text-on-surface-variant mt-1 max-w-md mx-auto">
                    Click "Run Diagnostic Prioritization" above or choose a sample case to extract phenotypes, query knowledge bases, and calibrate Indian population priors.
                  </p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'differential' && (
            <DifferentialExplorer
              differential={caseData?.differential}
              onSelectCandidate={(cand) => handleExplain(cand.disease_id)}
            />
          )}

          {activeTab === 'copilot' && (
            <DoctorCopilot
              onAsk={handleCopilotAsk}
              isLoading={isCopilotLoading}
              currentCase={caseData}
            />
          )}

        </div>
      </main>
    </>
  );
}
