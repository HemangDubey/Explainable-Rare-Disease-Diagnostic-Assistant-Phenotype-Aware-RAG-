"""Genomic evidence panel repair: gene lookup, ingestion, cache coverage, source states, API contract and twin consistency.

Real data: the ClinVar P/LP parquet and the gnomAD v4.1 per-gene cache (SLC26A4, PAX8, TSHR were ingested from the official public
VCFs by `scripts/ingest_population.py --genes SLC26A4,PAX8,TSHR`). Ingestion-mechanics tests use a temp cache directory and an
injected fetch function so they are deterministic and offline; one optional live test fetches a small real gene into a temp dir.
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import pandas as pd
import yaml

sys.path.append(os.path.abspath("."))
from tests.helpers_auth import authed_client, use_temp_database  # noqa: E402

use_temp_database()
from src.population.gene_evidence import GeneEvidenceService  # noqa: E402
from src.population.population_lookup import PopulationLookup  # noqa: E402

CACHE = Path("data/raw/gnomad/gene_cache")
PLP = pd.read_parquet("data/processed/population/clinvar_plp_grch38.parquet")
THREE = ["SLC26A4", "PAX8", "TSHR"]
_LK = None


def lookup():
    global _LK
    if _LK is None:
        _LK = PopulationLookup()
    return _LK


class TestThreeGenesRealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc = GeneEvidenceService(lookup())

    def test_cache_files_exist_and_are_real_records(self):
        for g in THREE:
            rec = json.load(open(CACHE / f"{g}.json", encoding="utf-8"))
            self.assertEqual(rec["status"], "available", g)
            self.assertEqual(rec["dataset"], "gnomad_v4.1_exomes")
            self.assertEqual(rec["reference_genome"], "GRCh38")
            self.assertTrue(rec["fetched_at"])
            self.assertEqual(rec["clinvar_plp"], PLP[PLP.gene == g].variant_id.nunique())
            self.assertGreater(rec["clinvar_plp_in_gnomad"], 0)

    def test_all_sources_for_three_genes(self):
        for g in THREE:
            ev = self.svc.evidence(g)
            n = PLP[PLP.gene == g].variant_id.nunique()
            self.assertEqual(ev["clinvar"]["status"], "available", g)
            self.assertEqual(ev["clinvar"]["clinvar_plp_variants"], n)      # full ClinVar list, not only gnomAD-observed variants
            self.assertEqual(ev["clinvar"]["variants_shown"], min(n, 25))
            for k in ("gnomad_global", "gnomad_south_asian"):
                self.assertEqual(ev[k]["status"], "available", (g, k))
                self.assertEqual(ev[k]["release"], "gnomAD v4.1")
                self.assertEqual(ev[k]["reference_genome"], "GRCh38")
                self.assertTrue(ev[k]["retrieved_at"])
            self.assertEqual(ev["indigen"]["status"], "unavailable")
            self.assertNotIn("cumulative_af", ev["indigen"])
            self.assertEqual(ev["patient_variant"]["status"], "not_provided")
            self.assertEqual(ev["population_comparison"]["status"], "available")

    def test_variant_rows_match_sources(self):
        rec = json.load(open(CACHE / "TSHR.json", encoding="utf-8"))
        by = {v["variant_id"]: v for v in rec["plp_variants"]}
        ev = self.svc.evidence("TSHR")
        for v in ev["clinvar"]["variants"]:
            row = PLP[(PLP.gene == "TSHR") & (PLP.variant_id == v["variant_id"])].iloc[0]
            self.assertEqual(v["clinical_significance"], row.clinical_significance)
            self.assertEqual(v["gold_stars"], int(row.gold_stars))
            self.assertEqual(v["clinvar_url"], f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{row.variation_id}/")
            self.assertEqual(f"{v['chrom']}:{v['pos']}:{v['ref']}:{v['alt']}", v["variant_id"])
            if v["variant_id"] in by:
                ex = by[v["variant_id"]]["exome"]
                self.assertTrue(v["in_gnomad"])
                self.assertAlmostEqual(v["af_global"], ex["ac"] / ex["an"])
                self.assertEqual((v["ac_global"], v["an_global"]), (ex["ac"], ex["an"]))
                self.assertEqual((v["ac_south_asian"], v["an_south_asian"]), (ex["sas_ac"], ex["sas_an"]))   # separate SAS fields
                self.assertEqual(v["af_south_asian"], ex["sas_ac"] / ex["sas_an"] if ex["sas_an"] else None)
            else:
                self.assertFalse(v["in_gnomad"])
                self.assertIsNone(v["af_global"])
        stars = [v["gold_stars"] for v in ev["clinvar"]["variants"]]
        self.assertEqual(stars, sorted(stars, reverse=True))

    def test_global_and_south_asian_not_mixed(self):
        ev = self.svc.evidence("SLC26A4")
        s = lookup().genes["SLC26A4"]["sum"]
        self.assertAlmostEqual(ev["gnomad_global"]["cumulative_af"], s["caf_global"])
        self.assertAlmostEqual(ev["gnomad_south_asian"]["cumulative_af"], s["caf_sas"])
        self.assertNotEqual(ev["gnomad_global"]["cumulative_af"], ev["gnomad_south_asian"]["cumulative_af"])
        self.assertIn("not an India-specific", ev["gnomad_south_asian"]["note"])
        self.assertNotIn("India", ev["gnomad_global"].get("note", ""))


class TestSymbolResolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc = GeneEvidenceService(lookup())

    def test_case_and_whitespace(self):
        r = self.svc.resolve("  pax8 ")
        self.assertEqual((r["symbol"], r["status"]), ("PAX8", "case_normalised"))
        self.assertEqual(self.svc.resolve("TSHR")["status"], "mapped")

    def test_alias_via_ncbi_gene_id(self):
        svc = GeneEvidenceService(lookup())
        gid = svc._kb_gene_id["SLC26A4"]                                   # real NCBI GeneID from HPO phenotype_to_genes
        self.assertEqual(svc._by_gene_id[gid], "SLC26A4")                  # ...which ClinVar maps back to the same symbol
        svc._kb_gene_id["PDS"] = gid                                       # PDS: the historical name of SLC26A4
        r = svc.resolve("PDS")
        self.assertEqual((r["symbol"], r["status"]), ("SLC26A4", "alias_resolved"))
        self.assertIn(gid, r["via"])

    def test_gene_without_plp_records_is_empty_not_pending(self):
        sym = next(g for g in self.svc.totals if g not in self.svc._rows and not (CACHE / f"{g}.json").exists())
        ev = self.svc.evidence(sym)                                        # ClinVar knows the gene, but has no qualifying P/LP record
        self.assertEqual(ev["resolution"]["status"], "mapped")
        self.assertEqual(ev["clinvar"]["status"], "not_found")
        self.assertEqual(ev["gnomad_global"]["status"], "not_found")
        self.assertEqual(ev["gnomad_south_asian"]["status"], "not_found")

    def test_unknown_gene_is_a_real_empty_result(self):
        ev = self.svc.evidence("SNORD116-1")                               # in the knowledge base, no ClinVar GRCh38 record
        self.assertEqual(ev["resolution"]["status"], "not_found")
        self.assertEqual(ev["clinvar"]["status"], "not_found")
        self.assertEqual(ev["gnomad_global"]["status"], "not_found")
        self.assertEqual(ev["indigen"]["status"], "unavailable")


def _fake_record(gene, plp_gene, total, seen):
    rows = plp_gene.drop_duplicates("variant_id").head(2)
    return {"input_gene": gene, "dataset": "gnomad_v4.1_exomes", "reference_genome": "GRCh38", "source": "test", "status": "available",
            "fetched_at": "2026-01-01T00:00:00+00:00", "normalized_gene": gene, "clinvar_total": total,
            "clinvar_plp": int(plp_gene["variant_id"].nunique()), "non_pass_variants": 0,
            "plp_variants": [{"variant_id": r.variant_id, "clinical_significance": r.clinical_significance, "review_status": r.review_status,
                              "gold_stars": int(r.gold_stars), "clinvar_variation_id": r.variation_id,
                              "exome": {"ac": 3, "an": 1000, "sas_ac": 1, "sas_an": 100}, "genome": None} for r in rows.itertuples()],
            "clinvar_plp_in_gnomad": len(rows)}


class TestIngestionMechanics(unittest.TestCase):
    """Offline: temp cache + injected fetch. Proves idempotency, force, error handling and that errors are never cached as empty."""

    def make(self, fetch):
        tmp = tempfile.mkdtemp(prefix="gene_cache_")
        lk = PopulationLookup(cache_dir=tmp)
        return GeneEvidenceService(lk, cache_dir=tmp, fetch=fetch), Path(tmp)

    def test_not_ingested_then_ingested_then_cached(self):
        calls = []
        svc, tmp = self.make(lambda *a: calls.append(a[0]) or _fake_record(*a))
        self.assertEqual(svc.evidence("PAX8")["gnomad_global"]["status"], "not_ingested")
        self.assertEqual(svc.evidence("PAX8")["clinvar"]["status"], "available")     # ClinVar does not wait for gnomAD
        self.assertEqual(svc.ingest("PAX8")["status"], "ingested")
        self.assertTrue((tmp / "PAX8.json").exists())
        self.assertFalse(any(tmp.glob("*.tmp")))
        self.assertEqual(svc.ingest("pax8")["status"], "cached")
        self.assertEqual(calls, ["PAX8"])
        self.assertEqual(svc.ingest("PAX8", force=True)["status"], "ingested")
        self.assertEqual(calls, ["PAX8", "PAX8"])
        ev = svc.evidence("PAX8")
        self.assertEqual(ev["gnomad_global"]["status"], "available")
        self.assertAlmostEqual(ev["gnomad_global"]["cumulative_af"], 2 * 3 / 1000)
        self.assertAlmostEqual(ev["gnomad_south_asian"]["cumulative_af"], 2 * 1 / 100)

    def test_error_is_reported_retryable_and_not_cached(self):
        state = {"fail": True}

        def fetch(*a):
            if state["fail"]:
                raise ConnectionError("network down")
            return _fake_record(*a)
        svc, tmp = self.make(fetch)
        r = svc.ingest("TSHR")
        self.assertEqual(r["status"], "error")
        self.assertIn("ConnectionError", r["reason"])
        self.assertFalse((tmp / "TSHR.json").exists())
        ev = svc.evidence("TSHR")
        self.assertEqual(ev["gnomad_global"]["status"], "error")
        self.assertEqual(ev["clinvar"]["status"], "available")              # one failing source does not blank the panel
        state["fail"] = False
        self.assertEqual(svc.ingest("TSHR")["status"], "ingested")
        self.assertEqual(svc.evidence("TSHR")["gnomad_global"]["status"], "available")

    def test_fetch_returning_error_status(self):
        svc, tmp = self.make(lambda *a: {"status": "error", "reason": "HTTPError: 503"})
        self.assertEqual(svc.ingest("PAX8")["status"], "error")
        self.assertFalse((tmp / "PAX8.json").exists())

    def test_unknown_gene_makes_no_network_call(self):
        calls = []
        svc, _ = self.make(lambda *a: calls.append(a) or _fake_record(*a))
        self.assertEqual(svc.ingest("NOT-A-GENE-XYZ")["status"], "not_found")
        self.assertEqual(calls, [])

    def test_concurrent_requests_fetch_once(self):
        calls = []

        def slow(*a):
            calls.append(a[0]); time.sleep(0.3); return _fake_record(*a)
        svc, _ = self.make(slow)
        out = []
        ts = [threading.Thread(target=lambda: out.append(svc.ingest("PAX8")["status"])) for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(calls), 1)
        self.assertEqual(sorted(out), ["cached", "cached", "cached", "ingested"])

    def test_cli_written_file_is_picked_up_without_restart(self):
        svc, tmp = self.make(lambda *a: _fake_record(*a))
        self.assertEqual(svc.evidence("PAX8")["gnomad_global"]["status"], "not_ingested")
        rec = _fake_record("PAX8", PLP[PLP.gene == "PAX8"], 299, True)
        (tmp / "PAX8.json").write_text(json.dumps(rec), encoding="utf-8")
        self.assertEqual(svc.evidence("PAX8")["gnomad_global"]["status"], "available")


@unittest.skipIf(os.environ.get("NO_NETWORK"), "network disabled")
class TestLiveFetch(unittest.TestCase):
    def test_small_real_gene_from_official_gnomad(self):
        cached = {p.stem for p in CACHE.glob("*.json")}
        sizes = PLP.groupby("gene").variant_id.nunique()
        gene = next(g for g, n in sizes.sort_values().items()
                    if n >= 2 and g not in cached and PLP[PLP.gene == g].variant_id.str[:2].isin(["1:", "2:"]).all())
        tmp = tempfile.mkdtemp(prefix="gene_live_")
        svc = GeneEvidenceService(PopulationLookup(cache_dir=tmp), cache_dir=tmp)
        r = svc.ingest(gene)
        if r["status"] == "error":
            self.skipTest(f"gnomAD not reachable: {r['reason']}")
        self.assertEqual(r["status"], "ingested")
        rec = json.load(open(Path(tmp) / f"{gene}.json", encoding="utf-8"))
        self.assertEqual(rec["dataset"], "gnomad_v4.1_exomes")
        self.assertEqual(rec["clinvar_plp"], sizes[gene])
        self.assertIn(svc.evidence(gene)["gnomad_global"]["status"], ("available", "not_found"))


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

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def setUp(self):
        self.main._hits.clear()

    def test_requires_auth(self):
        from fastapi.testclient import TestClient
        anon = TestClient(self.main.app, raise_server_exceptions=False)
        self.assertEqual(anon.get("/api/genomic/gene/PAX8").status_code, 401)
        self.assertEqual(anon.post("/api/genomic/gene/PAX8/ingest").status_code, 401)

    def test_gene_endpoint_three_genes(self):
        for g in THREE + ["slc26a4"]:
            r = self.c.get(f"/api/genomic/gene/{g}")
            self.assertEqual(r.status_code, 200, r.text)
            ev = r.json()
            self.assertEqual(ev["clinvar"]["status"], "available")
            self.assertEqual(ev["gnomad_global"]["status"], "available")
            self.assertEqual(ev["indigen"]["status"], "unavailable")

    def test_ingest_endpoint_cached_and_not_found(self):
        r = self.c.post("/api/genomic/gene/TSHR/ingest").json()
        self.assertEqual(r["ingest"]["status"], "cached")
        self.assertEqual(r["evidence"]["gnomad_south_asian"]["status"], "available")
        r = self.c.post("/api/genomic/gene/SNORD116-1/ingest").json()
        self.assertEqual(r["ingest"]["status"], "not_found")
        self.assertEqual(r["evidence"]["clinvar"]["status"], "not_found")

    def test_invalid_symbol(self):
        self.assertEqual(self.c.get("/api/genomic/gene/%3Cscript%3E").status_code, 422)
        self.assertEqual(self.c.get("/api/genomic/gene/" + "A" * 40).status_code, 422)

    def test_twin_and_gene_api_share_one_contract(self):
        r = self.c.post("/api/diagnose", json={"clinical_text": "Synthetic case. Congenital hypothyroidism with goitre and bilateral "
                                                               "sensorineural hearing loss; enlarged vestibular aqueduct on imaging.", "top_k": 5})
        self.assertEqual(r.status_code, 200, r.text)
        cid = r.json()["case_id"]
        tw = self.c.get(f"/api/twin/{cid}").json()
        self.assertTrue(tw["genomic"]["genes"])
        for g in tw["genomic"]["genes"]:
            self.assertEqual(g, self.c.get(f"/api/genomic/gene/{g['gene']}").json(), g["gene"])
            self.assertEqual(g["patient_variant"]["status"], "not_provided")
        from fastapi.testclient import TestClient
        other = TestClient(self.main.app, raise_server_exceptions=False)
        authed_client(other)
        self.assertEqual(other.get(f"/api/twin/{cid}").status_code, 404)      # case isolation unchanged

    def test_ranking_weights_unchanged(self):
        w = yaml.safe_load(open("configs/config.yaml", encoding="utf-8"))["ranking"]
        self.assertEqual((w["w_phenotype"], w["w_retrieval"], w["w_population"]), (0.2, 0.8, 0.0))
        rw = self.main.ranking_pipeline.disease_ranker.weights
        self.assertEqual((rw["w_phenotype"], rw["w_retrieval"], rw["w_population"]), (0.2, 0.8, 0.0))


class TestFrontendStatic(unittest.TestCase):
    def test_panel_uses_backend_and_has_states(self):
        src = Path("frontend/src/components/twin/GenomicPanel.jsx").read_text(encoding="utf-8")
        self.assertIn("ingestGeneEvidence", src)
        for s in ("not_found", "not_ingested", "error", "unavailable", "Retry", "animate-spin"):
            self.assertIn(s, src)
        self.assertNotIn("min-h-[120px]", src)
        self.assertNotRegex(src, r"0\.0\d{3,}")
        client = Path("frontend/src/api/client.js").read_text(encoding="utf-8")
        self.assertIn("/api/genomic/gene/", client)


if __name__ == "__main__":
    unittest.main()
