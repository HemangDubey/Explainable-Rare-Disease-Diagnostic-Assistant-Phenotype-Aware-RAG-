// Active-case state shared by every internal module (previously local to the dashboard's tabs). Moving between sidebar routes keeps
// the current case, its ranked candidates and any explanations. Nothing here is persisted in the browser: the case itself lives in
// the owner-scoped backend store; this is only the in-memory working copy for the open tab.
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { askDoctorCopilot, checkBackendHealth, diagnoseCase, reasonCase } from '../api/client';

export const SAMPLE_CASES = [
  { title: 'Neurodevelopmental & Seizures', text: 'Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.' },
  { title: 'Skeletal Dysplasia & Craniofacial Signs',
    text: 'Patient presents with microcephaly, craniosynostosis, syndactyly, intellectual disability and cardiac murmur.' },
  { title: 'Metabolic & Muscular Weakness',
    text: 'Infant presents with progressive muscle weakness, lactic acidosis, hepatomegaly, failure to thrive and cardiomyopathy.' },
];

const Ctx = createContext(null);

export function useWorkspace() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useWorkspace must be used inside <WorkspaceProvider>');
  return v;
}

export function WorkspaceProvider({ children }) {
  const [inputText, setInputText] = useState(SAMPLE_CASES[0].text);
  const [caseData, setCaseData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [explanations, setExplanations] = useState({});
  const [isExplaining, setIsExplaining] = useState(false);
  const [reasoningStatus, setReasoningStatus] = useState(null);
  const [isCopilotLoading, setIsCopilotLoading] = useState(false);
  const [backendStatus, setBackendStatus] = useState(null);

  useEffect(() => { checkBackendHealth().then(setBackendStatus); }, []);

  const runDiagnosis = useCallback(async (textToRun) => {
    const text = textToRun ?? inputText;
    if (!text || !text.trim()) return null;
    setIsLoading(true);
    setError(null);
    try {
      const data = await diagnoseCase({ text, top_k: 5 });
      setCaseData(data);
      setExplanations({});
      setReasoningStatus(null);
      return data;
    } catch (err) {
      setError(err.message || 'The diagnostic pipeline could not be run.');
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [inputText]);

  const explainCandidates = useCallback(async () => {
    if (!caseData) return;
    setIsExplaining(true);
    setReasoningStatus(null);
    try {
      const res = await reasonCase({ case_id: caseData.case_id, clinical_text: caseData.clinical_text, top_k: 5 });
      const byId = {};
      (res.reasoning?.candidates || []).forEach((c) => { byId[c.candidate_id] = c; });
      setExplanations(byId);
      setReasoningStatus(res.reasoning?.provider || null);
    } catch (err) {
      setReasoningStatus({ status: 'error', reason: err.message });
    } finally {
      setIsExplaining(false);
    }
  }, [caseData]);

  const askCopilot = useCallback(async (query) => {
    setIsCopilotLoading(true);
    try {
      return await askDoctorCopilot({ query, case_id: caseData?.case_id, clinical_text: caseData?.clinical_text || inputText });
    } finally {
      setIsCopilotLoading(false);
    }
  }, [caseData, inputText]);

  const value = useMemo(() => ({
    inputText, setInputText, caseData, isLoading, error, setError, runDiagnosis,
    explanations, isExplaining, reasoningStatus, explainCandidates, isCopilotLoading, askCopilot, backendStatus,
  }), [inputText, caseData, isLoading, error, runDiagnosis, explanations, isExplaining, reasoningStatus, explainCandidates,
    isCopilotLoading, askCopilot, backendStatus]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
