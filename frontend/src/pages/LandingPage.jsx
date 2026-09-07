import React from 'react';
import Navbar from '../components/Navbar';
import HeroSection from '../components/HeroSection';
import CredibilityStrip from '../components/CredibilityStrip';
import ProblemSection from '../components/ProblemSection';
import WorkflowSection from '../components/WorkflowSection';
import ArchitectureSection from '../components/ArchitectureSection';
import EvidenceSection from '../components/EvidenceSection';
import ResearchSection from '../components/ResearchSection';
import FeaturesSection from '../components/FeaturesSection';
import EvaluationSection from '../components/EvaluationSection';
import CTASection from '../components/CTASection';
import Footer from '../components/Footer';

export default function LandingPage() {
  return (
    <>
      <Navbar />
      <main className="w-full pt-20 bg-surface min-h-screen">
        <div className="flex flex-col w-full">
          <HeroSection />
          <CredibilityStrip />
          <ProblemSection />
          <WorkflowSection />
          <ArchitectureSection />
          <EvidenceSection />
          <ResearchSection />
          <FeaturesSection />
          <EvaluationSection />
          <CTASection />
        </div>
      </main>
      <Footer />
    </>
  );
}
