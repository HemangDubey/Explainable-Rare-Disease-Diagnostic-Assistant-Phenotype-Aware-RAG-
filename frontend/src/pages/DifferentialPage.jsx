import React from 'react';
import DifferentialExplorer from '../components/DifferentialExplorer';
import { NeedsCase, PageHeader } from '../app/ui';
import { useWorkspace } from '../app/WorkspaceContext';

export default function DifferentialPage() {
  const { caseData } = useWorkspace();
  return (
    <>
      <PageHeader title="Differential Diagnosis"
        description="Compare the ranked candidates of the active case: matched and unmatched phenotypes, score components and evidence completeness." />
      {caseData ? <DifferentialExplorer differential={caseData.differential} onSelectCandidate={() => {}} /> : <NeedsCase what="The differential view" />}
    </>
  );
}
