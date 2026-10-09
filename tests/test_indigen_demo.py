"""IndiGen DEMO (synthetic) integration: dataset, provider, isolation from real sources and ranking, API, report and UI labels.

The demo dataset is synthetic by design (scripts/build_indigen_demo.py). These tests check that it is labelled everywhere, only shown
on request, never written into real-source caches, never read by the ranking, and that real ClinVar / gnomAD results are unchanged.
"""
import copy
import gzip
import hashlib
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.append(os.path.abspath("."))
from tests.helpers_auth import authed_client, use_temp_database  # noqa: E402

use_temp_database()
from src.population.gene_evidence import GeneEvidenceService  # noqa: E402
from src.population.indigen_demo import DEMO_LABEL, DEMO_PATH, IndiGenDemoProvider, demo_allowed  # noqa: E402
from src.population.population_lookup import PopulationLookup  # noqa: E402

THREE = ["SLC26A4", "PAX8", "TSHR"]
CACHE = Path("data/raw/gnomad/gene_cache")
PLP = pd.read_parquet("data/processed/population/clinvar_plp_grch38.parquet", columns=["variant_id", "gene", "variation_id"])
_LK = None


def lookup():
    global _LK
    if _LK is None:
        _LK = PopulationLookup()
    return _LK


def strip_demo(ev):
    ev = copy.deepcopy(ev)
    ev.pop("indigen_demo", None)
    ev["population_comparison"].pop("demo_column", None)
    for v in ev["population_comparison"]["variants"]:
        v.pop("af_indigen_demo", None)
    return ev


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class TestDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(DEMO_PATH, "rt", encoding="utf-8") as f:
            cls.d = json.load(f)

    def test_location_is_isolated(self):
        p = str(DEMO_PATH).replace("\\", "/")
        self.assertTrue(p.startswith("data/demo/"))
        for real in ("data/raw/indigen", "data/processed/population", "data/raw/gnomad"):
            self.assertFalse(p.startswith(real))

    def test_provenance_says_synthetic(self):
        pv = self.d["provenance"]
        self.assertTrue(pv["synthetic"])
        self.assertEqual(pv["label"], DEMO_LABEL)
        self.assertIn("NOT measured from Indian genomes", pv["statement"])
        self.assertIn("NOT obtained from CSIR-IGIB", pv["statement"])
        self.assertIn("disease ranking", pv["must_not_be_used_for"])
        self.assertEqual(self.d["schema_version"], "indigen-demo/1")
        self.assertEqual(self.d["n_records"], sum(g["n_variants"] for g in self.d["genes"].values()))

    def test_supported_genes_and_real_identifiers(self):
        for g in THREE:
            self.assertIn(g, self.d["genes"])
            ids = {v["variant_id"] for v in self.d["genes"][g]["variants"]}
            real = set(PLP[PLP.gene == g].variant_id)
            self.assertEqual(ids, real, g)                                  # every real ClinVar P/LP id, nothing invented

    def test_deterministic(self):
        from scripts.build_indigen_demo import SEED, simulate
        self.assertEqual(self.d["provenance"]["seed"], SEED)
        for g in THREE:
            for v in self.d["genes"][g]["variants"][:50]:
                self.assertEqual(simulate(v["variant_id"]), {k: v[k] for k in ("demo_ac", "demo_an", "demo_af")})
            self.assertAlmostEqual(self.d["genes"][g]["demo_caf"], sum(v["demo_af"] for v in self.d["genes"][g]["variants"]))

    def test_values_not_copied_from_gnomad(self):
        rec = json.load(open(CACHE / "TSHR.json", encoding="utf-8"))
        demo = {v["variant_id"]: v for v in self.d["genes"]["TSHR"]["variants"]}
        same = sum(1 for v in rec["plp_variants"] if v["exome"]["sas_an"] and v["exome"]["sas_ac"] > 0
                   and abs(demo[v["variant_id"]]["demo_af"] - v["exome"]["sas_ac"] / v["exome"]["sas_an"]) < 1e-12)
        self.assertEqual(same, 0)


class TestProvider(unittest.TestCase):
    def test_gene_switching(self):
        pr = IndiGenDemoProvider()
        seen = {}
        for g in THREE:
            r = pr.gene(g)
            self.assertEqual(r["status"], "available")
            self.assertEqual(r["label"], DEMO_LABEL)
            self.assertTrue(r["synthetic"])
            seen[g] = {v["variant_id"] for v in r["variants"]}
        self.assertTrue(seen["PAX8"].isdisjoint(seen["TSHR"]))
        self.assertEqual(pr.gene("pax8")["n_variants"], len(seen["PAX8"]))
        self.assertEqual(pr.gene("NOTAGENE")["status"], "not_found")

    def test_missing_and_invalid_files(self):
        self.assertEqual(IndiGenDemoProvider(Path(tempfile.mkdtemp()) / "none.json.gz").gene("PAX8")["status"], "unavailable")
        bad = Path(tempfile.mkdtemp()) / "bad.json.gz"
        with gzip.open(bad, "wt", encoding="utf-8") as f:
            json.dump({"schema_version": "indigen-demo/1", "provenance": {"synthetic": False}, "genes": {}}, f)
        self.assertEqual(IndiGenDemoProvider(bad).status()["status"], "error")    # refuses a file not marked synthetic

    def test_demo_allowed_switch(self):
        with mock.patch.dict(os.environ, {"INDIGEN_DEMO_ALLOWED": "0"}):
            self.assertFalse(demo_allowed())
        with mock.patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            os.environ.pop("INDIGEN_DEMO_ALLOWED", None)
            self.assertFalse(demo_allowed())
        with mock.patch.dict(os.environ, {"APP_ENV": "production", "INDIGEN_DEMO_ALLOWED": "1"}):
            self.assertTrue(demo_allowed())


class TestServiceIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc = GeneEvidenceService(lookup())

    def test_real_fields_unchanged_by_demo(self):
        before = {g: sha(CACHE / f"{g}.json") for g in THREE}
        for g in THREE:
            real = self.svc.evidence(g)
            demo = self.svc.evidence(g, indigen_demo=True)
            self.assertNotIn("indigen_demo", real)
            self.assertEqual(strip_demo(demo), real, g)
            self.assertEqual(demo["indigen"]["status"], "unavailable")             # the REAL IndiGen field never carries demo values
            self.assertNotIn("cumulative_af", demo["indigen"])
            self.assertEqual(demo["indigen_demo"]["status"], "available")
            self.assertEqual(demo["indigen_demo"]["label"], DEMO_LABEL)
            self.assertEqual(demo["population_comparison"]["demo_column"]["label"], "IndiGen Demo (synthetic)")
            self.assertEqual(demo["population_comparison"]["columns"][2]["status"], "unavailable")
            self.assertEqual(demo["patient_variant"]["status"], "not_provided")
        self.assertEqual(before, {g: sha(CACHE / f"{g}.json") for g in THREE})     # real caches untouched
        self.assertFalse(lookup().indigen.available)                               # the lookup feeding ranking never sees the demo
        self.assertFalse(any("demo" in json.dumps(lookup().lookup_gene(g)).lower() for g in THREE))

    def test_comparison_demo_values_come_from_demo_file(self):
        ev = self.svc.evidence("PAX8", indigen_demo=True)
        by = {v["variant_id"]: v["demo_af"] for v in IndiGenDemoProvider().gene("PAX8")["variants"]}
        for v in ev["population_comparison"]["variants"]:
            self.assertEqual(v["af_indigen_demo"], by[v["variant_id"]])
        self.assertAlmostEqual(ev["population_comparison"]["demo_column"]["cumulative_af"], IndiGenDemoProvider().gene("PAX8")["cumulative_af"])

    def test_disabled_and_superseded(self):
        with mock.patch.dict(os.environ, {"INDIGEN_DEMO_ALLOWED": "0"}):
            self.assertEqual(self.svc.evidence("PAX8", indigen_demo=True)["indigen_demo"]["status"], "disabled")
        ev = self.svc.evidence("PAX8")
        ev["indigen"] = {"status": "available", "cumulative_af": 0.001}               # as if an authorised export were loaded
        out = self.svc._attach_demo(ev)
        self.assertEqual(out["indigen_demo"]["status"], "superseded_by_real_data")
        self.assertNotIn("demo_column", out["population_comparison"])

    def test_missing_demo_file_breaks_nothing(self):
        svc = GeneEvidenceService(lookup(), demo_provider=IndiGenDemoProvider(Path(tempfile.mkdtemp()) / "x.json.gz"))
        ev = svc.evidence("TSHR", indigen_demo=True)
        self.assertEqual(ev["indigen_demo"]["status"], "unavailable")
        self.assertEqual(ev["clinvar"]["status"], "available")
        self.assertEqual(ev["gnomad_global"]["status"], "available")

    def test_ranking_code_never_reads_the_demo(self):
        for root in ("src/ranking", "src/pipeline", "src/reasoning", "src/counterfactual", "src/evaluation"):
            for f in Path(root).rglob("*.py"):
                self.assertNotIn("indigen_demo", f.read_text(encoding="utf-8"), str(f))
        for f in ("src/population/population_lookup.py", "src/population/indigen_adapter.py", "src/population/gnomad_bulk.py",
                  "scripts/ingest_population.py"):
            self.assertNotIn("indigen_demo", Path(f).read_text(encoding="utf-8"), f)


class TestApi(unittest.TestCase):
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
        r = cls.c.post("/api/diagnose", json={"clinical_text": "Synthetic case. Infant with congenital hypothyroidism, thyroid hypoplasia "
                                                              "and elevated TSH.", "top_k": 5})
        assert r.status_code == 200, r.text
        cls.diag = r.json()
        cls.case_id = cls.diag["case_id"]

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def setUp(self):
        self.main._hits.clear()

    def test_auth_required(self):
        from fastapi.testclient import TestClient
        anon = TestClient(self.main.app, raise_server_exceptions=False)
        for path in ("/api/genomic/indigen-demo/status", "/api/genomic/indigen-demo/genes?symbols=PAX8", "/api/genomic/gene/PAX8?indigen_demo=true"):
            self.assertEqual(anon.get(path).status_code, 401, path)

    def test_status_and_gene_routes(self):
        st = self.c.get("/api/genomic/indigen-demo/status").json()
        self.assertTrue(st["allowed"])
        self.assertFalse(st["real_indigen_available"])
        self.assertEqual(st["demo"]["status"], "available")
        g = self.c.get("/api/genomic/indigen-demo/genes?symbols=PAX8,TSHR,SLC26A4").json()
        self.assertEqual(g["label"], DEMO_LABEL)
        self.assertTrue(all(v["status"] == "available" for v in g["genes"].values()))
        a = self.c.get("/api/genomic/gene/PAX8").json()
        b = self.c.get("/api/genomic/gene/PAX8?indigen_demo=true").json()
        self.assertEqual(strip_demo(b), a)

    def test_twin_and_panel_use_the_same_provider(self):
        tw = self.c.get(f"/api/twin/{self.case_id}?indigen_demo=true").json()
        plain = self.c.get(f"/api/twin/{self.case_id}").json()
        self.assertIn(DEMO_LABEL, [s["source"] for s in tw["genomic"]["sources"]])
        self.assertNotIn(DEMO_LABEL, [s["source"] for s in plain["genomic"]["sources"]])
        for g in tw["genomic"]["genes"]:
            self.assertEqual(g, self.c.get(f"/api/genomic/gene/{g['gene']}?indigen_demo=true").json(), g["gene"])
        self.assertEqual([strip_demo(g) for g in tw["genomic"]["genes"]], plain["genomic"]["genes"])
        self.assertEqual(tw["candidates"], plain["candidates"])

    def test_ranking_unaffected(self):
        for c in self.diag["fused_candidates"]:
            self.assertEqual(c.get("population_contribution", 0.0), 0.0)
            self.assertIsNone(c.get("indian_population_signal"))
        rw = self.main.ranking_pipeline.disease_ranker.weights
        self.assertEqual((rw["w_phenotype"], rw["w_retrieval"], rw["w_population"]), (0.2, 0.8, 0.0))
        r = self.c.post("/api/diagnose", json={"clinical_text": "Synthetic case. Infant with congenital hypothyroidism, thyroid hypoplasia "
                                                              "and elevated TSH.", "top_k": 5}).json()
        self.assertEqual([(c["disease_id"], c["final_score"]) for c in r["fused_candidates"]],
                         [(c["disease_id"], c["final_score"]) for c in self.diag["fused_candidates"]])

    def test_report_appendix_and_export_labels(self):
        plain = self.c.post("/api/report/generate", json={"case_id": self.case_id}).json()
        self.assertIsNone(plain.get("appendix_indigen_demo"))
        rep = self.c.post("/api/report/generate", json={"case_id": self.case_id, "include_indigen_demo": True}).json()
        app = rep["appendix_indigen_demo"]
        self.assertEqual(app["label"], DEMO_LABEL)
        self.assertTrue(app["synthetic"])
        self.assertEqual(app["status"], "available")
        self.assertTrue(app["genes"])
        self.assertEqual(rep["section_5_indian_population_context"]["indigen_gnomad_comparison"]["indigen"], "unavailable")
        self.assertEqual([c["final_score"] for c in rep["section_3_top_differentials"]],
                         [c["final_score"] for c in plain["section_3_top_differentials"]])
        html = self.c.get(f"/api/report/{rep['header']['report_id']}/export").text
        self.assertIn(DEMO_LABEL.replace("—", "&mdash;") if "&mdash;" in html else DEMO_LABEL, html)
        self.assertNotIn(DEMO_LABEL, self.c.get(f"/api/report/{plain['header']['report_id']}/export").text)


class TestFrontend(unittest.TestCase):
    def read(self, rel):
        return Path("frontend/src", rel).read_text(encoding="utf-8")

    def test_label_and_wiring(self):
        demo = self.read("components/twin/indigenDemo.jsx")
        self.assertIn("IndiGen Demo — Synthetic Data, Not Official IndiGen Evidence", demo)
        panel = self.read("components/twin/GenomicPanel.jsx")
        for s in ("DemoBanner", "DemoToggle", "getGeneEvidence(gene, { demo: true })", "af_indigen_demo", "demo_column", "onRetry={() => fetchDemo(g.gene)}"):
            self.assertIn(s, panel)
        self.assertIn("getIndigenDemoGenes", self.read("components/EvidenceCards.jsx"))
        rv = self.read("components/ReportGeneratorView.jsx")
        self.assertIn("include_indigen_demo: demo.enabled", rv)
        self.assertIn("appendix_indigen_demo", rv)
        self.assertIn("localStorage", demo)
        self.assertNotRegex(panel + demo, r"0\.0\d{3,}")                # no typed frequencies


if __name__ == "__main__":
    unittest.main()
