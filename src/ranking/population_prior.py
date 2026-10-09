"""Population evidence for a candidate disease (real data only; no neutral placeholders).

Statistic (per gene): cumulative allele frequency CAF(g) = sum over ClinVar pathogenic/likely-pathogenic
variants v of gene g of AF(v). For a disease with associated genes G with data, CAF(D) = sum_g CAF(g)
(each causal allele counts once; genes are treated as alternative causes).

Signal: s(D) = F(CAF(D)), where F is the empirical CDF of CAF over the ingested reference genes with CAF > 0,
and F(0) = 0. s is in [0, 1]; it is undefined (None) when the reference has < MIN_REFERENCE_GENES genes.
Components: IndiGen (Indian), gnomAD global baseline, gnomAD South-Asian ancestry group (optional).
population_signal = mean of the enabled components that are available; None if none is.

INTERPRETATION: a larger signal means pathogenic alleles for the disease's genes are more frequent in that
population. It is evidence about occurrence, not a disease probability and not a diagnosis.
"""
from typing import List, Optional

import yaml

from src.population.population_lookup import PopulationLookup, compare_frequencies
from src.population.population_schema import AVAILABLE, NOT_APPLICABLE, NOT_FOUND, UNAVAILABLE


class PopulationPriorEngine:
    def __init__(self, config_path="configs/config.yaml", lookup: Optional[PopulationLookup] = None):
        cfg = yaml.safe_load(open(config_path, encoding="utf-8"))["population"]
        self.use_indigen = bool(cfg.get("use_indigen", True))
        self.use_global = bool(cfg.get("use_gnomad_global", True))
        self.use_sas = bool(cfg.get("use_gnomad_sas", False))
        self.use_enrich = bool(cfg.get("use_sas_vs_global", False))
        self.lookup = lookup or PopulationLookup(config_path)

    @staticmethod
    def _component(gene_infos, source_key, caf_key, cdf):
        vals, states = [], []
        for gi in gene_infos:
            ev = gi[source_key]
            states.append(ev["status"])
            if ev["status"] == AVAILABLE:
                vals.append(ev[caf_key])
        if vals:
            caf = float(sum(vals))
            return {"status": AVAILABLE, "caf": caf, "signal": cdf(caf), "genes_with_data": len(vals), "genes_total": len(gene_infos)}
        status = NOT_FOUND if states and all(s == NOT_FOUND for s in states) else UNAVAILABLE
        return {"status": status, "caf": None, "signal": None, "genes_with_data": 0, "genes_total": len(gene_infos)}

    def compute_population_scores(self, associated_genes: List[str], use_indigen=None, use_gnomad_global=None, use_gnomad_sas=None,
                                  use_sas_vs_global=None):
        use_i = self.use_indigen if use_indigen is None else use_indigen
        use_g = self.use_global if use_gnomad_global is None else use_gnomad_global
        use_s = self.use_sas if use_gnomad_sas is None else use_gnomad_sas
        use_e = self.use_enrich if use_sas_vs_global is None else use_sas_vs_global
        genes = [g for g in (associated_genes or []) if g]
        if not genes:
            return {"status": NOT_APPLICABLE, "level": "GENE_LEVEL", "population_signal": None, "signal_components": [],
                    "indigen": {"status": NOT_APPLICABLE}, "gnomad_global": {"status": NOT_APPLICABLE},
                    "gnomad_sas": {"status": NOT_APPLICABLE}, "sas_vs_global": {"status": NOT_APPLICABLE}, "genes": []}
        infos = [self.lookup.lookup_gene(g) for g in genes]
        lk = self.lookup
        ind = self._component(infos, "indigen", "caf", lk.cdf_indigen)
        glo = self._component(infos, "gnomad", "caf_global", lk.cdf_global)
        sas = self._component(infos, "gnomad", "caf_sas", lk.cdf_sas)
        # South-Asian vs global comparison: log2(CAF_sas / CAF_global); undefined (not zero) unless both are > 0
        enr = {"status": UNAVAILABLE, "caf": None, "signal": None, "log2_ratio": None}
        if glo["status"] == AVAILABLE and sas["status"] == AVAILABLE:
            if glo["caf"] > 0 and sas["caf"] > 0:
                import math
                lr = math.log2(sas["caf"] / glo["caf"])
                enr = {"status": AVAILABLE, "caf": None, "log2_ratio": lr, "signal": lk.cdf_enrich(lr)}
            else:
                enr = {"status": UNAVAILABLE, "caf": None, "signal": None, "log2_ratio": None,
                       "reason": "ratio undefined: a frequency is zero (0 observed carriers)"}
        used = []
        sigs = []
        for name, comp, enabled in (("indigen", ind, use_i), ("gnomad_global", glo, use_g), ("gnomad_sas", sas, use_s),
                                    ("sas_vs_global", enr, use_e)):
            if enabled and comp["status"] == AVAILABLE and comp["signal"] is not None:
                used.append(name); sigs.append(comp["signal"])
        signal = sum(sigs) / len(sigs) if sigs else None
        enabled_comps = [c for c, en in ((ind, use_i), (glo, use_g), (sas, use_s), (enr, use_e)) if en]
        if signal is not None:
            status = AVAILABLE
        elif any(c["status"] == AVAILABLE for c in enabled_comps):
            status = UNAVAILABLE            # data exists but the reference distribution is too small for a signal
        elif enabled_comps and all(c["status"] == NOT_FOUND for c in enabled_comps):
            status = NOT_FOUND
        else:
            status = UNAVAILABLE
        return {
            "status": status, "level": "GENE_LEVEL", "population_signal": signal, "signal_components": used,
            "indigen": ind, "gnomad_global": glo, "gnomad_sas": sas, "sas_vs_global": enr,
            "indian_vs_global": compare_frequencies(ind["caf"], glo["caf"]),
            "genes": [{k: gi.get(k) for k in ("input_gene", "normalized_gene", "mapping_source", "mapping_status")}
                      | {"gnomad_status": gi["gnomad"]["status"], "indigen_status": gi["indigen"]["status"]} for gi in infos],
        }
