"""Phase 7R.5: Clinical Digital Twin tests.

Unit level: deterministic HPO -> region mapping (real HPO ontology file), assertion/verification display states, genomic evidence
packaging with missing values, evidence-graph grounding. Integration level: the real FastAPI app with the real pipeline and a temp
SQLite database (auth, ownership, review persistence, scenarios). Static level: frontend files contain no reference-image data, the
anatomy asset is a valid GLB whose hash matches its manifest, and licence/fallback/reduced-motion code exists. All data is synthetic.
"""
import hashlib
import json
import os
import re
import struct
import sys
import unittest

sys.path.append(os.path.abspath("."))
from tests.helpers_auth import authed_client, use_temp_database  # noqa: E402

use_temp_database()
from src.twin.anatomy import REGIONS, AnatomyMapper  # noqa: E402
from src.twin.builder import _gene_evidence, assess_assertion, build_findings, build_graph, build_twin, display_state  # noqa: E402

HPO_FILE = "data/processed/hpo/hpo_terms.json"
FRONT = "frontend/src"
ASSET_DIR = "frontend/public/models/anatomy"
_TERMS = None


def terms():
    global _TERMS
    if _TERMS is None:
        with open(HPO_FILE, encoding="utf-8") as f:
            _TERMS = json.load(f)
    return _TERMS


@unittest.skipUnless(os.path.exists(HPO_FILE), "HPO ontology file not provisioned")
class TestRegionMapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = AnatomyMapper(terms())

    def regions(self, h):
        return [r["region"] for r in self.m.regions_for(h)]

    def test_table_ids_exist_in_this_hpo_release(self):
        self.assertEqual(self.m.dropped, [])

    def test_known_mappings(self):
        self.assertEqual(self.regions("HP:0001250"), ["brain"])          # Seizure
        self.assertEqual(self.regions("HP:0002240"), ["liver"])          # Hepatomegaly: liver only, digestive suppressed
        self.assertEqual(self.regions("HP:0004322"), ["systemic"])       # Short stature: not localisable
        self.assertEqual(self.regions("HP:0000365"), ["ears"])           # Hearing impairment
        self.assertEqual(self.regions("HP:0001631"), ["heart"])          # Atrial septal defect
        self.assertEqual(self.regions("HP:0002650"), ["spine"])          # Scoliosis

    def test_most_specific_entry_kept(self):
        r = self.regions("HP:0002240")
        self.assertNotIn("abdomen", r)
        self.assertNotIn("head", self.regions("HP:0000486"))             # Strabismus -> eyes, not the broader head/neck entry

    def test_unmapped_and_unknown_ids_return_empty(self):
        self.assertEqual(self.m.regions_for("HP:0001382"), [])           # Joint hypermobility: no organ-system ancestor in the table
        self.assertEqual(self.m.regions_for("HP:9999999"), [])
        self.assertEqual(self.m.regions_for(""), [])
        self.assertEqual(self.m.regions_for(None), [])

    def test_mapping_is_deterministic_and_has_provenance(self):
        a, b = self.m.regions_for("HP:0000252"), AnatomyMapper(terms()).regions_for("HP:0000252")
        self.assertEqual(a, b)
        for r in a:
            self.assertIn(r["via_hpo_id"], self.m.ancestors("HP:0000252"))
            self.assertTrue(r["via_hpo_name"] and r["rule"])

    def test_every_region_has_catalogue_entry(self):
        from src.twin.anatomy import ORGAN_SYSTEM_TABLE
        for _, region in ORGAN_SYSTEM_TABLE:
            self.assertIn(region, REGIONS)
        manifest_tags = {p["region"] for p in json.load(open(os.path.join(ASSET_DIR, "anatomy_manifest.json")))["parts"]}
        for key, r in REGIONS.items():
            for tag in r["mesh_regions"]:
                self.assertIn(tag, manifest_tags, f"{key} -> {tag} has no mesh in the asset")


class TestAssertionAndStates(unittest.TestCase):
    def test_display_state_rules(self):
        self.assertEqual(display_state(True, "patient", "present", True), "confirmed")
        self.assertEqual(display_state(True, "patient", "present", False), "unverified")
        for st in ("negated", "uncertain", "pending"):
            self.assertEqual(display_state(True, "patient", st, True), st, "verification must never turn a non-present finding into confirmed")
        self.assertEqual(display_state(True, "relative", "present", True), "relative_finding")
        self.assertEqual(display_state(False, "patient", "present", True), "unmapped")

    def test_rule_based_assertion(self):
        t = "The child has seizures. There is no hepatomegaly. Possible hearing loss."
        s = t.index("seizures"); self.assertEqual(assess_assertion(t, s, s + 8)["status"], "present")
        s = t.index("hepatomegaly"); self.assertEqual(assess_assertion(t, s, s + 12)["status"], "negated")
        s = t.index("hearing loss"); self.assertEqual(assess_assertion(t, s, s + 12)["status"], "uncertain")
        self.assertEqual(assess_assertion(t, None, None)["status"], "pending")

    @unittest.skipUnless(os.path.exists(HPO_FILE), "HPO ontology file not provisioned")
    def test_build_findings_review_overrides(self):
        t = "The child has seizures. There is no hepatomegaly. Joint laxity noted."
        case = {"clinical_text": t, "extracted_phenotypes": [
            {"mention": "seizures", "start": t.index("seizures"), "end": t.index("seizures") + 8, "hpo_id": "HP:0001250", "hpo_term": "Seizure", "mapping_status": "exact"},
            {"mention": "hepatomegaly", "start": t.index("hepatomegaly"), "end": t.index("hepatomegaly") + 12, "hpo_id": "HP:0002240", "hpo_term": "Hepatomegaly", "mapping_status": "exact"},
            {"mention": "Joint laxity", "start": t.index("Joint"), "end": t.index("Joint") + 12, "hpo_id": "HP:0001382", "hpo_term": "Joint hypermobility", "mapping_status": "synonym"},
            {"mention": "funny turns", "start": None, "end": None, "hpo_id": None, "mapping_status": "unresolved"}]}
        m = AnatomyMapper(terms())
        fs = build_findings(case, m)
        self.assertEqual([f["display_state"] for f in fs], ["unverified", "negated", "unverified", "unmapped"])
        self.assertTrue(fs[2]["unassigned"])
        self.assertEqual(fs[2]["regions"], [])
        self.assertFalse(fs[3]["unassigned"])
        self.assertIsNone(fs[3]["hpo_id"])
        case["phenotype_review"] = {fs[0]["finding_id"]: {"verified": True}, fs[1]["finding_id"]: {"verified": True}}
        fs2 = build_findings(case, m)
        self.assertEqual(fs2[0]["display_state"], "confirmed")
        self.assertEqual(fs2[1]["display_state"], "negated")
        case["phenotype_review"][fs[0]["finding_id"]]["status"] = "uncertain"
        self.assertEqual(build_findings(case, m)[0]["display_state"], "uncertain")
        self.assertEqual(build_findings(case, m)[0]["status_source"], "clinician")


class TestGenomicAndGraph(unittest.TestCase):
    def test_missing_gene_data_is_marked_unavailable(self):
        g = _gene_evidence("GENEX", None, None)
        self.assertEqual(g["patient_variant"]["status"], "not_provided")
        for k in ("gnomad_global", "gnomad_south_asian", "indigen", "clinvar"):
            self.assertEqual(g[k]["status"], "unavailable", k)

    def test_available_gene_data_and_sas_wording(self):
        rec = {"status": "available", "source": "test", "clinvar_total": 3, "clinvar_plp": 1, "plp_variants": [
            {"variant_id": "1-100-A-G", "clinical_significance": "Pathogenic", "gold_stars": 2, "exome": {"ac": 1, "an": 1000, "sas_ac": 0, "sas_an": 0}}]}
        info = {"gnomad": {"status": "available", "caf_global": 0.001, "caf_sas": 0.0, "dataset_version": "gnomAD test"}, "indigen": {"status": "unavailable"}}
        g = _gene_evidence("GENEY", lambda s: rec, lambda s: info)
        self.assertEqual(g["clinvar"]["variants"][0]["af_global"], 0.001)
        self.assertIsNone(g["clinvar"]["variants"][0]["af_south_asian"])          # AN = 0 -> unknown, not 0
        self.assertIn("None of them was detected in this patient", g["clinvar"]["note"])
        self.assertIn("not an India-specific", g["gnomad_south_asian"]["note"])
        self.assertNotIn("indian", json.dumps(g).lower().replace("india-specific", ""))
        self.assertEqual(g["patient_variant"]["status"], "not_provided")

    def test_graph_edges_are_grounded(self):
        findings = [{"finding_id": "F0_1_2", "text_span": "seizures", "display_state": "unverified", "hpo_id": "HP:0001250", "hpo_label": "Seizure",
                     "status": "present", "verified": False, "normalization": {}},
                    {"finding_id": "F1", "text_span": "x", "display_state": "unmapped", "hpo_id": None, "hpo_label": None, "status": "present", "verified": False, "normalization": {}}]
        cands = [{"disease_id": "D:1", "disease_name": "Disease one", "rank": 1, "final_score": 0.5, "label": None, "genes": ["GENEA"],
                  "evidence": [{"id": "C1-E1", "type": "phenotype_match", "text": "t", "source": "s", "hpo_id": "HP:0001250"},
                               {"id": "C1-E2", "type": "phenotype_match", "text": "t", "source": "s", "hpo_id": "HP:0000001"},   # not in case -> no edge
                               {"id": "C1-E3", "type": "gene_association", "text": "GENEA associated", "source": "s", "hpo_id": None}]}]
        g = build_graph(findings, cands)
        ids = {n["id"] for n in g["nodes"]}
        for e in g["edges"]:
            self.assertIn(e["source"], ids)
            self.assertIn(e["target"], ids)
        ann = [e for e in g["edges"] if e["type"] == "annotated_to"]
        self.assertEqual([e["evidence_id"] for e in ann], ["C1-E1"])
        self.assertNotIn("h:HP:0000001", ids)
        self.assertEqual(g["literature"]["status"], "not_retrieved")
        self.assertFalse(any(n["type"] == "literature" for n in g["nodes"]))

    @unittest.skipUnless(os.path.exists(HPO_FILE), "HPO ontology file not provisioned")
    def test_twin_without_ranking(self):
        tw = build_twin("c1", {"clinical_text": "", "extracted_phenotypes": []}, AnatomyMapper(terms()))
        self.assertEqual(tw["candidates"], [])
        self.assertEqual(tw["genomic"]["genes"], [])
        self.assertFalse(tw["case"]["has_ranking"])


TEXT = ("Synthetic case. The child has recurrent seizures and global developmental delay. Hepatomegaly was noted on examination. "
        "There is no hearing impairment. Short stature is present.")


class TestTwinApi(unittest.TestCase):
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
        r = cls.c.post("/api/diagnose", json={"clinical_text": TEXT, "top_k": 5})
        assert r.status_code == 200, r.text
        cls.case_id = r.json()["case_id"]

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def setUp(self):
        self.main._hits.clear()

    def twin(self):
        r = self.c.get(f"/api/twin/{self.case_id}")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_requires_auth(self):
        from fastapi.testclient import TestClient
        anon = TestClient(self.main.app, raise_server_exceptions=False)
        for method, path in (("get", "/api/twin/cases"), ("get", f"/api/twin/{self.case_id}"), ("put", f"/api/twin/{self.case_id}/findings"), ("post", "/api/twin/regions")):
            self.assertEqual(getattr(anon, method)(path, **({"json": {}} if method in ("put", "post") else {})).status_code, 401, path)

    def test_other_user_cannot_read_or_review(self):
        from fastapi.testclient import TestClient
        other = TestClient(self.main.app, raise_server_exceptions=False)
        authed_client(other)
        self.assertEqual(other.get(f"/api/twin/{self.case_id}").status_code, 404)
        fid = self.twin()["findings"][0]["finding_id"]
        r = other.put(f"/api/twin/{self.case_id}/findings", json={"updates": [{"finding_id": fid, "verified": True}]})
        self.assertEqual(r.status_code, 404)
        self.assertNotIn(self.case_id, [c["case_id"] for c in other.get("/api/twin/cases").json()["cases"]])
        self.assertNotIn(fid, (self.main.repo.get_case(self.user["user"]["id"], self.case_id).get("phenotype_review") or {}))

    def test_case_list_has_no_note_text(self):
        cases = self.c.get("/api/twin/cases").json()["cases"]
        self.assertIn(self.case_id, [c["case_id"] for c in cases])
        self.assertNotIn("seizures", json.dumps(cases).lower())

    def test_payload_is_grounded_in_the_stored_case(self):
        tw = self.twin()
        stored = self.main.repo.get_case(self.user["user"]["id"], self.case_id)
        self.assertEqual(len(tw["findings"]), len(stored["extracted_phenotypes"]))
        self.assertEqual([c["disease_id"] for c in tw["candidates"]], [c["disease_id"] for c in stored["fused_candidates"][:5]])
        for f in tw["findings"]:
            self.assertNotEqual(f["display_state"], "confirmed", "nothing is confirmed before clinician verification")
            if f["hpo_id"]:
                self.assertTrue(f["regions"] or f["unassigned"])
        for g in tw["genomic"]["genes"]:
            self.assertEqual(g["patient_variant"]["status"], "not_provided")
        node_ids = {n["id"] for n in tw["graph"]["nodes"]}
        ev_ids = {e["id"] for c in tw["candidates"] for e in c["evidence"]}
        for e in tw["graph"]["edges"]:
            self.assertIn(e["source"], node_ids)
            self.assertIn(e["target"], node_ids)
            if e.get("evidence_id"):
                self.assertIn(e["evidence_id"], ev_ids)

    def test_review_verify_negate_persist(self):
        tw = self.twin()
        mapped = [f for f in tw["findings"] if f["hpo_id"] and f["status"] == "present"]
        self.assertGreaterEqual(len(mapped), 2, "synthetic case should yield at least two mapped present findings")
        a, b = mapped[0]["finding_id"], mapped[1]["finding_id"]
        r = self.c.put(f"/api/twin/{self.case_id}/findings", json={"updates": [{"finding_id": a, "verified": True},
                                                                              {"finding_id": b, "verified": True, "status": "negated"}]})
        self.assertEqual(r.status_code, 200, r.text)
        after = {f["finding_id"]: f for f in self.twin()["findings"]}       # re-read: persisted, not just echoed
        self.assertEqual(after[a]["display_state"], "confirmed")
        self.assertEqual(after[b]["display_state"], "negated")
        self.assertEqual(after[b]["status_source"], "clinician")
        r = self.c.put(f"/api/twin/{self.case_id}/findings", json={"updates": [{"finding_id": a, "verified": False}, {"finding_id": b, "status": "present", "verified": False}]})
        self.assertEqual(r.status_code, 200)

    def test_review_rejects_unknown_and_invalid(self):
        r = self.c.put(f"/api/twin/{self.case_id}/findings", json={"updates": [{"finding_id": "F999_0_1", "verified": True}]})
        self.assertEqual(r.status_code, 422)
        fid = self.twin()["findings"][0]["finding_id"]
        r = self.c.put(f"/api/twin/{self.case_id}/findings", json={"updates": [{"finding_id": fid, "status": "definitely"}]})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.c.get("/api/twin/nonexistent-case").status_code, 404)

    def test_regions_endpoint(self):
        r = self.c.post("/api/twin/regions", json={"hpo_ids": ["HP:0001250", "HP:9999999"]})
        self.assertEqual(r.status_code, 200)
        reg = r.json()["regions"]
        self.assertEqual([x["region"] for x in reg["HP:0001250"]], ["brain"])
        self.assertEqual(reg["HP:9999999"], [])

    def test_scenario_is_listed_and_reopenable(self):
        r = self.c.post("/api/counterfactual/scenario", json={"case_id": self.case_id, "operations": [{"op": "add", "phenotype": "HP:0001251"}], "top_k": 5})
        self.assertEqual(r.status_code, 200, r.text)
        res = r.json()
        self.assertTrue(res["hypothetical"])
        listed = self.twin()["scenarios"]
        self.assertIn(res["scenario_id"], [s["scenario_id"] for s in listed])
        again = self.c.get(f"/api/counterfactual/scenario/{res['scenario_id']}").json()
        self.assertEqual(again["counterfactual_ranking"], res["counterfactual_ranking"])
        # the stored case itself is unchanged by a hypothetical scenario
        self.assertNotIn("HP:0001251", [f["hpo_id"] for f in self.twin()["findings"]])


REFERENCE_ONLY = ["Dravet", "RD-2024-001", "SCN1A", "MECP2", "23456789", "Dr. Researcher", "With Ataxia", "Rett"]


def _front_files():
    out = []
    for root, _, files in os.walk(FRONT):
        for f in files:
            if f.endswith((".js", ".jsx")):
                out.append(os.path.join(root, f))
    return out


class TestFrontendStatic(unittest.TestCase):
    TWIN = ["pages/DigitalTwinPage.jsx", "components/twin/TwinScene.jsx", "components/twin/twinModel.js", "components/twin/twinTheme.js",
            "components/twin/EvidenceNetwork.jsx", "components/twin/GenomicPanel.jsx", "components/twin/CounterfactualTwin.jsx"]

    def read(self, rel):
        with open(os.path.join(FRONT, rel), encoding="utf-8") as f:
            return f.read()

    def test_no_reference_image_data_hardcoded(self):
        for rel in self.TWIN:
            src = self.read(rel)
            for s in REFERENCE_ONLY:
                self.assertNotIn(s, src, f"{rel} contains reference-image content {s!r}")
            self.assertIsNone(re.search(r"HP:\d{7}", src), f"{rel} hardcodes an HPO id")
            self.assertIsNone(re.search(r"PMID", src), f"{rel} mentions PMIDs")

    def test_no_indian_label_for_south_asian(self):
        for rel in self.TWIN:
            self.assertNotRegex(self.read(rel), r"(?i)\bindian\b", rel)

    def test_route_nav_and_lazy_loading(self):
        app = self.read("App.jsx")
        self.assertIn('path="/digital-twin"', app)
        self.assertIn('path="/digital-twin" element={<Suspense', app)       # lazy route inside the protected app shell
        self.assertRegex(app, r"<Protected>\s*<WorkspaceProvider>\s*<AppShell />")
        self.assertIn("lazy(() => import('./pages/DigitalTwinPage'))", app)
        self.assertIn('to="/digital-twin"', self.read("components/Navbar.jsx"))
        self.assertIn("lazy(() => import('../components/twin/TwinScene'))", self.read("pages/DigitalTwinPage.jsx"))
        self.assertIn("/digital-twin?case=", self.read("pages/DashboardPage.jsx"))

    def test_fallbacks_and_motion(self):
        page = self.read("pages/DigitalTwinPage.jsx")
        self.assertIn("does not support WebGL", page)
        self.assertIn("not an anatomical model", page)
        self.assertIn("SceneBoundary", page)
        self.assertIn("prefers-reduced-motion", page)
        self.assertIn("visibilitychange", page)
        scene = self.read("components/twin/TwinScene.jsx")
        self.assertIn("material.dispose()", scene)
        self.assertIn("frameloop={animate ? 'always' : 'demand'}", scene)
        self.assertIn("prefers-reduced-motion", self.read("components/twin/GenomicPanel.jsx"))

    def test_api_calls_are_authenticated(self):
        client = open(os.path.join(FRONT, "api/client.js"), encoding="utf-8").read()
        twin_block = client[client.index("PHASE 7R.5"):]
        self.assertIn("authFetch(", twin_block)
        self.assertNotIn("fetch(`", twin_block.replace("authFetch(`", ""))

    def test_hypothetical_is_labelled(self):
        cf = self.read("components/twin/CounterfactualTwin.jsx")
        self.assertIn("HYPOTHETICAL", cf)
        self.assertIn("HYPOTHETICAL", self.read("pages/DigitalTwinPage.jsx"))
        self.assertIn("Illustration only", self.read("components/twin/GenomicPanel.jsx"))


class TestAnatomyAsset(unittest.TestCase):
    def test_glb_is_valid_and_matches_manifest(self):
        man = json.load(open(os.path.join(ASSET_DIR, "anatomy_manifest.json"), encoding="utf-8"))
        path = os.path.join(ASSET_DIR, man["asset"])
        data = open(path, "rb").read()
        magic, version, length = struct.unpack("<4sII", data[:12])
        self.assertEqual(magic, b"glTF")
        self.assertEqual(version, 2)
        self.assertEqual(length, len(data))
        self.assertEqual(len(data), man["bytes"])
        self.assertEqual(hashlib.sha256(data).hexdigest(), man["sha256"])
        self.assertLess(len(data), 15 * 1024 * 1024)
        clen, ctype = struct.unpack("<I4s", data[12:20])
        gltf = json.loads(data[20:20 + clen])
        names = {n.get("name") for n in gltf["nodes"]}
        for p in man["parts"]:
            self.assertIn(p["node"], names)
            self.assertRegex(p["node"], r"^(skin|skeleton|organs|nervous)__[a-z_]+__[A-Z]+\d+[a-z0-9]*$")

    def test_licence_and_attribution(self):
        man = json.load(open(os.path.join(ASSET_DIR, "anatomy_manifest.json"), encoding="utf-8"))
        self.assertIn("CC BY-SA 2.1", man["licence"])
        self.assertIn("Database Center for Life Science", man["credit"])
        lic = open(os.path.join(ASSET_DIR, "LICENSE_ANATOMY.md"), encoding="utf-8").read()
        self.assertIn("Attribution-ShareAlike 2.1 Japan", lic)
        page = open(os.path.join(FRONT, "pages/DigitalTwinPage.jsx"), encoding="utf-8").read()
        self.assertIn("BodyParts3D", page)
        self.assertIn("CC BY-SA", page)

    def test_asset_is_served_locally(self):
        model = open(os.path.join(FRONT, "components/twin/twinModel.js"), encoding="utf-8").read()
        self.assertIn("ASSET_URL = '/models/anatomy/", model)
        self.assertNotRegex(model, r"https?://")


if __name__ == "__main__":
    unittest.main()
