"""Phase 3R: population ingestion status -> weight tuning (validation) -> ablation (test) -> reports.

    python -m src.population.population_ingestion --max-genes N   # real gnomAD API ingestion (slow, rate limited)
    python scripts/run_phase3.py
IndiGen requires access from CSIR-IGIB; place the export in data/raw/indigen/ and run src/population/indigen_adapter.py.
"""
import os
import sys

sys.path.append(os.path.abspath("."))
from src.evaluation.evaluate_ranking import evaluate
from src.population.indigen_adapter import ingest as ingest_indigen

if __name__ == "__main__":
    print("IndiGen:", ingest_indigen())
    rep = evaluate()
    print("coverage:", rep["population_coverage"])
