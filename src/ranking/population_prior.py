import os
import json
import yaml
import numpy as np
import pandas as pd
from pathlib import Path

class PopulationPriorEngine:
    def __init__(self, config_path="configs/config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        ind_path = Path(self.config["population"]["indigen_processed_dir"]) / self.config["population"]["indigen_file"]
        gno_path = Path(self.config["population"]["gnomad_processed_dir"]) / self.config["population"]["gnomad_file"]

        self.indigen_map = {}
        self.gnomad_map = {}

        if ind_path.exists():
            try: df_ind = pd.read_parquet(ind_path)
            except Exception: df_ind = pd.read_csv(Path(self.config["population"]["indigen_processed_dir"]) / "indigen_frequency.csv")
            for _, r in df_ind.iterrows():
                gene = str(r["gene"]).upper().strip()
                if gene not in self.indigen_map: self.indigen_map[gene] = []
                self.indigen_map[gene].append(float(r["allele_frequency"]))

        if gno_path.exists():
            try: df_gno = pd.read_parquet(gno_path)
            except Exception: df_gno = pd.read_csv(Path(self.config["population"]["gnomad_processed_dir"]) / "gnomad_frequency.csv")
            for _, r in df_gno.iterrows():
                gene = str(r["gene"]).upper().strip()
                if gene not in self.gnomad_map: self.gnomad_map[gene] = []
                self.gnomad_map[gene].append({"global_af": float(r["global_af"]), "sas_af": float(r["south_asian_af"])})

        self._document_scoring_method()

    def _document_scoring_method(self):
        reports_dir = Path(self.config["dataset"]["reports_dir"])
        reports_dir.mkdir(parents=True, exist_ok=True)
        doc_path = reports_dir / "population_scoring_method.md"
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write("""# Population Prior Scoring Method

## Scientific Rationale & Interpretation Rule
Population frequency alone is **NOT** a direct measure of disease causality or probability. In rare disease diagnostics, population allele frequency serves as a population-aware prior signal to calibrate candidate disease prioritization across specific ancestry backgrounds (e.g. Indian population genomes).

## Mathematical Transformation
For a candidate disease $D$ with associated genes $G = \{g_1, g_2, \\dots, g_m\}$:

1. **Missing Data Neutral Baseline**:
   If no variant frequency data is available for any associated gene ($G \\cap \\text{IndiGen} = \\emptyset$), the engine sets:
   $$\\text{status} = \\text{'unavailable' / 'not\\_found'}$$
   $$\\text{indian\\_population\\_signal} = 0.50$$
   $$\\text{global\\_population\\_signal} = 0.50$$
   *This ensures that missing population records never penalize or unfairly boost a candidate disease.*

2. **Population Enrichment Signal**:
   When variant frequencies are present, average IndiGen frequency $\\text{AF}_{\\text{IND}}$ and gnomAD global frequency $\\text{AF}_{\\text{GLOBAL}}$ are evaluated:
   $$\\text{raw\\_enrichment} = \\log_{10}\\left(1 + \\frac{\\text{AF}_{\\text{IND}} + 10^{-7}}{\\text{AF}_{\\text{GLOBAL}} + 10^{-7}}\\right)$$

3. **Bounded Sigmoid Normalization**:
   To ensure stability and interpretability in $[0.0, 1.0]$:
   $$\\text{indian\\_population\\_signal} = \\frac{1}{1 + e^{-2.0 \\cdot (\\text{raw\\_enrichment} - 0.30)}}$$
   - Neutral baseline / equal frequencies: $\\approx 0.50$
   - High relative population prevalence: $> 0.50$ to $1.0$
   - Depleted relative population prevalence: $< 0.50$
""")

    def compute_population_scores(self, associated_genes, use_indigen=True, use_gnomad=True):
        if not associated_genes:
            return {
                "indian_population_signal": 0.50,
                "global_population_signal": 0.50,
                "population_evidence_status": "unavailable",
                "evidence_sources": []
            }

        ind_afs = []
        gno_afs = []
        sources = []

        for gene in associated_genes:
            g_clean = str(gene).upper().strip()
            if use_indigen and g_clean in self.indigen_map:
                ind_afs.extend(self.indigen_map[g_clean])
                if "IndiGen" not in sources: sources.append("IndiGen")
            if use_gnomad and g_clean in self.gnomad_map:
                gno_afs.extend([v["global_af"] for v in self.gnomad_map[g_clean]])
                if "gnomAD" not in sources: sources.append("gnomAD")

        if not ind_afs and not gno_afs:
            return {
                "indian_population_signal": 0.50,
                "global_population_signal": 0.50,
                "population_evidence_status": "not_found",
                "evidence_sources": []
            }

        eps = 1e-7
        avg_ind = float(np.mean(ind_afs)) if ind_afs else 0.001
        avg_gno = float(np.mean(gno_afs)) if gno_afs else 0.001

        if use_indigen and ind_afs:
            raw_enr = np.log10(1.0 + (avg_ind + eps) / (avg_gno + eps))
            ind_signal = float(round(1.0 / (1.0 + np.exp(-2.0 * (raw_enr - 0.30))), 4))
        else:
            ind_signal = 0.50

        if use_gnomad and gno_afs:
            gno_signal = float(round(min(1.0, max(0.0, 0.50 + np.log10(1.0 + avg_gno * 100) * 0.2)), 4))
        else:
            gno_signal = 0.50

        return {
            "indian_population_signal": ind_signal,
            "global_population_signal": gno_signal,
            "population_evidence_status": "available",
            "evidence_sources": sources
        }

if __name__ == "__main__":
    engine = PopulationPriorEngine()
    print(engine.compute_population_scores(["OTUD7A", "UBE4A"]))
    print(engine.compute_population_scores(["UNKNOWN_GENE"]))
