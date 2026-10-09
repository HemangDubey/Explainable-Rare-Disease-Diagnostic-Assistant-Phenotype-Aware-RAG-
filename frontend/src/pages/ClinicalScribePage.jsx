import React from 'react';
import { useNavigate } from 'react-router-dom';
import ClinicalScribeView from '../components/ClinicalScribeView';
import { PageHeader } from '../app/ui';
import { useWorkspace } from '../app/WorkspaceContext';

export default function ClinicalScribePage() {
  const { setInputText, runDiagnosis } = useWorkspace();
  const navigate = useNavigate();
  const sendToDiagnosis = (text) => {
    setInputText(text);
    navigate('/dashboard');
    runDiagnosis(text);
  };
  return (
    <>
      <PageHeader title="Clinical Scribe"
        description="Type or dictate a clinical note, structure it into findings, review the draft, and send it to the diagnostic workspace. Drafts are saved to your account." />
      <ClinicalScribeView onSendToDiagnosis={sendToDiagnosis} />
    </>
  );
}
