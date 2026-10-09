import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import ClinicalScribePage from './pages/ClinicalScribePage';
import CounterfactualPage from './pages/CounterfactualPage';
import DifferentialPage from './pages/DifferentialPage';
import CopilotPage from './pages/CopilotPage';
import EvidencePage from './pages/EvidencePage';
import ReportsPage from './pages/ReportsPage';
import CasesPage from './pages/CasesPage';
// The Digital Twin pulls in three.js / d3; it is split out so the rest of the app does not download it.
const DigitalTwinPage = lazy(() => import('./pages/DigitalTwinPage'));
import Navbar from './components/Navbar';
import AuthPanel from './components/AuthPanel';
import { AuthProvider, useAuth } from './components/AuthContext';
import AppShell from './app/AppShell';
import { WorkspaceProvider } from './app/WorkspaceContext';
import { LoadingState } from './app/ui';

// Signed-out visitors see the sign-in card instead of the workspace. If the server later rejects the session (expiry, logout elsewhere),
// the workspace stays mounted so unsaved edits are kept, and a sign-in overlay appears on top.
function Protected({ children }) {
  const { session, expired, onAuthenticated } = useAuth();
  if (!session && !expired) {
    return (
      <div className="min-h-screen bg-surface">
        <Navbar />
        <main className="pt-32 px-gutter-mobile lg:px-gutter-desktop pb-space-3xl">
          <AuthPanel onAuthenticated={onAuthenticated} />
        </main>
      </div>
    );
  }
  return (
    <>
      {children}
      {expired && (
        <div className="fixed inset-0 z-[100] bg-black/40 flex items-center justify-center p-space-md overflow-y-auto" role="dialog" aria-modal="true">
          <AuthPanel onAuthenticated={onAuthenticated}
            notice="Session expired. Sign in again to continue. Anything you have typed on this page is still here, but may not have been saved." />
        </div>
      )}
    </>
  );
}

// Every internal module renders inside one authenticated application shell (sidebar + top bar) sharing the active case.
function Workspace() {
  return (
    <Protected>
      <WorkspaceProvider>
        <AppShell />
      </WorkspaceProvider>
    </Protected>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route element={<Workspace />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/differential" element={<DifferentialPage />} />
            <Route path="/clinical-scribe" element={<ClinicalScribePage />} />
            <Route path="/copilot" element={<CopilotPage />} />
            <Route path="/evidence" element={<EvidencePage />} />
            <Route path="/counterfactual" element={<CounterfactualPage />} />
            <Route path="/digital-twin" element={<Suspense fallback={<LoadingState label="Loading the Digital Twin…" />}><DigitalTwinPage /></Suspense>} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/cases" element={<CasesPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}
