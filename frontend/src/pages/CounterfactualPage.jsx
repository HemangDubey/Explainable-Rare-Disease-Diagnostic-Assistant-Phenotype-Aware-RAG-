import React from 'react';
import CounterfactualView from '../components/CounterfactualView';
import { PageHeader } from '../app/ui';
import { useWorkspace } from '../app/WorkspaceContext';

export default function CounterfactualPage() {
  const { caseData, inputText } = useWorkspace();
  return (
    <>
      <PageHeader title="Counterfactual Lab"
        description="Add, remove or modify phenotypes on a copy of the case and re-run the real ranking. The baseline case is never changed; every scenario is saved to the case." />
      <CounterfactualView caseId={caseData?.case_id} clinicalText={caseData?.clinical_text || inputText} />
    </>
  );
}
