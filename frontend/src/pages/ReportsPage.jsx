import React from 'react';
import { useNavigate } from 'react-router-dom';
import ReportGeneratorView from '../components/ReportGeneratorView';
import { NeedsCase, PageHeader } from '../app/ui';
import { useWorkspace } from '../app/WorkspaceContext';

export default function ReportsPage() {
  const { caseData } = useWorkspace();
  const navigate = useNavigate();
  return (
    <>
      <PageHeader title="Clinical Reports"
        description="Generate the structured case report for the active case, review each section, and print or export it. Reports are saved to your account." />
      {caseData ? <ReportGeneratorView activeCase={caseData} onNavigateToLiterature={() => navigate('/evidence')} /> : <NeedsCase what="Report generation" />}
    </>
  );
}
