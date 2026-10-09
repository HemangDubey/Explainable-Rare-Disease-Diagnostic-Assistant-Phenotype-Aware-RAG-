import React from 'react';
import { useNavigate } from 'react-router-dom';
import EvidenceExplorerView from '../components/EvidenceExplorerView';
import { NeedsCase, PageHeader } from '../app/ui';
import { useWorkspace } from '../app/WorkspaceContext';

export default function EvidencePage() {
  const { caseData } = useWorkspace();
  const navigate = useNavigate();
  return (
    <>
      <PageHeader title="Evidence & Literature"
        description="Evidence profile for each ranked candidate and PubMed literature retrieved for it. Patient findings, disease annotations and literature are kept separate." />
      {caseData ? <EvidenceExplorerView activeCase={caseData} onNavigateToReport={() => navigate('/reports')} /> : <NeedsCase what="The evidence explorer" />}
    </>
  );
}
