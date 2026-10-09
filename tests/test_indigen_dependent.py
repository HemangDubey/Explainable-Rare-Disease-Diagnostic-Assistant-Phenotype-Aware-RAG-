"""IndiGen-dependent features: provenance, missing-data behaviour, the authorised-data path, no substitution, API responses and
protection of the clinical ranking.

No IndiGen data exist on this machine, so the "authorised export" tests build a tiny TEMPORARY TSV in a temp directory (synthetic,
clearly test-only, never written under data/). It exercises the real ingest -> store -> lookup -> twin path and is then discarded.
"""
import copy
import json
import math
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.append(os.path.abspath("."))
from tests.helpers_auth import authed_client, use_temp_database  # noqa: E402

use_temp_database()
from src.population.indigen_adapter import IndiGenStore, ingest  # noqa: E402
from src.population.population_lookup import PopulationLookup  # noqa: E402
from src.ranking.explanation import generate_ranking_explanation  # noqa: E402
from src.twin.builder import _gene_evidence, population_comparison, population_sources  # noqa: E402

CFG = "configs/config.yaml"
GENE_CACHE = Path("data/raw/gnomad/gene_cache")
GENE = "GJB2"


def temp_config(tmp, raw_dir=None):
    cfg = yaml.safe_load(open(CFG, encoding="utf-8"))
    cfg["population"]["indigen_raw_dir"] = str(raw_dir or Path(tmp) / "indigen_raw").replace("\\", "/")
    cfg["population"]["indigen_processed_file"] = str(Path(tmp) / "processed" / "indigen_variants.parquet").replace("\\", "/")
    p = Path(tmp) / "config.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return str(p)


class TestRealDataState(unittest.TestCase):
    """What is actually on this machine."""

    def test_no_indigen_export_is_present(self):
        cfg = yaml.safe_load(open(CFG, encoding="utf-8"))["population"]
        raw = Path(cfg["indigen_raw_dir"])
        files = [p for p in raw.glob("*") if p.suffix in (".vcf", ".gz", ".tsv", ".txt")] if raw.exists() else []
        self.assertEqual(files, [], "an IndiGen export appeared: re-run the ingest and update the report")
        self.assertFalse(Path(cfg["indigen_processed_file"]).exists())
        self.assertFalse(IndiGenStore(CFG).available)

    def test_ranking_weights_frozen(self):
        w = yaml.safe_load(open(CFG, encoding="utf-8"))["ranking"]
        self.assertEqual((w["w_phenotype"], w["w_retrieval"], w["w_population"]), (0.2, 0.8, 0.0))


class TestMissingIndiGen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="indigen_missing_")
        cls.cfg = temp_config(cls.tmp)
        cls.lk = PopulationLookup(cls.cfg)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_ingest_without_files_reports_unavailable(self):
        r = ingest(self.cfg)
        self.assertEqual(r["status"], "unavailable")
        self.assertIn("no data is generated", r["reason"])

    def test_gene_lookup_marks_indigen_unavailable_with_reason(self):
        info = self.lk.lookup_gene(GENE)
        self.assertEqual(info["gnomad"]["status"], "available")
        self.assertEqual(info["indigen"]["status"], "unavailable")
        self.assertIn("access required", info["indigen"]["reason"])
        self.assertNotIn("caf", info["indigen"])

    def test_twin_gene_evidence_never_substitutes_south_asian(self):
        g = _gene_evidence(GENE, lambda s: self.lk.genes[s]["rec"], self.lk.lookup_gene)
        self.assertEqual(g["gnomad_south_asian"]["status"], "available")
        self.assertIsNotNone(g["gnomad_south_asian"]["cumulative_af"])
        self.assertEqual(g["indigen"]["status"], "unavailable")
        self.assertNotIn("cumulative_af", g["indigen"])
        self.assertIn("never shown as IndiGen", g["indigen"]["substitution"])
        pc = g["population_comparison"]
        cols = {c["label"]: c for c in pc["columns"]}
        self.assertEqual(list(cols), ["gnomAD Global", "gnomAD South Asian", "IndiGen"])
        self.assertIsNone(cols["IndiGen"]["cumulative_af"])
        self.assertEqual(cols["IndiGen"]["status"], "unavailable")
        self.assertEqual(cols["gnomAD South Asian"]["cumulative_af"], g["gnomad_south_asian"]["cumulative_af"])
        self.assertEqual(pc["status"], "available")                     # global + South Asian still give a working comparison
        self.assertIn("not a substitute for IndiGen", pc["note"])

    def test_comparison_values_match_the_cache(self):
        rec = json.load(open(GENE_CACHE / f"{GENE}.json", encoding="utf-8"))
        g = _gene_evidence(GENE, lambda s: rec, self.lk.lookup_gene)
        by_id = {v["variant_id"]: v for v in rec["plp_variants"]}
        for v in g["population_comparison"]["variants"]:
            ex = by_id[v["variant_id"]]["exome"]
            self.assertAlmostEqual(v["af_global"], ex["ac"] / ex["an"])
            self.assertEqual(v["af_south_asian"], (ex["sas_ac"] / ex["sas_an"]) if ex["sas_an"] else None)
            if v["af_global"] and v["af_south_asian"]:
                self.assertAlmostEqual(v["log2_sas_vs_global"], math.log2(v["af_south_asian"] / v["af_global"]))
            else:
                self.assertIsNone(v["log2_sas_vs_global"])

    def test_gene_without_any_data(self):
        g = _gene_evidence("NOTAGENE1", None, None)
        pc = g["population_comparison"]
        self.assertEqual(pc["status"], "unavailable")
        self.assertTrue(all(c["cumulative_af"] is None for c in pc["columns"]))
        self.assertEqual(pc["variants"], [])

    def test_sources_provenance(self):
        src = {s["source"]: s for s in population_sources(True, False)}
        self.assertEqual(set(src), {"ClinVar", "gnomAD Global", "gnomAD South Asian", "IndiGen"})
        self.assertEqual(src["IndiGen"]["status"], "unavailable")
        self.assertIn("clingen.igib.res.in/indigen", src["IndiGen"]["provenance"])
        self.assertIn("not India-specific", src["gnomAD South Asian"]["role"])
        self.assertEqual(population_sources(False)[0]["status"], "unavailable")


class TestAuthorisedExportPath(unittest.TestCase):
    """If an authorised IndiGen export is supplied, the existing adapter ingests it and every consumer shows it as IndiGen."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="indigen_export_")
        raw = Path(cls.tmp) / "indigen_raw"
        raw.mkdir()
        rec = json.load(open(GENE_CACHE / f"{GENE}.json", encoding="utf-8"))
        cls.vids = [v["variant_id"] for v in rec["plp_variants"][:2]]
        rows = ["chrom\tpos\tref\talt\tAC\tAN"]
        for i, vid in enumerate(cls.vids):                         # TEST-ONLY counts; this file lives in a temp dir and is deleted
            c, p, r, a = vid.split(":")
            rows.append(f"{c}\t{p}\t{r}\t{a}\t{i + 1}\t2000")
        (raw / "test_only_export.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        cls.cfg = temp_config(cls.tmp, raw)
        try:
            cls.prov = ingest(cls.cfg)
        except Exception as e:                                       # e.g. parquet engine blocked by the OS
            raise unittest.SkipTest(f"ingest unavailable in this environment: {type(e).__name__}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_ingest_records_provenance(self):
        self.assertEqual(self.prov["status"], "available")
        self.assertEqual(self.prov["records"], 2)
        self.assertEqual(self.prov["file"], "test_only_export.tsv")
        self.assertTrue((Path(self.tmp) / "processed" / "indigen_provenance.json").exists())

    def test_store_and_gene_lookup(self):
        store = IndiGenStore(self.cfg)
        self.assertTrue(store.available)
        r = store.lookup_variant(self.vids[0])
        self.assertEqual((r["status"], r["allele_count"], r["allele_number"]), ("available", 1, 2000))
        self.assertEqual(store.lookup_variant("1:1:A:C")["status"], "not_found")
        lk = PopulationLookup(self.cfg, indigen=store)
        ind = lk.lookup_gene(GENE)["indigen"]
        self.assertEqual(ind["status"], "available")
        self.assertAlmostEqual(ind["caf"], 1 / 2000 + 2 / 2000)
        self.assertEqual(ind["n_variants_found"], 2)
        g = _gene_evidence(GENE, lambda s: lk.genes[s]["rec"], lk.lookup_gene)
        self.assertEqual(g["indigen"]["status"], "available")
        self.assertAlmostEqual(g["indigen"]["cumulative_af"], 3 / 2000)
        cols = {c["label"]: c for c in g["population_comparison"]["columns"]}
        self.assertAlmostEqual(cols["IndiGen"]["cumulative_af"], 3 / 2000)
        self.assertNotEqual(cols["IndiGen"]["cumulative_af"], cols["gnomAD South Asian"]["cumulative_af"])
        self.assertEqual(lk.lookup_gene("HBB")["indigen"]["status"], "not_found")   # gene with no variant in the export


class TestExplanationWording(unittest.TestCase):
    def test_sources_named_separately(self):
        txt = generate_ranking_explanation({"disease_name": "D", "disease_id": "X:1", "global_population_signal": 0.4,
                                            "south_asian_population_signal": 0.7, "indian_population_signal": None,
                                            "population_evidence_status": "available", "associated_genes": ["G"]})
        line = next(l for l in txt.split("\n") if "Population Evidence" in l)
        self.assertIn("gnomAD global: 0.400", line)
        self.assertIn("gnomAD South Asian (not India-specific): 0.700", line)
        self.assertIn("IndiGen: unavailable", line)
        self.assertNotRegex(line, r"(?i)indian")


class TestReportGenerator(unittest.TestCase):
    def test_indigen_status_is_data_driven(self):
        from src.reporting.report_generator import _indigen_status, _pop_note
        base = {"disease_name": "D", "genes": ["G"], "population": {"status": "available", "gnomad_south_asian": {"caf": 0.002},
                                                                     "gnomad_global": {"caf": 0.001}, "indigen": {"status": "unavailable"}}}
        self.assertEqual(_indigen_status([base]), "unavailable")
        self.assertEqual(_indigen_status([]), "unavailable")
        note = _pop_note(base)
        self.assertIn("South Asian 0.002, global 0.001", note)
        self.assertNotIn("IndiGen", note)                             # never a value for a missing source
        with_ind = copy.deepcopy(base)
        with_ind["population"]["indigen"] = {"status": "available", "caf": 0.004}
        self.assertEqual(_indigen_status([base, with_ind]), "available")
        self.assertIn("IndiGen 0.004", _pop_note(with_ind))


class TestApiAndRankingProtection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from src.api import main
        cls.main = main
        cls._ctx = TestClient(main.app, raise_server_exceptions=False)
        cls.c = cls._ctx.__enter__()
        if main.retrieval_pipeline is None:
            raise unittest.SkipTest("pipeline not loaded")
        cls.user = authed_client(cls.c)
        r = cls.c.post("/api/diagnose", json={"clinical_text": "Synthetic case. Child with hepatomegaly, recurrent seizures, hypotonia and "
                                                              "sensorineural hearing loss.", "top_k": 5})
        assert r.status_code == 200, r.text
        cls.diag = r.json()
        cls.case_id = cls.diag["case_id"]

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def test_twin_genomic_payload(self):
        tw = self.c.get(f"/api/twin/{self.case_id}").json()
        gen = tw["genomic"]
        src = {s["source"]: s["status"] for s in gen["sources"]}
        self.assertEqual(src["IndiGen"], "unavailable")
        self.assertEqual(src["gnomAD South Asian"], "available")
        self.assertTrue(gen["genes"], "synthetic case should produce candidate genes")
        for g in gen["genes"]:
            self.assertEqual(g["patient_variant"]["status"], "not_provided")
            self.assertEqual(g["indigen"]["status"], "unavailable")
            self.assertIn(g["population_comparison"]["status"], ("available", "partial", "unavailable"))
            self.assertIsNone(g["population_comparison"]["columns"][2]["cumulative_af"])
        self.assertTrue(any(g["population_comparison"]["status"] == "available" for g in gen["genes"]))

    def test_diagnosis_population_fields(self):
        cov = self.diag.get("population_coverage") or {}
        self.assertEqual(cov.get("indigen_available"), 0)
        self.assertNotEqual(cov.get("indigen_dataset"), "available")
        for c in self.diag["fused_candidates"]:
            self.assertEqual(c.get("population_contribution", 0.0), 0.0)
            self.assertIsNone(c.get("indian_population_signal"))
            self.assertAlmostEqual(c["final_score"], round(0.2 * c["phenotype_score"] + 0.8 * c["retrieval_score"], 6), places=5)

    def test_injected_indigen_store_cannot_change_ranking(self):
        """Even if an IndiGen store (here: test-only values) were loaded, w_population = 0 keeps every score and rank identical."""
        rp = self.main.ranking_pipeline
        lk = rp.disease_ranker.pop.lookup
        terms = self.main.repo.get_case(self.user["user"]["id"], self.case_id)["hpo_terms"]
        before = rp.run_from_hpo_terms(copy.deepcopy(terms), top_k_disease=10, exp_config="rag_indigen")["ranked_candidates"]

        class FakeStore:                                       # every variant gets a large, obviously fake frequency
            available, version = True, "TEST-ONLY"

            def lookup_variant(self, vid):
                return {"source": "IndiGen", "status": "available", "allele_frequency": 0.25}
        real = lk.indigen
        try:
            lk.indigen = FakeStore()
            lk.reload()
            self.assertGreater(len(lk.indigen_caf), 0)
            after = rp.run_from_hpo_terms(copy.deepcopy(terms), top_k_disease=10, exp_config="rag_indigen")["ranked_candidates"]
        finally:
            lk.indigen = real
            lk.reload()
        self.assertFalse(lk.indigen.available)
        self.assertEqual([c["disease_id"] for c in before], [c["disease_id"] for c in after])
        self.assertEqual([c["final_score"] for c in before], [c["final_score"] for c in after])
        self.assertTrue(all(c["population_contribution"] == 0 for c in after))


LEGACY_CLAIMS = [r"IndiGen Prior", r"IndiGen Allele Prior", r"1,029 genomes", r"1,068 variants", r"Indian Population Priors",
                 r"IndiGen \(1,029", r"COMPLETED & INTEGRATED", r"Calibrated against whole-genome"]


class TestNoFalseIndiGenClaims(unittest.TestCase):
    FILES = [p for p in Path("frontend/src").rglob("*.jsx")] + [Path("README.md"), Path("scripts/generate_pdf1_walkthrough.py"),
                                                                 Path("scripts/generate_pdf2_demo_guide.py")]

    def test_no_legacy_claims(self):
        for f in self.FILES:
            txt = f.read_text(encoding="utf-8")
            for pat in LEGACY_CLAIMS:
                self.assertIsNone(re.search(pat, txt, re.I), f"{f}: {pat}")

    def test_research_section_has_no_typed_frequencies(self):
        src = Path("frontend/src/components/ResearchSection.jsx").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"0\.0\d{3,}", src), "allele frequencies must come from the generated data file")
        self.assertIn("/data/population_showcase.json", src)

    def test_showcase_file_matches_the_real_cache(self):
        d = json.load(open("frontend/public/data/population_showcase.json", encoding="utf-8"))
        self.assertIn("unavailable", d["sources"]["indigen"])
        self.assertTrue(d["rows"])
        for r in d["rows"]:
            if r["status"] != "available":
                continue
            rec = json.load(open(GENE_CACHE / f"{r['gene']}.json", encoding="utf-8"))
            v = next(x for x in rec["plp_variants"] if x["variant_id"] == r["variant_id"])
            ex = v["exome"]
            self.assertAlmostEqual(r["gnomad_global"]["af"], ex["ac"] / ex["an"])
            self.assertAlmostEqual(r["gnomad_south_asian"]["af"], ex["sas_ac"] / ex["sas_an"])
            self.assertEqual(r["indigen"]["status"], "unavailable")
            self.assertNotIn("af", r["indigen"])

    def test_twin_panel_labels(self):
        src = Path("frontend/src/components/twin/GenomicPanel.jsx").read_text(encoding="utf-8")
        self.assertIn("Population comparison", src)
        self.assertIn("No value is substituted", src)
        self.assertNotRegex(src, r"(?i)\bindian\b")

    def test_legacy_synthetic_isolated(self):
        for root in ("src", "scripts"):
            for f in Path(root).rglob("*.py"):
                if "_legacy_synthetic" in f.parts or f.name == "build_population_reports.py":
                    continue
                txt = f.read_text(encoding="utf-8")
                self.assertNotRegex(txt, r"(from|import)\s+[\w.]*_legacy_synthetic", str(f))
                self.assertNotIn("_legacy_synthetic/", txt, str(f))


if __name__ == "__main__":
    unittest.main()
