import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import ClinicalScribePage from './pages/ClinicalScribePage';
import CounterfactualPage from './pages/CounterfactualPage';

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/clinical-scribe" element={<ClinicalScribePage />} />
        <Route path="/counterfactual" element={<CounterfactualPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Router>
  );
}

