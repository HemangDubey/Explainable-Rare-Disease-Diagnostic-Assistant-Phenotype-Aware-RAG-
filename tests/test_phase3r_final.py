"""Phase 3R final tests: real-source schema, gnomAD global / South Asian extraction, A/B/C ablation consistency.

FIXTURE_* inputs are tiny hand-written examples used ONLY to test parsing/arithmetic; real-data tests read the
actual ingested files and FAIL if they are missing. Run: python -m unittest tests.test_phase3r_final -v
"""
import json
import math
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.append(os.path.abspath("."))
CONFIG = "configs/config.yaml"

from src.population.gnomad_bulk import gene_regions, parse_lines  # noqa: E402
from src.population.gnomad_adapter import summarize_gene  # noqa: E402
from src.population.population_lookup import PopulationLookup  # noqa: E402
from src.population.remote_tabix import _decode_blocks, _reg2bins  # noqa: E402
from src.ranking.disease_ranker import DiseaseRanker, EXPERIMENTS  # noqa: E402
from src.ranking.population_prior import PopulationPriorEngine  # noqa: E402
from tests.test_phase3r_population import _NoIndigen, fixture_gene  # noqa: E402

FIXTURE_VCF = [
    "chr1\t100\t.\tA\tG\t.\tPASS\tAC=12;AN=2000;AF=0.006;AC_sas=3;AN_sas=400;AF_sas=0.0075",
    "chr1\t200\t.\tC\tT,G\t.\tPASS\tAC=5,0;AN=1000;AC_sas=1,0;AN_sas=100",
    "chr1\t300\t.\tG\tA\t.\tAS_VQSR\tAC=7;AN=1000;AC_sas=0;AN_sas=100",
    "chr1\t400\t.\tT\tC\t.\tPASS\tAC=9;AN=900",                       # no South Asian fields at all
]


class TestVcfExtraction(unittest.TestCase):
    def test_global_and_south_asian_extraction(self):
        p = parse_lines(FIXTURE_VCF)
        v = p[(100, "A", "G")]
        self.assertEqual((v["ac"], v["an"], v["sas_ac"], v["sas_an"]), (12, 2000, 3, 400))

    def test_multiallelic_split_per_alt(self):
        p = parse_lines(FIXTURE_VCF)
        self.assertEqual(p[(200, "C", "T")]["ac"], 5); self.assertEqual(p[(200, "C", "G")]["ac"], 0)
        self.assertEqual(p[(200, "C", "T")]["sas_ac"], 1)

    def test_zero_frequency_is_recorded_as_zero(self):
        self.assertEqual(parse_lines(FIXTURE_VCF)[(200, "C", "G")]["ac"], 0)

    def test_missing_south_asian_stays_missing(self):
        v = parse_lines(FIXTURE_VCF)[(400, "T", "C")]
        self.assertIsNone(v["sas_ac"]); self.assertIsNone(v["sas_an"]); self.assertEqual(v["an"], 900)

    def test_filter_status_preserved(self):
        self.assertEqual(parse_lines(FIXTURE_VCF)[(300, "G", "A")]["filter"], "AS_VQSR")

    def test_missing_sas_variant_excluded_from_sas_caf_not_from_global(self):
        rec = {"input_gene": "FIX", "status": "available", "normalized_gene": "FIX", "dataset": "x", "clinvar_total": 3, "clinvar_plp": 2,
               "clinvar_plp_in_gnomad": 2, "plp_variants": [
                   {"variant_id": "1:100:A:G", "exome": {"ac": 10, "an": 1000, "sas_ac": 2, "sas_an": 100}, "genome": None},
                   {"variant_id": "1:400:T:C", "exome": {"ac": 9, "an": 900, "sas_ac": None, "sas_an": None}, "genome": None}]}
        s = summarize_gene(rec)
        self.assertAlmostEqual(s["caf_global"], 0.01 + 0.01)
        self.assertAlmostEqual(s["caf_sas"], 0.02); self.assertEqual(s["n_variants_sas"], 1)


class TestRegionsAndBgzf(unittest.TestCase):
    def test_gene_regions_cluster_by_gap(self):
        import pandas as pd
        df = pd.DataFrame({"variant_id": ["1:100:A:T", "1:150:A:T", "1:90000:A:T", "2:5:A:T"]})
        r = gene_regions(df, gap=1000)
        self.assertEqual(r["1"], [(100, 150), (90000, 90000)]); self.assertEqual(r["2"], [(5, 5)])

    def test_reg2bins_contains_root_and_leaf(self):
        b = _reg2bins(0, 1)
        self.assertIn(0, b); self.assertIn(4681, b)

    def test_bgzf_decode_roundtrip_fixture(self):
        def block(payload: bytes) -> bytes:
            c = zlib.compressobj(6, zlib.DEFLATED, -15); cdata = c.compress(payload) + c.flush()
            hdr = b"\x1f\x8b\x08\x04\x00\x00\x00\x00\x00\xff\x06\x00BC\x02\x00" + struct.pack("<H", len(cdata) + 25)
            return hdr + cdata + struct.pack("<II", zlib.crc32(payload), len(payload))
        data = b"junk" + block(b"hello\n") + block(b"world\n")
        out = _decode_blocks(data, 1000)
        self.assertEqual([b for _, b in out], [b"hello\n", b"world\n"]); self.assertEqual(out[0][0], 1004)


class TestRealSourceData(unittest.TestCase):
    """These read the REAL ingested files."""

    def test_clinvar_table_schema_and_provenance(self):
        import pandas as pd
        df = pd.read_parquet("data/processed/population/clinvar_plp_grch38.parquet")
        for c in ("variant_id", "gene", "clinical_significance", "review_status", "gold_stars", "variation_id"):
            self.assertIn(c, df.columns)
        self.assertTrue(df["clinical_significance"].isin(["Pathogenic", "Likely pathogenic", "Pathogenic/Likely pathogenic"]).all())
        self.assertTrue((df["gold_stars"] >= 1).all())
        self.assertTrue(df["variant_id"].str.match(r"^[0-9XYM]+:\d+:[ACGTN]+:[ACGTN]+$").all())   # real ClinVar has large insertions with N placeholders
        prov = json.load(open("data/processed/population/clinvar_provenance.json"))
        self.assertEqual(prov["filters"]["assembly"], "GRCh38"); self.assertGreater(prov["rows_in_file"], 1_000_000)

    def test_gene_records_have_real_variant_level_counts(self):
        cache = Path("data/raw/gnomad/gene_cache")
        files = list(cache.glob("*.json"))
        self.assertGreater(len(files), 40)
        seen = 0
        for f in files:
            r = json.load(open(f, encoding="utf-8"))
            for v in r.get("plp_variants", []):
                seen += 1
                self.assertRegex(v["variant_id"], r"^[0-9XY]+:\d+:[ACGT]+:[ACGT]+$")
                ex = v["exome"]
                self.assertTrue(ex["an"] and ex["an"] > 0 and 0 <= ex["ac"] <= ex["an"])
                if ex["sas_an"]:
                    self.assertTrue(0 <= ex["sas_ac"] <= ex["sas_an"])
                self.assertIn("clinvar_variation_id", v)
            self.assertIn("v4.1", r["dataset"]) if r["status"] == "available" else None
        self.assertGreater(seen, 100)

    def test_vcf_counts_agree_with_independent_gnomad_api(self):
        rep = json.load(open("reports/population_crosscheck_vcf_vs_api.json"))
        self.assertGreater(rep["variants_compared"], 200)
        self.assertEqual(rep["mismatches"], 0)

    def test_provenance_report(self):
        p = json.load(open("reports/population_data_provenance.json"))
        names = {d["source"] for d in p["datasets"]}
        self.assertTrue(any("gnomAD" in n for n in names)); self.assertTrue(any("ClinVar" in n for n in names))
        ind = next(d for d in p["datasets"] if "IndiGen" in d["source"])
        self.assertIn("UNAVAILABLE", ind["status"]); self.assertEqual(ind["records"], 0)
        gn = next(d for d in p["datasets"] if d["source"].startswith("gnomAD"))
        for k in ("source_version", "access_mechanism", "filtering_rules", "license_terms_status", "processing_script", "genome_build", "retrieval_date_utc", "record_count"):
            self.assertIn(k, gn)

    def test_coverage_report_consistency(self):
        c = json.load(open("reports/population_coverage.json"))
        self.assertLessEqual(c["genes_with_gnomad_south_asian_evidence"], c["genes_with_gnomad_global_evidence"])
        self.assertLessEqual(c["genes_with_gnomad_global_evidence"], c["total_disease_associated_genes"])
        self.assertEqual(c["genes_with_indigen_data"], 0)
        self.assertIn("UNAVAILABLE", c["indigen_status"])
        self.assertAlmostEqual(c["gnomad_global_coverage_pct"], 100 * c["genes_with_gnomad_global_evidence"] / c["total_disease_associated_genes"], places=1)


class TestSouthAsianComparison(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # FIXTURE genes: global CAF = i*0.001; South-Asian CAF alternates above/below
        for i in range(1, 9):
            ac, sas = i, (2 * i if i % 2 else max(i // 2, 1))
            Path(self.tmp, f"G{i}.json").write_text(json.dumps(fixture_gene(f"G{i}", [(ac, 1000, sas, 1000)])))
        Path(self.tmp, "ZSAS.json").write_text(json.dumps(fixture_gene("ZSAS", [(5, 1000, 0, 1000)])))   # SAS CAF = 0
        self.lk = PopulationLookup(CONFIG, cache_dir=self.tmp, min_reference_genes=3, indigen=_NoIndigen())
        self.eng = PopulationPriorEngine(CONFIG, lookup=self.lk)

    def test_log2_ratio(self):
        r = self.eng.compute_population_scores(["G1"], use_gnomad_sas=True, use_sas_vs_global=True)
        self.assertAlmostEqual(r["sas_vs_global"]["log2_ratio"], math.log2(0.002 / 0.001))
        self.assertEqual(r["status"], "available")

    def test_zero_sas_makes_ratio_undefined_not_zero(self):
        r = self.eng.compute_population_scores(["ZSAS"], use_gnomad_sas=True, use_sas_vs_global=True)
        self.assertIsNone(r["sas_vs_global"]["log2_ratio"]); self.assertIsNone(r["sas_vs_global"]["signal"])
        self.assertEqual(r["gnomad_sas"]["caf"], 0.0)       # observed zero, kept as zero

    def test_components_are_labelled_south_asian_not_indian(self):
        r = self.eng.compute_population_scores(["G1"], use_indigen=False, use_gnomad_global=False, use_gnomad_sas=True, use_sas_vs_global=False)
        self.assertEqual(r["signal_components"], ["gnomad_sas"])
        self.assertEqual(r["indigen"]["status"], "unavailable")

    def test_ablation_configs_share_candidates_and_scores(self):
        ranker = DiseaseRanker(CONFIG, weights={"w_phenotype": 0.3, "w_retrieval": 0.7, "w_population": 0.4}, population_engine=self.eng)
        cands = [{"disease_id": f"D{i}", "disease_name": f"D{i}", "hpo_match_score": 1.0, "retrieval_score_norm": 0.6 - 0.01 * i,
                  "associated_genes": [f"G{i}"]} for i in range(1, 8)]                          # FIXTURE candidates
        a = ranker.rank_candidates(cands, exp_config="rag_only")
        b = ranker.rank_candidates(cands, exp_config="rag_south_asian")
        c = ranker.rank_candidates(cands, exp_config="rag_south_asian_global")
        self.assertEqual({x["disease_id"] for x in a}, {x["disease_id"] for x in b}, "candidate set must not change")
        for cfg in (a, b, c):
            self.assertEqual({x["disease_id"]: x["retrieval_score"] for x in cfg}, {x["disease_id"]: x["retrieval_score"] for x in a})
            self.assertEqual({x["disease_id"]: x["base_score"] for x in cfg}, {x["disease_id"]: x["base_score"] for x in a})
        self.assertTrue(all(x["population_contribution"] == 0 and x["rank_change"] == 0 for x in a))
        self.assertTrue(any(x["population_contribution"] != 0 for x in b))
        for x in b:
            self.assertEqual(x["baseline_rank"] - x["rank"], x["rank_change"])

    def test_indigen_experiment_never_falls_back_to_south_asian(self):
        self.assertTrue(EXPERIMENTS["rag_indigen"]["use_indigen"])
        self.assertFalse(EXPERIMENTS["rag_indigen"]["use_gnomad_sas"])
        ranker = DiseaseRanker(CONFIG, weights={"w_population": 0.5}, population_engine=self.eng)
        out = ranker.rank_candidates([{"disease_id": "D", "hpo_match_score": 1, "retrieval_score_norm": 0.5, "associated_genes": ["G1"]}], exp_config="rag_indigen")
        self.assertIsNone(out[0]["population"]["signal"]); self.assertEqual(out[0]["population_contribution"], 0.0)


class TestEvaluationReport(unittest.TestCase):
    def test_report_structure_and_blocked_indigen(self):
        rep = json.load(open("reports/ranking_evaluation.json"))
        for variant, res in rep["test_results"].items():
            self.assertIn("A_retrieval_phenotype", res)
            self.assertIn("BLOCKED", res["D_plus_indigen"]["status"])
            for k in ("B_plus_south_asian", "C_plus_south_asian_and_global_comparison"):
                self.assertIn(k, res)
        self.assertEqual(rep["n_test_queries"], 500)
        w = rep["frozen_phenotype_retrieval_weights"]
        self.assertAlmostEqual(w["w_phenotype"] + w["w_retrieval"], 1.0)

    def test_population_weight_zero_when_coverage_insufficient(self):
        rep = json.load(open("reports/ranking_evaluation.json"))
        for name, w in rep["chosen_population_weights"].items():
            note = rep["weight_notes"][name]
            if w == 0.0 and "could not be reliably estimated" in note:
                self.assertIn("w_population = 0", note)


if __name__ == "__main__":
    unittest.main()
