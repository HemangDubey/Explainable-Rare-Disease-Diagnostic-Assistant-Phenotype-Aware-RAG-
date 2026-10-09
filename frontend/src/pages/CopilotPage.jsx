import React from 'react';
import DoctorCopilot from '../components/DoctorCopilot';
import { PageHeader } from '../app/ui';
import { useWorkspace } from '../app/WorkspaceContext';

export default function CopilotPage() {
  const { askCopilot, isCopilotLoading, caseData } = useWorkspace();
  return (
    <>
      <PageHeader title="AI Doctor Copilot"
        description="Ask questions about the active case. Answers are grounded in the case's computed evidence; when the language model is unavailable a labelled deterministic answer is shown." />
      <DoctorCopilot onAsk={askCopilot} isLoading={isCopilotLoading} currentCase={caseData} />
    </>
  );
}
