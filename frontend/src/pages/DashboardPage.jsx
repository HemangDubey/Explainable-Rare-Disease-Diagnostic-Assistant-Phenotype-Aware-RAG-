import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import EvidenceCards from '../components/EvidenceCards';
import DifferentialExplorer from '../components/DifferentialExplorer';
import DoctorCopilot from '../components/DoctorCopilot';
import ClinicalScribeView from '../components/ClinicalScribeView';
import CounterfactualView from '../components/CounterfactualView';
import ClinicalInputSection from '../components/ClinicalInputSection';
import EvidenceExplorerView from '../components/EvidenceExplorerView';
import ReportGeneratorView from '../components/ReportGeneratorView';
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

export default function DashboardPage({ defaultTab = 'evidence' }) {
  const location = useLocation();
  const initialTab = location.state?.initialTab || defaultTab;

  const [inputText, setInputText] = useState(location.state?.clinical_text || SAMPLE_CASES[0].text);
  const [activeTab, setActiveTab] = useState(initialTab); // 'scribe' | 'evidence' | 'differential' | 'copilot' | 'counterfactual'
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

  const handleScribeToDiagnosis = (textFromScribe, caseIdFromScribe) => {
    setInputText(textFromScribe);
    setActiveTab('evidence');
    handleAnalyze(textFromScribe);
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
      const res = await askDoctorCopilot({
        query,
        case_id: caseData?.case_id,
        clinical_text: caseData?.clinical_text || inputText
      });
      return res;
    } catch (err) {
      console.error('Copilot error:', err);
      throw err;
    } finally {
      setIsCopilotLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-surface font-body-md text-on-surface">
      <Navbar />

      <main className="flex-1 max-w-container-max w-full mx-auto px-gutter-mobile lg:px-gutter-desktop pt-28 pb-space-3xl">
        <div className="flex flex-col gap-space-xl">
          
          {/* Top Clinical Header */}
          <div className="flex flex-wrap items-center justify-between gap-space-md mb-space-sm">
            <div>
              <div className="inline-flex items-center gap-space-xs px-space-xs py-0.5 rounded-full bg-secondary-fixed/40 text-on-secondary-fixed font-label-sm font-semibold mb-1">
                <span className="w-2 h-2 rounded-full bg-secondary animate-pulse"></span>
                <span>Unified Clinical Decision Support System (Phases 1–5)</span>
              </div>
              <h1 className="font-headline-md text-primary font-bold">
                Rare-Disease Diagnostic Assistant Workspace
              </h1>
              <p className="font-body-md text-on-surface-variant">
                Phenotype-Aware RAG with Indian Ancestral Population Priors & Explainable AI Reasoning
              </p>
            </div>

            {/* System Readiness Status Indicator */}
            <div className="flex items-center gap-space-xs px-space-md py-space-xs rounded-xl bg-surface-container-lowest border border-outline-variant/30 text-body-sm shadow-sm">
              <span className={`w-2.5 h-2.5 rounded-full ${backendStatus?.status === 'healthy' ? 'bg-primary' : 'bg-tertiary'}`}></span>
              <span className="font-medium text-on-surface">
                {backendStatus?.status === 'healthy' ? 'AI Reasoning Engine Ready' : 'Backend Initializing...'}
              </span>
            </div>
          </div>

          {/* Clinical Observation Input Box (Visible in Diagnosis, Differential, Copilot tabs) */}
          {(activeTab === 'evidence' || activeTab === 'differential' || activeTab === 'copilot') && (
            <ClinicalInputSection
              inputText={inputText}
              setInputText={setInputText}
              onRunDiagnosis={(textToRun) => handleAnalyze(textToRun)}
              isLoading={isLoading}
              sampleCases={SAMPLE_CASES}
            />
          )}

          {/* Error Banner */}
          {error && (
            <div className="p-space-md rounded-xl bg-error-container text-on-error-container mb-space-lg flex items-center gap-space-sm">
              <span className="material-symbols-outlined text-[24px]">error</span>
              <p className="font-body-md font-medium">{error}</p>
            </div>
          )}

          {/* Extracted Phenotypes Strip */}
          {caseData?.extracted_phenotypes && caseData.extracted_phenotypes.length > 0 && (
            <div className="p-space-md rounded-2xl bg-surface-container-low border border-outline-variant/30 mb-space-sm">
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

          {/* Unified Central Tab Navigation */}
          <div className="flex items-center gap-space-xs border-b border-outline-variant/30 mb-space-lg overflow-x-auto">
            <button
              onClick={() => setActiveTab('scribe')}
              className={`flex items-center gap-space-xs px-space-md py-space-sm border-b-2 font-title-sm transition-all whitespace-nowrap ${
                activeTab === 'scribe'
                  ? 'border-primary text-primary font-bold'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">edit_note</span>
              <span>AI Clinical Scribe</span>
            </button>

            <button
              onClick={() => setActiveTab('evidence')}
              className={`flex items-center gap-space-xs px-space-md py-space-sm border-b-2 font-title-sm transition-all whitespace-nowrap ${
                activeTab === 'evidence'
                  ? 'border-primary text-primary font-bold'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">fact_check</span>
              <span>Prioritized Candidates & Evidence</span>
              {caseData?.fused_candidates && (
                <span className="w-5 h-5 rounded-full bg-primary-fixed text-on-primary-fixed text-[11px] flex items-center justify-center font-bold">
                  {caseData.fused_candidates.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab('differential')}
              className={`flex items-center gap-space-xs px-space-md py-space-sm border-b-2 font-title-sm transition-all whitespace-nowrap ${
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
              className={`flex items-center gap-space-xs px-space-md py-space-sm border-b-2 font-title-sm transition-all whitespace-nowrap ${
                activeTab === 'copilot'
                  ? 'border-primary text-primary font-bold'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">smart_toy</span>
              <span>Explainable AI Doctor Copilot</span>
            </button>

            <button
              onClick={() => setActiveTab('counterfactual')}
              className={`flex items-center gap-space-xs px-space-md py-space-sm border-b-2 font-title-sm transition-all whitespace-nowrap ${
                activeTab === 'counterfactual'
                  ? 'border-primary text-primary font-bold'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">science</span>
              <span>Counterfactual Diagnosis Lab</span>
            </button>

            <button
              onClick={() => setActiveTab('literature')}
              className={`flex items-center gap-space-xs px-space-md py-space-sm border-b-2 font-title-sm transition-all whitespace-nowrap ${
                activeTab === 'literature'
                  ? 'border-primary text-primary font-bold'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">menu_book</span>
              <span>Evidence & Literature</span>
            </button>

            <button
              onClick={() => setActiveTab('report')}
              className={`flex items-center gap-space-xs px-space-md py-space-sm border-b-2 font-title-sm transition-all whitespace-nowrap ${
                activeTab === 'report'
                  ? 'border-primary text-primary font-bold'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">description</span>
              <span>Clinical Case Report</span>
            </button>
          </div>

          {/* Unified Tab Content Views */}
          {activeTab === 'scribe' && (
            <ClinicalScribeView onSendToDiagnosis={handleScribeToDiagnosis} />
          )}

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
                  <h3 className="font-title-lg text-primary font-bold">No Case Prioritization Run Yet</h3>
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

          {activeTab === 'counterfactual' && (
            <CounterfactualView
              caseId={caseData?.case_id}
              clinicalText={caseData?.clinical_text || inputText}
            />
          )}

          {activeTab === 'literature' && (
            <EvidenceExplorerView
              activeCase={caseData}
              onNavigateToReport={() => setActiveTab('report')}
            />
          )}

          {activeTab === 'report' && (
            <ReportGeneratorView
              activeCase={caseData}
              onNavigateToLiterature={() => setActiveTab('literature')}
            />
          )}

        </div>
      </main>

      <Footer />
    </div>
  );
}
