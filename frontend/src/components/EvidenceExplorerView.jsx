import React, { useState, useEffect } from 'react';
import { 
  searchLiterature, 
  getEvidenceProfile, 
  getEvidenceMatrix, 
  getLiteratureArticle 
} from '../api/client';

export default function EvidenceExplorerView({ 
  activeCase, 
  onSelectCandidate,
  onNavigateToReport 
}) {
  const candidates = activeCase?.fused_candidates || activeCase?.ranked_candidates || [];
  const [selectedDisease, setSelectedDisease] = useState(
    candidates.length > 0 ? candidates[0] : null
  );

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [profile, setProfile] = useState(null);
  const [matrixData, setMatrixData] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState('ALL');
  const [customSearchText, setCustomSearchText] = useState('');
  const [activeArticleModal, setActiveArticleModal] = useState(null);

  // Sync selectedDisease when activeCase updates
  useEffect(() => {
    if (candidates.length > 0 && (!selectedDisease || !candidates.find(c => c.disease_id === selectedDisease.disease_id))) {
      setSelectedDisease(candidates[0]);
    }
  }, [activeCase]);

  // Fetch literature profile and matrix whenever selectedDisease changes
  useEffect(() => {
    if (!selectedDisease) return;

    let isMounted = true;
    async function loadLiterature() {
      setLoading(true);
      setError(null);
      try {
        const diseaseId = selectedDisease.disease_id;
        const caseId = activeCase?.case_id || null;

        const [prof, mat] = await Promise.all([
          getEvidenceProfile(diseaseId, caseId).catch(err => {
            console.warn('Profile fetch failed:', err);
            return null;
          }),
          getEvidenceMatrix(diseaseId, caseId).catch(err => {
            console.warn('Matrix fetch failed:', err);
            return null;
          })
        ]);

        if (isMounted) {
          setProfile(prof);
          setMatrixData(mat);
        }
      } catch (err) {
        if (isMounted) setError(err.message);
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    loadLiterature();
    return () => { isMounted = false; };
  }, [selectedDisease, activeCase?.case_id]);

  const handleCustomSearch = async (e) => {
    e.preventDefault();
    if (!customSearchText.trim() || !selectedDisease) return;

    setLoading(true);
    setError(null);
    try {
      const res = await searchLiterature({
        disease_id: selectedDisease.disease_id,
        disease_name: selectedDisease.disease_name,
        genes: selectedDisease.genes || [],
        phenotypes: activeCase?.extracted_phenotypes?.map(p => typeof p === 'string' ? p : p.text) || [],
        custom_query: customSearchText.trim(),
        max_results: 10
      });

      // Update profile with search results
      if (profile) {
        setProfile({
          ...profile,
          top_articles: res.articles || []
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredArticles = profile?.top_articles?.filter(art => {
    if (selectedCategory === 'ALL') return true;
    if (selectedCategory === 'INDIAN') return art.is_indian_cohort;
    return art.evidence_category === selectedCategory;
  }) || [];

  return (
    <div className="space-y-6">
      {onNavigateToReport && (
        <div className="flex justify-end">
          <button type="button" onClick={onNavigateToReport} className="ui-btn-secondary">
            <span className="material-symbols-outlined text-[18px]" aria-hidden="true">description</span>Generate case report
          </button>
        </div>
      )}

      {/* Candidate Selector Tabs */}
      {candidates.length > 0 ? (
        <div className="flex gap-2 overflow-x-auto pb-2 border-b border-slate-200">
          {candidates.map((cand, idx) => {
            const isSelected = selectedDisease?.disease_id === cand.disease_id;
            return (
              <button
                key={cand.disease_id || idx}
                onClick={() => setSelectedDisease(cand)}
                className={`px-4 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition flex items-center gap-2 border ${
                  isSelected 
                    ? 'bg-blue-50 border-blue-400 text-blue-700 shadow-sm' 
                    : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                  isSelected ? 'bg-blue-600 text-white' : 'bg-slate-200 text-slate-700'
                }`}>
                  {idx + 1}
                </span>
                <span>{cand.disease_name}</span>
                <span className="text-[10px] opacity-75 font-mono">
                  ({Math.round((cand.final_score || 0) * 100)}%)
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-xs">
          No diagnostic candidates prioritized yet. Run a diagnosis in the primary pipeline first or browse general literature.
        </div>
      )}

      {/* Main Literature Workspace */}
      {selectedDisease && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left 2 Columns: Evidence Matrix & Literature Cards */}
          <div className="lg:col-span-2 space-y-6">
            {/* Search Query Bar */}
            <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
              <form onSubmit={handleCustomSearch} className="flex gap-2">
                <input
                  type="text"
                  value={customSearchText}
                  onChange={(e) => setCustomSearchText(e.target.value)}
                  placeholder={`Search PubMed for ${selectedDisease.disease_name}... (e.g. mutation, pediatric, India)`}
                  className="flex-1 px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  type="submit"
                  disabled={loading}
                  className="px-4 py-2 bg-slate-800 text-white rounded-lg text-xs font-semibold hover:bg-slate-900 transition disabled:opacity-50"
                >
                  {loading ? 'Searching...' : 'Search PubMed'}
                </button>
              </form>
            </div>

            {/* Phenotype x Literature Evidence Matrix */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px]" aria-hidden="true">grid_on</span> Phenotype × Literature Evidence Matrix
                </h3>
                <span className="text-[11px] text-slate-500">
                  Direct cross-reference of patient phenotypes with verified citations
                </span>
              </div>

              {matrixData?.matrix && matrixData.matrix.length > 0 ? (
                <div className="overflow-x-auto border border-slate-200 rounded-lg">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="p-2.5 font-semibold text-slate-700">Patient Phenotype</th>
                        {matrixData.pmids.map(pmid => (
                          <th key={pmid} className="p-2.5 font-semibold text-slate-700 text-center">
                            <a 
                              href={`https://pubmed.ncbi.nlm.nih.gov/${pmid}/`} 
                              target="_blank" 
                              rel="noreferrer"
                              className="text-blue-600 hover:underline"
                            >
                              PMID:{pmid}
                            </a>
                          </th>
                        ))}
                        <th className="p-2.5 font-semibold text-slate-700 text-center">Support</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {matrixData.matrix.map((row, rIdx) => (
                        <tr key={rIdx} className="hover:bg-slate-50/50">
                          <td className="p-2.5 font-medium text-slate-800">
                            <div>{row.phenotype}</div>
                            {row.hpo_id && (
                              <div className="text-[10px] text-slate-400 font-mono">{row.hpo_id}</div>
                            )}
                          </td>
                          {matrixData.pmids.map(pmid => {
                            const status = row.paper_statuses[pmid] || '-';
                            return (
                              <td key={pmid} className="p-2.5 text-center">
                                <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold ${
                                  status === '✓' 
                                    ? 'bg-emerald-100 text-emerald-800 border border-emerald-300' 
                                    : status === '?' 
                                      ? 'bg-amber-100 text-amber-800 border border-amber-300' 
                                      : 'text-slate-300'
                                }`}>
                                  {status}
                                </span>
                              </td>
                            );
                          })}
                          <td className="p-2.5 text-center font-semibold text-slate-700">
                            {row.evidence_count} / {matrixData.pmids.length}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-6 text-center text-xs text-slate-500 bg-slate-50 rounded-lg border border-dashed border-slate-200">
                  {loading ? 'Compiling evidence matrix from PubMed...' : 'No matrix data available yet.'}
                </div>
              )}
            </div>

            {/* Literature Filter & Articles List */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
                <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px]" aria-hidden="true">article</span> Verified PubMed Citations ({filteredArticles.length})
                </h3>

                {/* Filter Pills */}
                <div className="flex flex-wrap gap-1.5 text-xs">
                  {['ALL', 'Gene-Disease Association', 'Phenotype Evidence', 'INDIAN', 'Case Report'].map(cat => (
                    <button
                      key={cat}
                      onClick={() => setSelectedCategory(cat)}
                      className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition ${
                        selectedCategory === cat
                          ? 'bg-slate-800 text-white'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {cat === 'INDIAN' ? 'Indian Cohorts' : cat}
                    </button>
                  ))}
                </div>
              </div>

              {loading && (
                <div className="p-8 text-center text-xs text-slate-500">
                  <div className="inline-block animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mb-2"></div>
                  <div>Querying NCBI PubMed and scoring relevance...</div>
                </div>
              )}

              {error && (
                <div className="p-3 bg-red-50 text-red-700 text-xs rounded-lg border border-red-200">
                  {error}
                </div>
              )}

              {!loading && filteredArticles.length === 0 && (
                <div className="p-8 text-center text-xs text-slate-400 bg-slate-50 rounded-lg">
                  No articles found for selected category.
                </div>
              )}

              {!loading && filteredArticles.map(art => (
                <div 
                  key={art.pmid} 
                  className="p-4 rounded-lg border border-slate-200 hover:border-blue-300 hover:shadow-md transition bg-white space-y-2"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <a
                        href={art.url || `https://pubmed.ncbi.nlm.nih.gov/${art.pmid}/`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm font-semibold text-blue-700 hover:underline"
                      >
                        {art.title}
                      </a>
                      <div className="text-[11px] text-slate-500 mt-1">
                        {art.authors?.slice(0, 3).join(', ')}{art.authors?.length > 3 ? ' et al.' : ''} • 
                        <span className="font-medium text-slate-700"> {art.journal}</span> ({art.pub_year || 'Recent'})
                      </div>
                    </div>

                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        art.evidence_strength === 'STRONG'
                          ? 'bg-green-100 text-green-800 border border-green-300'
                          : art.evidence_strength === 'MODERATE'
                            ? 'bg-blue-100 text-blue-800 border border-blue-300'
                            : 'bg-slate-100 text-slate-700'
                      }`}>
                        {art.evidence_strength}
                      </span>
                      {art.is_indian_cohort && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-orange-100 text-orange-800 border border-orange-300">
                          Indian Cohort
                        </span>
                      )}
                    </div>
                  </div>

                  {art.abstract && (
                    <p className="text-xs text-slate-600 line-clamp-3 leading-relaxed">
                      {art.abstract}
                    </p>
                  )}

                  <div className="pt-2 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 text-[11px]">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-400 font-mono">PMID: {art.pmid}</span>
                      {art.doi && (
                        <span className="text-slate-400 font-mono">DOI: {art.doi}</span>
                      )}
                    </div>

                    <div className="flex items-center gap-3">
                      <span className="text-slate-500">
                        Relevance: <b className="text-slate-800">{Math.round((art.relevance_score || 0) * 100)}%</b>
                      </span>
                      <button
                        onClick={() => setActiveArticleModal(art)}
                        className="text-blue-600 hover:text-blue-800 font-medium"
                      >
                        Read Abstract ↗
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right Column: Disease Literature Stats & Population Intelligence */}
          <div className="space-y-6">
            {/* Candidate Overview Card */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
              <h3 className="text-sm font-bold text-slate-800 border-b border-slate-100 pb-2">
                Disease Literature Summary
              </h3>

              <div className="space-y-3 text-xs">
                <div>
                  <div className="text-slate-400">Target Candidate:</div>
                  <div className="font-bold text-slate-800 text-sm">{selectedDisease.disease_name}</div>
                  <div className="text-[11px] text-slate-500 font-mono">{selectedDisease.disease_id}</div>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-2">
                  <div className="bg-slate-50 p-2.5 rounded-lg text-center">
                    <div className="text-lg font-bold text-slate-800">
                      {profile?.total_articles || 0}
                    </div>
                    <div className="text-[10px] text-slate-500">Indexed Papers</div>
                  </div>

                  <div className="bg-emerald-50 p-2.5 rounded-lg text-center">
                    <div className="text-lg font-bold text-emerald-700">
                      {profile?.strong_evidence_count || 0}
                    </div>
                    <div className="text-[10px] text-emerald-600">Strong Evidence</div>
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-[11px] mb-1">
                    <span className="text-slate-500">Phenotype Literature Coverage:</span>
                    <span className="font-bold text-slate-700">{profile?.phenotype_coverage_pct || 0}%</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-2">
                    <div 
                      className="bg-blue-600 h-2 rounded-full transition-all duration-500" 
                      style={{ width: `${profile?.phenotype_coverage_pct || 0}%` }}
                    ></div>
                  </div>
                </div>
              </div>
            </div>

            {/* Indian Cohort Intelligence */}
            <div className="bg-warn-soft rounded-xl border border-warn/20 p-5 space-y-3">
              <div className="flex items-center gap-2 text-amber-900 font-bold text-sm">
                <span className="material-symbols-outlined text-[16px]" aria-hidden="true">groups</span> Indian Cohort Evidence
              </div>

              <p className="text-xs text-amber-900/80 leading-relaxed">
                Publications referencing Indian, South Asian, or IndiGen patient series for {selectedDisease.disease_name}.
              </p>

              {profile?.indian_cohort_articles && profile.indian_cohort_articles.length > 0 ? (
                <div className="space-y-2 pt-2">
                  {profile.indian_cohort_articles.map(art => (
                    <div key={art.pmid} className="p-2.5 bg-white/80 rounded border border-amber-200 text-xs">
                      <a 
                        href={art.url} 
                        target="_blank" 
                        rel="noreferrer"
                        className="font-medium text-amber-950 hover:underline block line-clamp-2"
                      >
                        {art.title}
                      </a>
                      <span className="text-[10px] text-amber-700 font-mono mt-1 block">
                        PMID: {art.pmid} ({art.pub_year || 'Recent'})
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-3 bg-white/60 rounded text-center text-xs text-amber-800">
                  No Indian-cohort studies were identified in this literature batch. This does not mean none exist.
                </div>
              )}
            </div>

            {/* Category Breakdown */}
            {profile?.category_breakdown && (
              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
                <h3 className="text-sm font-bold text-slate-800">
                  Evidence Categories
                </h3>
                <div className="space-y-2 text-xs">
                  {Object.entries(profile.category_breakdown).map(([cat, count]) => (
                    <div key={cat} className="flex justify-between items-center py-1 border-b border-slate-100 last:border-0">
                      <span className="text-slate-600">{cat}</span>
                      <span className="font-semibold bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-[11px]">
                        {count}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Abstract Modal */}
      {activeArticleModal && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-2xl w-full p-6 shadow-2xl space-y-4 max-h-[85vh] overflow-y-auto">
            <div className="flex justify-between items-start gap-4">
              <h3 className="text-base font-bold text-slate-900 leading-snug">
                {activeArticleModal.title}
              </h3>
              <button
                onClick={() => setActiveArticleModal(null)}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <div className="text-xs text-slate-500 font-mono border-y border-slate-100 py-2 flex flex-wrap gap-4">
              <span><b>PMID:</b> {activeArticleModal.pmid}</span>
              <span><b>Journal:</b> {activeArticleModal.journal}</span>
              <span><b>Year:</b> {activeArticleModal.pub_year || 'N/A'}</span>
            </div>

            <div className="text-xs text-slate-700 leading-relaxed space-y-2 whitespace-pre-line">
              <b>Abstract:</b>
              <p>{activeArticleModal.abstract || 'No abstract text available for this citation.'}</p>
            </div>

            <div className="pt-3 border-t border-slate-100 flex justify-between items-center">
              <a
                href={activeArticleModal.url || `https://pubmed.ncbi.nlm.nih.gov/${activeArticleModal.pmid}/`}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-blue-600 hover:underline font-semibold"
              >
                View on PubMed Official Site ↗
              </a>
              <button
                onClick={() => setActiveArticleModal(null)}
                className="px-4 py-1.5 bg-slate-100 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
