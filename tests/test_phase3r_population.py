"""Phase 3R tests.

IMPORTANT: objects named FIXTURE_* are tiny, hand-written, clearly artificial inputs used ONLY to test arithmetic
and state handling. They are never used as population evidence anywhere in the application.

Run: python -m unittest tests.test_phase3r_population -v
"""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(os.path.abspath("."))
CONFIG = "configs/config.yaml"

from src.population import indigen_adapter  # noqa: E402
from src.population.gnomad_adapter import is_plp, summarize_gene  # noqa: E402
from src.population.indigen_adapter import IndiGenStore, parse_vcf  # noqa: E402
from src.population.population_lookup import PopulationLookup, compare_frequencies  # noqa: E402
from src.population.variant_normalizer import normalize_variant, parse_variant_id, split_multiallelic  # noqa: E402
from src.ranking.disease_ranker import DiseaseRanker, _ranks  # noqa: E402
from src.ranking.population_prior import PopulationPriorEngine  # noqa: E402


def fixture_gene(symbol, plp):
    """FIXTURE gnomAD gene record. plp: list of (exome_ac, exome_an, sas_ac, sas_an)."""
    return {"input_gene": symbol, "status": "available", "normalized_gene": symbol, "dataset": "gnomad_r4", "clinvar_total": 10,
            "clinvar_plp": len(plp), "clinvar_plp_in_gnomad": len(plp),
            "plp_variants": [{"variant_id": f"1:{100 + i}:A:T", "exome": {"ac": a, "an": n, "sas_ac": sa, "sas_an": sn}, "genome": None}
                             for i, (a, n, sa, sn) in enumerate(plp)]}


def fixture_lookup(tmp, genes, min_n=3):
    for g in genes:
        Path(tmp, f"{g['input_gene']}.json").write_text(json.dumps(g))
    return PopulationLookup(CONFIG, cache_dir=tmp, min_reference_genes=min_n, indigen=IndiGenStore.__new__(IndiGenStore))


class _NoIndigen(IndiGenStore):
    def __init__(self):
        self.df, self.version = None, None


class TestVariantNormalization(unittest.TestCase):
    def test_prefix_case_and_format(self):
        self.assertEqual(normalize_variant("chr1", "100", "a", "t"), "1:100:A:T")
        self.assertEqual(normalize_variant("MT", 5, "A", "G"), "M:5:A:G")
        self.assertEqual(parse_variant_id("chr5-148063971-C-T"), "5:148063971:C:T")

    def test_invalid_is_none_not_guessed(self):
        self.assertIsNone(normalize_variant("1", 100, "A", "A"))
        self.assertIsNone(normalize_variant("99", 100, "A", "T"))
        self.assertIsNone(normalize_variant("1", "x", "A", "T"))
        self.assertIsNone(normalize_variant("1", 100, "A", "*"))

    def test_multiallelic_split(self):
        self.assertEqual(split_multiallelic("1", 100, "A", "G,T"), ["1:100:A:G", "1:100:A:T"])
        self.assertEqual(split_multiallelic("1", 100, "A", "G,*"), ["1:100:A:G", None])


class TestFrequencyComparison(unittest.TestCase):
    def test_missing_values_never_become_zero(self):
        c = compare_frequencies(None, 0.01)
        self.assertIsNone(c["difference"]); self.assertIsNone(c["ratio"])

    def test_zero_zero_is_undefined(self):
        c = compare_frequencies(0.0, 0.0)
        self.assertIsNone(c["ratio"]); self.assertIsNone(c["log2_ratio"])

    def test_ratio_and_log(self):
        c = compare_frequencies(0.02, 0.01)
        self.assertAlmostEqual(c["ratio"], 2.0); self.assertAlmostEqual(c["log2_ratio"], 1.0)

    def test_absent_in_indian_present_globally(self):
        self.assertEqual(compare_frequencies(0.0, 0.01)["ratio"], 0.0)


class TestIndiGenAdapter(unittest.TestCase):
    def test_unavailable_without_data_and_nothing_generated(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = yaml_cfg(d)
            res = indigen_adapter.ingest(cfg)
            self.assertEqual(res["status"], "unavailable")
            self.assertFalse(Path(d, "processed.parquet").exists())
        self.assertEqual(_NoIndigen().lookup_variant("1:100:A:T")["status"], "unavailable")

    def test_vcf_parsing_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "FIXTURE.vcf")
            p.write_text("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
                         "chr1\t100\t.\tA\tG,T\t.\t.\tAC=2,1;AN=100;AF=0.02,0.01\n")
            rows = list(parse_vcf(p))
            self.assertEqual([r["variant_id"] for r in rows], ["1:100:A:G", "1:100:A:T"])
            self.assertAlmostEqual(rows[1]["allele_frequency"], 0.01)


def yaml_cfg(tmpdir):
    import yaml
    cfg = yaml.safe_load(open(CONFIG, encoding="utf-8"))
    cfg["population"]["indigen_raw_dir"] = tmpdir
    cfg["population"]["indigen_processed_file"] = str(Path(tmpdir, "processed.parquet"))
    out = Path(tmpdir, "cfg.yaml")
    out.write_text(yaml.safe_dump(cfg))
    return str(out)


class TestGnomadSummary(unittest.TestCase):
    def test_plp_filter(self):
        self.assertTrue(is_plp("Pathogenic")); self.assertTrue(is_plp("Likely pathogenic"))
        self.assertFalse(is_plp("Uncertain significance")); self.assertFalse(is_plp("Conflicting classifications of pathogenicity"))

    def test_caf_arithmetic_fixture(self):
        s = summarize_gene(fixture_gene("FIXG", [(10, 1000, 1, 100), (0, 1000, 0, 100)]))
        self.assertAlmostEqual(s["caf_global"], 0.01)      # 10/1000 + 0/1000
        self.assertAlmostEqual(s["caf_sas"], 0.01)         # 1/100 + 0/100

    def test_zero_af_is_a_real_observation(self):
        s = summarize_gene(fixture_gene("FIXZ", [(0, 1000, 0, 100)]))
        self.assertEqual(s["caf_global"], 0.0); self.assertTrue(s["has_plp"])


class TestLookupStatesAndSignal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        genes = [fixture_gene(f"G{i}", [(i, 1000, 0, 100)]) for i in range(1, 6)]          # CAF 0.001 .. 0.005
        genes.append(fixture_gene("ZERO", [(0, 1000, 0, 100)]))                              # CAF 0
        genes.append({**fixture_gene("NOPLP", []), "clinvar_plp": 0})                        # no P/LP -> not_found
        genes.append({"input_gene": "BADGENE", "status": "not_found", "plp_variants": []})
        self.lk = PopulationLookup(CONFIG, cache_dir=self.tmp, min_reference_genes=3, indigen=_NoIndigen())
        for g in genes:
            Path(self.tmp, f"{g['input_gene']}.json").write_text(json.dumps(g))
        self.lk = PopulationLookup(CONFIG, cache_dir=self.tmp, min_reference_genes=3, indigen=_NoIndigen())
        self.eng = PopulationPriorEngine(CONFIG, lookup=self.lk)

    def test_states(self):
        self.assertEqual(self.lk.lookup_gene("G3")["gnomad"]["status"], "available")
        self.assertEqual(self.lk.lookup_gene("NOPLP")["gnomad"]["status"], "not_found")
        self.assertEqual(self.lk.lookup_gene("BADGENE")["gnomad"]["status"], "not_found")
        self.assertEqual(self.lk.lookup_gene("NEVER_INGESTED")["gnomad"]["status"], "unavailable")
        self.assertEqual(self.lk.lookup_gene("G3")["indigen"]["status"], "unavailable")

    def test_signal_is_ecdf_and_zero_af_is_zero(self):
        r = self.eng.compute_population_scores(["G3"])
        self.assertAlmostEqual(r["population_signal"], 3 / 5)             # 3 of 5 reference CAFs <= G3
        self.assertEqual(self.eng.compute_population_scores(["ZERO"])["population_signal"], 0.0)

    def test_missing_evidence_is_none_never_a_neutral_number(self):
        for genes in (["NEVER_INGESTED"], ["NOPLP"]):
            r = self.eng.compute_population_scores(genes)
            self.assertIsNone(r["population_signal"])
            self.assertIn(r["status"], ("unavailable", "not_found"))
        self.assertEqual(self.eng.compute_population_scores([])["status"], "not_applicable")

    def test_multi_gene_disease_sums_caf(self):
        r = self.eng.compute_population_scores(["G1", "G2"])
        self.assertAlmostEqual(r["gnomad_global"]["caf"], 0.003)

    def test_indian_component_unavailable_without_indigen(self):
        r = self.eng.compute_population_scores(["G3"], use_indigen=True, use_gnomad_global=True)
        self.assertEqual(r["indigen"]["status"], "unavailable"); self.assertIsNone(r["indigen"]["signal"])
        self.assertEqual(r["signal_components"], ["gnomad_global"])

    def test_signal_undefined_when_reference_too_small(self):
        lk = PopulationLookup(CONFIG, cache_dir=self.tmp, min_reference_genes=1000, indigen=_NoIndigen())
        self.assertIsNone(PopulationPriorEngine(CONFIG, lookup=lk).compute_population_scores(["G3"])["population_signal"])

    def test_coverage_summary(self):
        c = self.lk.coverage_summary(["G1", "NOPLP", "NEVER_INGESTED"])
        self.assertEqual((c["total_genes"], c["gnomad_available"], c["gnomad_not_found"], c["gnomad_unavailable_or_not_ingested"]), (3, 1, 1, 1))
        self.assertEqual(c["indigen_available"], 0)


class TestRanking(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        for i, caf in enumerate([1, 2, 3, 4, 5], 1):
            Path(tmp, f"G{i}.json").write_text(json.dumps(fixture_gene(f"G{i}", [(caf, 1000, 0, 100)])))
        lk = PopulationLookup(CONFIG, cache_dir=tmp, min_reference_genes=3, indigen=_NoIndigen())
        self.ranker = DiseaseRanker(CONFIG, weights={"w_phenotype": 0.5, "w_retrieval": 0.5, "w_population": 0.0},
                                    population_engine=PopulationPriorEngine(CONFIG, lookup=lk))
        # FIXTURE candidates: A leads on base score, B has the highest-population gene, C has no gene data
        self.cands = [
            {"disease_id": "A", "disease_name": "A", "hpo_match_score": 1.0, "retrieval_score_norm": 0.60, "associated_genes": ["G1"]},
            {"disease_id": "B", "disease_name": "B", "hpo_match_score": 1.0, "retrieval_score_norm": 0.58, "associated_genes": ["G5"]},
            {"disease_id": "C", "disease_name": "C", "hpo_match_score": 1.0, "retrieval_score_norm": 0.57, "associated_genes": []},
        ]

    def test_weight_normalisation_from_config(self):
        from src.ranking.disease_ranker import load_ranking_config
        w = load_ranking_config(CONFIG)
        self.assertAlmostEqual(w["w_phenotype"] + w["w_retrieval"], 1.0)

    def test_zero_population_weight_reproduces_base_ranking(self):
        out = self.ranker.rank_candidates(self.cands)
        self.assertEqual([c["disease_id"] for c in out], ["A", "B", "C"])
        self.assertTrue(all(c["population_contribution"] == 0.0 and c["rank_change"] == 0 for c in out))

    def test_population_moves_candidates_and_is_measurable(self):
        out = self.ranker.rank_candidates(self.cands, exp_config="rag_gnomad_global", weights={"w_population": 0.3})
        by = {c["disease_id"]: c for c in out}
        # G5 signal = 5/5 = 1.0 -> +0.3*(1.0-0.5) = +0.15 ; G1 signal = 1/5 -> -0.09 ; C has no evidence -> exactly 0
        self.assertAlmostEqual(by["B"]["population_contribution"], 0.15, places=5)
        self.assertAlmostEqual(by["A"]["population_contribution"], -0.09, places=5)
        self.assertEqual(by["C"]["population_contribution"], 0.0)
        self.assertEqual(by["B"]["rank"], 1); self.assertEqual(by["B"]["baseline_rank"], 2); self.assertEqual(by["B"]["rank_change"], 1)
        self.assertEqual(by["A"]["rank_change"], -2)

    def test_retrieval_and_phenotype_scores_unchanged_by_population(self):
        a = {c["disease_id"]: c for c in self.ranker.rank_candidates(self.cands)}
        b = {c["disease_id"]: c for c in self.ranker.rank_candidates(self.cands, weights={"w_population": 0.5})}
        for k in a:
            self.assertEqual(a[k]["retrieval_score"], b[k]["retrieval_score"])
            self.assertEqual(a[k]["phenotype_score"], b[k]["phenotype_score"])
            self.assertEqual(a[k]["base_score"], b[k]["base_score"])

    def test_missing_signal_adds_nothing_even_with_weight(self):
        out = {c["disease_id"]: c for c in self.ranker.rank_candidates(self.cands, weights={"w_population": 1.0})}
        self.assertEqual(out["C"]["population_contribution"], 0.0)
        self.assertIsNone(out["C"]["population"]["signal"])

    def test_rank_ties_are_stable(self):
        self.assertEqual(_ranks([0.5, 0.5, 0.4]), [1, 2, 3])

    def test_exp_config_rag_only_switches_population_off(self):
        out = self.ranker.rank_candidates(self.cands, exp_config="rag_only", weights={"w_population": 0.5})
        self.assertTrue(all(c["population"]["signal"] is None for c in out))


class TestNoSyntheticDataInProduction(unittest.TestCase):
    def test_no_random_generation_in_production_code(self):
        pat = re.compile(r"random\.(seed|uniform|randint|choice)|np\.random|RandomState")
        for d in ("src/population", "src/ranking", "src/pipeline"):
            for f in Path(d).glob("*.py"):
                for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                    self.assertIsNone(pat.search(line), f"{f}:{n}")

    def test_legacy_synthetic_not_imported(self):
        for f in Path("src").rglob("*.py"):
            if "_legacy_synthetic" in f.parts:
                continue
            self.assertNotIn("_legacy_synthetic", f.read_text(encoding="utf-8"), str(f))

    def test_synthetic_files_are_quarantined(self):
        self.assertFalse(Path("data/processed/indigen").exists())
        self.assertFalse(Path("data/processed/gnomad").exists())
        self.assertTrue(Path("data/processed/population/_legacy_synthetic/README.md").exists())


class TestReports(unittest.TestCase):
    def test_ablation_report_is_honest_about_blocked_configs(self):
        rep = json.load(open("reports/ranking_evaluation.json", encoding="utf-8"))
        lk = PopulationLookup(CONFIG)
        for variant, res in rep["test_results"].items():
            if not lk.indigen.available:
                self.assertIn("BLOCKED", res["D_plus_indigen"]["status"])
            m = res["A_retrieval_phenotype"]
            for k in ("Recall@1", "Recall@5", "Recall@10", "MRR"):
                self.assertTrue(0.0 <= m[k] <= 1.0)
        self.assertEqual(rep["n_test_queries"], 500)

    def test_validation_and_test_queries_are_disjoint(self):
        from src.evaluation.evaluate_retrieval import build_queries
        test_q, _, _ = build_queries(CONFIG)
        val_q, _, _ = build_queries(CONFIG, seed=11, n_queries=300, exclude_ids={q["disease_id"] for q in test_q})
        self.assertFalse({q["disease_id"] for q in test_q} & {q["disease_id"] for q in val_q})


if __name__ == "__main__":
    unittest.main()
