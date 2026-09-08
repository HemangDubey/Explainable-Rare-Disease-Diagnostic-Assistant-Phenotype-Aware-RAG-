import React, { useState, useEffect } from 'react';
import { generateCaseReport, getExportReportHtmlUrl } from '../api/client';

export default function ReportGeneratorView({ activeCase, onNavigateToLiterature }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeSection, setActiveSection] = useState('summary');

  const handleGenerateReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await generateCaseReport({
        case_id: activeCase?.case_id || null,
        clinical_text: activeCase?.clinical_text || null,
        top_k: 5
      });
      setReport(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const exportUrl = report ? getExportReportHtmlUrl(report.header.report_id) : null;

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="p-2.5 rounded-lg bg-indigo-50 text-indigo-600 font-bold text-lg">
            📋
          </span>
          <div>
            <h2 className="text-xl font-bold text-slate-800">
              Clinical Case Report Generator
            </h2>
            <p className="text-xs text-slate-500">
              Module 16: Synthesizes complete 11-section clinical case report from diagnostic reasoning & PubMed evidence
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {report && (
            <>
              <a
                href={exportUrl}
                target="_blank"
                rel="noreferrer"
                className="px-4 py-2 bg-slate-800 text-white rounded-lg text-xs font-semibold shadow-sm hover:bg-slate-900 transition flex items-center gap-1.5"
              >
                <span>🖨️</span> Print / Save as PDF
              </a>
              <a
                href={exportUrl}
                download={`Report_${report.header.report_id}.html`}
                className="px-4 py-2 border border-slate-300 text-slate-700 bg-white rounded-lg text-xs font-semibold hover:bg-slate-50 transition"
              >
                Export HTML
              </a>
            </>
          )}

          <button
            onClick={handleGenerateReport}
            disabled={loading}
            className="px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-lg text-xs font-semibold shadow-sm hover:from-blue-700 hover:to-indigo-700 transition disabled:opacity-50 flex items-center gap-1.5"
          >
            {loading ? (
              <>
                <span className="animate-spin w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full"></span>
                <span>Assembling Report...</span>
              </>
            ) : (
              <>
                <span>⚡</span>
                <span>{report ? 'Regenerate Case Report' : 'Generate Full Case Report'}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 text-red-700 text-xs rounded-xl border border-red-200">
          {error}
        </div>
      )}

      {!report && !loading && (
        <div className="p-12 text-center bg-white rounded-xl border border-dashed border-slate-300 space-y-4 shadow-sm">
          <div className="w-12 h-12 bg-indigo-50 text-indigo-600 rounded-full flex items-center justify-center mx-auto text-xl font-bold">
            📄
          </div>
          <div className="max-w-md mx-auto space-y-1">
            <h3 className="text-base font-bold text-slate-800">
              Comprehensive Multi-Section Clinical Case Report
            </h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              Compile patient presentation, HPO terms, top differentials, Indian population genetics, PubMed citations, counterfactual stability, and recommended confirmatory testing into a single clinical document.
            </p>
          </div>
          <button
            onClick={handleGenerateReport}
            className="px-5 py-2.5 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-700 transition shadow-sm"
          >
            Generate Case Report Now
          </button>
        </div>
      )}

      {loading && !report && (
        <div className="p-16 text-center bg-white rounded-xl border border-slate-200 shadow-sm space-y-3">
          <div className="inline-block animate-spin w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full"></div>
          <div className="text-sm font-semibold text-slate-700">Synthesizing Diagnostic Reasoning & Literature...</div>
          <div className="text-xs text-slate-400">Aggregating Phase 1-6 pipelines into 11 structured clinical sections</div>
        </div>
      )}

      {/* Render Generated Report */}
      {report && (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Navigation Sidebar */}
          <div className="space-y-2 lg:col-span-1">
            <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm sticky top-4">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                Report Sections
              </div>
              <nav className="space-y-1 text-xs">
                {[
                  { id: 'summary', label: '1. Case Summary' },
                  { id: 'phenotypes', label: '2. Phenotype & HPO' },
                  { id: 'differentials', label: '3. Top Differentials' },
                  { id: 'population', label: '4. Indian Population Context' },
                  { id: 'literature', label: '5. Literature Evidence' },
                  { id: 'reasoning', label: '6. Explainable Reasoning' },
                  { id: 'counterfactual', label: '7. Sensitivity & Stability' },
                  { id: 'workup', label: '8. Recommended Workup' },
                  { id: 'limitations', label: '9. Limitations & Gaps' }
                ].map(sec => (
                  <button
                    key={sec.id}
                    onClick={() => setActiveSection(sec.id)}
                    className={`w-full text-left px-3 py-2 rounded-lg font-medium transition flex items-center justify-between ${
                      activeSection === sec.id
                        ? 'bg-blue-50 text-blue-700 font-semibold'
                        : 'text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <span>{sec.label}</span>
                    <span className="text-[10px] text-slate-400">✓</span>
                  </button>
                ))}
              </nav>
            </div>
          </div>

          {/* Main Report Content View */}
          <div className="lg:col-span-3 space-y-6">
            {/* Header Box */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                <div>
                  <div className="text-xs font-semibold text-blue-600 uppercase tracking-wider">
                    Official Diagnostic Decision Support Document
                  </div>
                  <h1 className="text-xl font-bold text-slate-900 mt-0.5">
                    Rare-Disease Diagnostic Case Report
                  </h1>
                </div>
                <div className="text-right">
                  <span className="bg-blue-50 text-blue-700 font-mono text-xs px-2.5 py-1 rounded border border-blue-200 font-semibold">
                    {report.header.report_id}
                  </span>
                  <div className="text-[10px] text-slate-400 mt-1">
                    {report.header.generated_at}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs pt-1">
                <div>
                  <span className="text-slate-400">Patient Reference:</span>
                  <div className="font-bold text-slate-700">{report.header.patient_id}</div>
                </div>
                <div>
                  <span className="text-slate-400">Ancestry Context:</span>
                  <div className="font-bold text-slate-700">{report.section_1_case_summary.ancestry}</div>
                </div>
                <div>
                  <span className="text-slate-400">Consanguinity:</span>
                  <div className="font-bold text-slate-700">{report.section_1_case_summary.consanguinity}</div>
                </div>
                <div>
                  <span className="text-slate-400">Top Candidate:</span>
                  <div className="font-bold text-emerald-700">
                    {report.section_3_top_differentials[0]?.disease_name || 'N/A'}
                  </div>
                </div>
              </div>
            </div>

            {/* Section 1: Case Summary */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <span className="text-blue-600">§ 1</span> Patient Presentation & Clinical Narrative
              </h3>
              <div className="bg-slate-50 p-3.5 rounded-lg text-xs text-slate-700 leading-relaxed font-sans">
                {report.section_1_case_summary.full_clinical_presentation}
              </div>
            </div>

            {/* Section 2: Phenotypes & HPO */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <span className="text-blue-600">§ 2</span> Normalized Phenotype Profile (HPO)
              </h3>
              <div className="flex flex-wrap gap-2">
                {report.section_2_phenotype_extraction.mapped_hpo_terms?.map((term, i) => (
                  <span 
                    key={i} 
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-slate-100 border border-slate-200 text-slate-800"
                  >
                    <span className="font-semibold">{term.name || term.term}</span>
                    <span className="font-mono text-[10px] text-slate-500">({term.id})</span>
                  </span>
                ))}
              </div>
            </div>

            {/* Section 3: Top Differentials Table */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <span className="text-blue-600">§ 3</span> Top Differential Diagnoses & Evidence Fusion
              </h3>

              <div className="overflow-x-auto border border-slate-200 rounded-lg">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-600">
                    <tr>
                      <th className="p-2.5">Rank</th>
                      <th className="p-2.5">Candidate Disease</th>
                      <th className="p-2.5 text-center">Final Score</th>
                      <th className="p-2.5 text-center">Phenotype Match</th>
                      <th className="p-2.5 text-center">IndiGen Prior</th>
                      <th className="p-2.5">Tier</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {report.section_3_top_differentials.map((cand) => (
                      <tr key={cand.disease_id} className="hover:bg-slate-50/50">
                        <td className="p-2.5 font-bold text-slate-700">#{cand.rank}</td>
                        <td className="p-2.5">
                          <div className="font-semibold text-slate-800">{cand.disease_name}</div>
                          <div className="text-[10px] text-slate-400 font-mono">
                            {cand.disease_id} {cand.genes?.length > 0 && `• Genes: ${cand.genes.join(', ')}`}
                          </div>
                        </td>
                        <td className="p-2.5 text-center font-bold text-blue-600">
                          {Math.round(cand.final_score * 100)}%
                        </td>
                        <td className="p-2.5 text-center text-slate-600">
                          {Math.round(cand.phenotype_score * 100)}%
                        </td>
                        <td className="p-2.5 text-center font-semibold text-emerald-600">
                          +{Math.round(cand.population_score * 100)}%
                        </td>
                        <td className="p-2.5">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">
                            {cand.confidence_tier}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Section 4: Indian Population Genetics Context */}
            <div className="bg-emerald-50/60 rounded-xl border border-emerald-200 p-6 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-emerald-950 flex items-center gap-2">
                <span>🇮🇳</span> Section 4: Indian Population Genetics Context (IndiGen + gnomAD SAS)
              </h3>
              <div className="text-xs text-emerald-900 space-y-2 leading-relaxed">
                <ul className="list-disc list-inside space-y-1">
                  {report.section_5_indian_population_context.carrier_frequency_notes.map((note, i) => (
                    <li key={i}>{note}</li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Section 5: Literature Highlights */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-3">
              <div className="flex justify-between items-center">
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <span className="text-blue-600">§ 5</span> Verified PubMed Literature Citations
                </h3>
                {onNavigateToLiterature && (
                  <button
                    onClick={onNavigateToLiterature}
                    className="text-xs text-blue-600 hover:underline font-semibold"
                  >
                    Open Literature Explorer ↗
                  </button>
                )}
              </div>

              <div className="space-y-2">
                {report.section_6_literature_evidence.top_pubmed_references.map((pub, i) => (
                  <div key={i} className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-1">
                    <a
                      href={pub.url || `https://pubmed.ncbi.nlm.nih.gov/${pub.pmid}/`}
                      target="_blank"
                      rel="noreferrer"
                      className="font-semibold text-blue-700 hover:underline block"
                    >
                      {pub.title}
                    </a>
                    <div className="text-[11px] text-slate-500 font-mono">
                      PMID: {pub.pmid} • {pub.journal} ({pub.pub_year || pub.year}) • Strength: <b>{pub.strength || pub.evidence_strength}</b>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Section 6: Explainable Reasoning */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <span className="text-blue-600">§ 6</span> Explainable Clinical Reasoning & Mechanism
              </h3>
              <p className="text-xs text-slate-700 leading-relaxed bg-slate-50 p-4 rounded-lg">
                {report.section_7_explainable_reasoning.executive_summary}
              </p>
            </div>

            {/* Section 7: Counterfactual Stability */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <span className="text-blue-600">§ 7</span> Counterfactual Sensitivity & Diagnosis Stability
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div className="p-3 bg-slate-50 rounded-lg space-y-1 border border-slate-200">
                  <div className="font-semibold text-slate-700">Critical Anchor Phenotypes:</div>
                  <div className="text-slate-600">
                    {report.section_9_counterfactual_sensitivity.critical_anchor_phenotypes.join(', ')}
                  </div>
                </div>
                <div className="p-3 bg-slate-50 rounded-lg space-y-1 border border-slate-200">
                  <div className="font-semibold text-slate-700">Diagnosis Rank Stability:</div>
                  <div className="text-slate-600 font-mono font-bold text-emerald-700">
                    {Math.round(report.section_9_counterfactual_sensitivity.rank_stability_score * 100)}% Stable
                  </div>
                </div>
              </div>
            </div>

            {/* Section 8: Recommended Confirmatory Workup */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <span className="text-blue-600">§ 8</span> Recommended Diagnostic Workup & Actionable Next Steps
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div className="p-3.5 bg-blue-50/50 border border-blue-200 rounded-lg space-y-1.5">
                  <div className="font-bold text-blue-900">Confirmatory Genomic Testing:</div>
                  <ul className="list-disc list-inside text-blue-950 space-y-1">
                    {report.section_10_recommended_workup.confirmatory_genetic_tests.map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                </div>

                <div className="p-3.5 bg-indigo-50/50 border border-indigo-200 rounded-lg space-y-1.5">
                  <div className="font-bold text-indigo-900">Biochemical / Metabolic Panel:</div>
                  <ul className="list-disc list-inside text-indigo-950 space-y-1">
                    {report.section_10_recommended_workup.biochemical_metabolic_workup.map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            {/* Section 9: Limitations & Clinical Governance */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <span className="text-blue-600">§ 9</span> Limitations & Evidence Gaps
              </h3>
              <ul className="list-disc list-inside text-xs text-slate-500 space-y-1">
                {report.section_11_limitations_and_gaps.map((lim, i) => (
                  <li key={i}>{lim}</li>
                ))}
              </ul>
            </div>

            {/* Disclaimer Footer */}
            <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-[11px] text-amber-800 leading-relaxed">
              <b>RESEARCH USE ONLY:</b> {report.disclaimer}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
