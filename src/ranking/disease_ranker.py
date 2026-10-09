"""Transparent population-aware re-ranking of Phase 2R retrieval candidates.

    base_score   = w_phenotype * phenotype_score + w_retrieval * retrieval_score      (w_phenotype + w_retrieval = 1)
    final_score  = base_score + population_contribution
    population_contribution = w_population * (population_signal - population_reference)    if a signal exists
                            = 0                                                              otherwise (no evidence -> no adjustment)

phenotype_score = HPO-overlap fraction; retrieval_score = Phase 2R `retrieval_score_norm`. These two are never
modified here. `rank_change` compares the final rank with the rank the SAME candidates get from base_score alone
(i.e. without population evidence), so the population effect is separately measurable.
All weights come from the single `ranking:` block of configs/config.yaml.
"""
from typing import Dict, List, Optional

import yaml

from src.ranking.population_prior import PopulationPriorEngine

# legacy experiment names used by the API/UI -> population components switched on
_OFF = dict(use_indigen=False, use_gnomad_global=False, use_gnomad_sas=False, use_sas_vs_global=False)
EXPERIMENTS = {
    "rag_only": dict(_OFF),                                                        # A
    "rag_south_asian": {**_OFF, "use_gnomad_sas": True},                           # B
    "rag_south_asian_global": {**_OFF, "use_gnomad_sas": True, "use_sas_vs_global": True},   # C
    "rag_indigen": {**_OFF, "use_indigen": True},                                  # D (blocked until IndiGen exists)
    "rag_gnomad_global": {**_OFF, "use_gnomad_global": True},                      # extra: global baseline only
    "rag_indigen_gnomad": {**_OFF, "use_indigen": True, "use_gnomad_global": True},  # legacy API name
}


def load_ranking_config(config_path="configs/config.yaml") -> dict:
    r = yaml.safe_load(open(config_path, encoding="utf-8"))["ranking"]
    w_h, w_r = float(r["w_phenotype"]), float(r["w_retrieval"])
    s = w_h + w_r
    if s <= 0:
        raise ValueError("w_phenotype + w_retrieval must be > 0")
    return {"w_phenotype": w_h / s, "w_retrieval": w_r / s, "w_population": float(r["w_population"]),
            "population_reference": float(r["population_reference"])}


def _ranks(scores: List[float]) -> List[int]:
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))       # stable: ties keep retrieval order
    ranks = [0] * len(scores)
    for pos, i in enumerate(order, 1):
        ranks[i] = pos
    return ranks


class DiseaseRanker:
    def __init__(self, config_path="configs/config.yaml", weights: Optional[dict] = None, population_engine=None):
        self.config_path = config_path
        self.weights = {**load_ranking_config(config_path), **(weights or {})}
        self.pop = population_engine or PopulationPriorEngine(config_path)
        self._cache: Dict[tuple, dict] = {}

    def population_for(self, genes, flags) -> dict:
        key = (tuple(genes), tuple(sorted(flags.items())))
        if key not in self._cache:
            self._cache[key] = self.pop.compute_population_scores(list(genes), **flags)
        return self._cache[key]

    def rank_candidates(self, candidates: List[dict], exp_config: str = "rag_south_asian_global", weights: Optional[dict] = None,
                        population_flags: Optional[dict] = None) -> List[dict]:
        w = {**self.weights, **(weights or {})}
        flags = population_flags if population_flags is not None else EXPERIMENTS.get(exp_config, EXPERIMENTS["rag_south_asian_global"])
        items = []
        for c in candidates:
            ph = float(c.get("hpo_match_score", c.get("phenotype_overlap", 0.0)))
            rt = float(c.get("retrieval_score_norm", c.get("embedding_similarity", 0.0)))
            base = w["w_phenotype"] * ph + w["w_retrieval"] * rt
            pop = self.population_for(c.get("associated_genes", []) or [], flags)
            sig = pop["population_signal"]
            contrib = w["w_population"] * (sig - w["population_reference"]) if (sig is not None and w["w_population"] != 0) else 0.0
            items.append((c, ph, rt, base, pop, sig, contrib))
        base_rank = _ranks([x[3] for x in items])
        final_rank = _ranks([x[3] + x[6] for x in items])
        out = []
        for (c, ph, rt, base, pop, sig, contrib), br, fr in zip(items, base_rank, final_rank):
            ind, glo, sas = pop["indigen"], pop["gnomad_global"], pop["gnomad_sas"]
            out.append({
                "disease_id": c.get("disease_id"), "disease_name": c.get("disease_name"),
                "phenotype_score": round(ph, 6), "retrieval_score": round(rt, 6),
                "base_score": round(base, 6),
                "population": {
                    "status": pop["status"], "level": pop["level"], "signal": None if sig is None else round(sig, 6),
                    "components_used": pop["signal_components"],
                    "indigen": {"status": ind["status"], "caf": ind.get("caf"), "signal": ind.get("signal")},
                    "gnomad_global": {"status": glo["status"], "caf": glo.get("caf"), "signal": glo.get("signal")},
                    "gnomad_south_asian": {"status": sas["status"], "caf": sas.get("caf"), "signal": sas.get("signal")},
                    "sas_vs_global": {"status": pop["sas_vs_global"]["status"], "log2_ratio": pop["sas_vs_global"].get("log2_ratio"),
                                      "signal": pop["sas_vs_global"].get("signal")},
                    "genes": pop["genes"],
                },
                "population_contribution": round(contrib, 6),
                "final_score": round(base + contrib, 6),
                "rank": fr, "baseline_rank": br, "rank_change": br - fr,
                # legacy keys consumed by Phase 4 / UI (None when no evidence; never a neutral placeholder)
                "indian_population_signal": ind.get("signal"), "global_population_signal": glo.get("signal"),
                "south_asian_population_signal": sas.get("signal"),     # gnomAD SAS, reported under its own name (not Indian data)
                "population_evidence_status": pop["status"],
                "matched_hpo_ids": c.get("matched_hpo_ids", []), "associated_phenotypes": c.get("associated_phenotypes", []),
                "associated_genes": c.get("associated_genes", []),
                "evidence_sources": [s for s in [c.get("source_db", "")] if s] + (["gnomAD"] if glo["status"] == "available" else []) + (["IndiGen"] if ind["status"] == "available" else []),
            })
        out.sort(key=lambda x: x["rank"])
        return out
