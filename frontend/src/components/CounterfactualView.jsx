import React, { useState, useEffect } from 'react';
import { runCounterfactual } from '../api/client';

const SAMPLE_CASE_TEXT = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.";

export default function CounterfactualView({ caseId, clinicalText = SAMPLE_CASE_TEXT }) {
  const [addPhenotypeInput, setAddPhenotypeInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [cfData, setCfData] = useState(null);

  useEffect(() => {
    handleRunCounterfactual('compare', {});
  }, [caseId, clinicalText]);

  const handleRunCounterfactual = async (op, options = {}) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await runCounterfactual({
        case_id: caseId,
        clinical_text: clinicalText,
        operation: op,
        phenotype_id: options.phenotype_id,
        added_phenotypes: options.added_phenotypes || [],
        removed_phenotypes: options.removed_phenotypes || [],
        modified_phenotypes: options.modified_phenotypes || [],
        top_k: 5
      });
      setCfData(data);
    } catch (err) {
      console.error('Counterfactual error:', err);
      setError(err.message || 'Counterfactual analysis failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRemovePhenotype = (hpoIdOrName) => {
    handleRunCounterfactual('remove', { phenotype_id: hpoIdOrName });
  };

  const handleAddPhenotypeSubmit = (e) => {
    e.preventDefault();
    if (!addPhenotypeInput.trim()) return;
    handleRunCounterfactual('add', { phenotype_id: addPhenotypeInput.trim() });
    setAddPhenotypeInput('');
  };

  return (
    <div className="flex flex-col gap-space-xl">
      {/* Active Case & What-If Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
        {/* Active Baseline Phenotypes Box */}
        <div className="lg:col-span-7 bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-space-xs">
              <h3 className="font-title-md text-primary font-bold flex items-center gap-space-2xs">
                <span className="material-symbols-outlined text-secondary text-[20px]">science</span>
                Active Phenotype Set (State A vs State B)
              </h3>
              <span className="text-label-sm text-on-surface-variant font-medium">
                Click phenotype chip to REMOVE
              </span>
            </div>

            <div className="flex flex-wrap gap-space-xs my-space-sm">
              {cfData?.modified_phenotypes?.map((hp, idx) => (
                <button
                  key={idx}
                  onClick={() => handleRemovePhenotype(hp.hpo_id || hp.name)}
                  className="inline-flex items-center gap-space-3xs px-space-sm py-space-xs rounded-xl bg-secondary-fixed/60 hover:bg-tertiary-fixed/60 text-on-secondary-fixed font-code-metric text-label-sm font-bold shadow-sm transition-all group"
                  title="Click to remove phenotype in counterfactual run"
                >
                  <span>{hp.name || hp.hpo_id}</span>
                  <span className="material-symbols-outlined text-[14px] text-error group-hover:scale-125 transition-transform">
                    cancel
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="pt-space-xs border-t border-outline-variant/20 flex items-center justify-between text-body-sm text-on-surface-variant">
            <span>Original Phenotypes: {cfData?.baseline_phenotypes?.length || 0}</span>
            <span>Active Modified Phenotypes: {cfData?.modified_phenotypes?.length || 0}</span>
          </div>
        </div>

        {/* Add Phenotype Form */}
        <div className="lg:col-span-5 bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <div>
            <h3 className="font-title-md text-primary font-bold mb-space-xs flex items-center gap-space-2xs">
              <span className="material-symbols-outlined text-secondary text-[20px]">add_circle</span>
              Add Phenotype to What-If State
            </h3>
            <form onSubmit={handleAddPhenotypeSubmit} className="flex flex-col gap-space-xs">
              <input
                type="text"
                value={addPhenotypeInput}
                onChange={(e) => setAddPhenotypeInput(e.target.value)}
                placeholder="e.g. Facial dysmorphism, Microcephaly, HP:0001250..."
                className="w-full p-space-sm rounded-xl bg-surface border border-outline-variant text-body-md focus:outline-none focus:ring-2 focus:ring-secondary"
              />
              <button
                type="submit"
                disabled={isLoading || !addPhenotypeInput.trim()}
                className="w-full py-space-xs px-space-md rounded-xl bg-primary hover:bg-primary/90 text-on-primary font-label-md font-bold transition-all shadow-md disabled:opacity-50 flex items-center justify-center gap-space-2xs"
              >
                <span className="material-symbols-outlined text-[18px]">play_arrow</span>
                <span>Run Counterfactual with Added Phenotype</span>
              </button>
            </form>
          </div>

          <button
            onClick={() => handleRunCounterfactual('compare', { modified_phenotypes: cfData?.baseline_phenotypes?.map(h => h.name) })}
            className="mt-space-sm text-label-sm text-secondary font-bold hover:underline self-start"
          >
            Reset to Baseline Case State
          </button>
        </div>
      </div>

      {error && (
        <div className="p-space-md rounded-xl bg-error-container text-on-error-container font-label-md">
          {error}
        </div>
      )}

      {/* Counterfactual Experiment Results */}
      {cfData && (
        <div className="flex flex-col gap-space-xl">
          {/* Table 1: Original vs Modified Ranking Comparison */}
          <div className="bg-surface-container-lowest rounded-2xl p-space-xl shadow-sm border border-outline-variant/30">
            <div className="flex items-center justify-between mb-space-md pb-space-xs border-b border-outline-variant/20">
              <h3 className="font-title-lg text-primary font-bold flex items-center gap-space-2xs">
                <span className="material-symbols-outlined text-secondary text-[22px]">format_list_numbered</span>
                Original vs Counterfactual Candidate Ranking
              </h3>
              <span className="font-code-metric text-label-sm px-space-xs py-0.5 rounded bg-surface-container text-primary font-semibold">
                OP: {cfData.operation.toUpperCase()}
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-outline-variant/30 text-label-md text-on-surface-variant uppercase font-bold bg-surface-container-low/50">
                    <th className="py-space-xs px-space-sm">Candidate Disease</th>
                    <th className="py-space-xs px-space-sm text-center">Original Rank</th>
                    <th className="py-space-xs px-space-sm text-center">Modified Rank</th>
                    <th className="py-space-xs px-space-sm text-right">Original Score</th>
                    <th className="py-space-xs px-space-sm text-right">Modified Score</th>
                    <th className="py-space-xs px-space-sm text-right">Δ Score</th>
                    <th className="py-space-xs px-space-sm text-center">Shift Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {cfData.ranking_deltas?.map((delta, idx) => (
                    <tr key={idx} className="border-b border-outline-variant/10 hover:bg-surface-container-low/30 transition-colors">
                      <td className="py-space-sm px-space-sm font-title-sm font-bold text-primary">
                        {delta.disease_name}
                        <span className="block font-code-metric text-label-sm text-on-surface-variant font-normal">
                          {delta.disease_id}
                        </span>
                      </td>
                      <td className="py-space-sm px-space-sm text-center font-code-metric font-bold">
                        #{delta.original_rank}
                      </td>
                      <td className="py-space-sm px-space-sm text-center font-code-metric font-bold text-secondary">
                        #{delta.counterfactual_rank}
                      </td>
                      <td className="py-space-sm px-space-sm text-right font-code-metric">
                        {delta.original_score.toFixed(4)}
                      </td>
                      <td className="py-space-sm px-space-sm text-right font-code-metric font-bold">
                        {delta.counterfactual_score.toFixed(4)}
                      </td>
                      <td className={`py-space-sm px-space-sm text-right font-code-metric font-bold ${delta.score_delta > 0 ? 'text-accent-sage' : delta.score_delta < 0 ? 'text-error' : 'text-on-surface-variant'}`}>
                        {delta.score_delta > 0 ? `+${delta.score_delta.toFixed(4)}` : delta.score_delta.toFixed(4)}
                      </td>
                      <td className="py-space-sm px-space-sm text-center">
                        {delta.rank_change > 0 ? (
                          <span className="inline-flex items-center gap-0.5 px-space-xs py-0.5 rounded-full bg-accent-sage/20 text-accent-sage font-label-sm font-bold">
                            ↑ +{delta.rank_change}
                          </span>
                        ) : delta.rank_change < 0 ? (
                          <span className="inline-flex items-center gap-0.5 px-space-xs py-0.5 rounded-full bg-error-container text-on-error-container font-label-sm font-bold">
                            ↓ {delta.rank_change}
                          </span>
                        ) : (
                          <span className="px-space-xs py-0.5 rounded-full bg-surface-container text-on-surface-variant font-label-sm font-semibold">
                            — Unchanged
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Phenotype Ranking Sensitivity & AI Insights Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
            {/* Phenotype Impact Sensitivity Cards */}
            <div className="lg:col-span-6 bg-surface-container-lowest rounded-2xl p-space-xl shadow-sm border border-outline-variant/30 flex flex-col gap-space-md">
              <h3 className="font-title-lg text-primary font-bold flex items-center gap-space-2xs">
                <span className="material-symbols-outlined text-secondary text-[22px]">bar_chart</span>
                Phenotype Ranking Sensitivity (Ablation Influence)
              </h3>
              <p className="text-body-sm text-on-surface-variant">
                Quantifies candidate ranking sensitivity when individual phenotypes are ablated from the case.
              </p>

              <div className="flex flex-col gap-space-xs mt-space-xs">
                {cfData.phenotype_impacts?.map((imp, idx) => (
                  <div key={idx} className="p-space-sm rounded-xl bg-surface-container-low border border-outline-variant/20 flex items-center justify-between">
                    <div>
                      <span className="font-title-sm font-bold text-primary block">{imp.hpo_name}</span>
                      <span className="font-code-metric text-label-sm text-secondary font-semibold">{imp.hpo_id}</span>
                    </div>
                    <div className="text-right">
                      <span className="font-code-metric text-title-sm font-bold text-primary block">
                        Δ {imp.impact_score.toFixed(4)}
                      </span>
                      <span className={`text-label-sm font-bold ${imp.sensitivity_level.includes('High') ? 'text-tertiary' : 'text-secondary'}`}>
                        {imp.sensitivity_level}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* AI-Generated Counterfactual Insights */}
            <div className="lg:col-span-6 bg-surface-container-lowest rounded-2xl p-space-xl shadow-sm border border-outline-variant/30 flex flex-col justify-between">
              <div>
                <h3 className="font-title-lg text-primary font-bold mb-space-md flex items-center gap-space-2xs">
                  <span className="material-symbols-outlined text-secondary text-[22px]">auto_awesome</span>
                  Grounded Counterfactual Reasoning Insights
                </h3>

                <div className="flex flex-col gap-space-sm mb-space-md">
                  {cfData.insights?.map((ins, idx) => (
                    <div key={idx} className="p-space-md rounded-xl bg-surface-container-low border border-secondary/20 flex items-start gap-space-xs">
                      <span className="material-symbols-outlined text-secondary text-[20px] mt-0.5">verified</span>
                      <p className="text-body-md text-on-surface font-medium leading-relaxed">
                        {ins}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-space-sm rounded-xl bg-surface-container text-on-surface-variant text-label-sm flex items-center gap-space-xs font-medium border border-outline-variant/20">
                <span className="material-symbols-outlined text-secondary text-[18px]">info</span>
                <span>{cfData.disclaimer}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
