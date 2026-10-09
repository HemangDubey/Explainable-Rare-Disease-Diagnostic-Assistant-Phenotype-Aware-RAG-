"""Phase 5R tests: clinical scribe drafts + counterfactual scenarios.

FIXTURE classes (clearly labelled) stand in for the NER extractor, HPO normalizer and ranking pipeline in unit tests.
`TestRealPipelineApi` uses the real models through the FastAPI TestClient.
"""
import copy
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.append(os.path.abspath("."))
from tests.helpers_auth import authed_client, register_and_login, use_temp_database  # noqa: E402

use_temp_database()

from src.counterfactual import scenario as sc                      # noqa: E402
from src.counterfactual.ranking_delta import compute_ranking_deltas  # noqa: E402
from src.scribe.draft_schema import DraftUpdate                    # noqa: E402
from src.scribe.draft_store import DbDraftStore, DraftNotFound, PersistenceError  # noqa: E402
from src.scribe.note_structurer import NoteStructurer              # noqa: E402

TEXT = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."
TERMS = {"seizures": "HP:0001250", "hypotonia": "HP:0001252", "developmental delay": "HP:0001263", "short stature": "HP:0004322",
         "epilepsy": "HP:0001250", "ataxia": "HP:0001251"}


def fixture_extractor(text):
    """FIXTURE: dictionary phenotype finder (not the real NER)."""
    out = []
    for t, h in TERMS.items():
        for m in re.finditer(re.escape(t), text, re.I):
            out.append({"mention": m.group(0), "start": m.start(), "end": m.end(), "hpo_id": h, "hpo_term": t, "mapping_status": "exact", "mapping_score": 1.0})
    return sorted(out, key=lambda x: x["start"])


S = NoteStructurer(fixture_extractor)


def pheno(note):
    d = S.structure(note)
    return {p.mention.lower(): p for p in d.phenotypes}, d


class TestScribeSemantics(unittest.TestCase):
    def test_structure_example(self):
        ph, d = pheno(TEXT)
        self.assertEqual(d.status, "Draft — clinician review required")
        self.assertEqual(d.sections["presenting_concerns"].status, "provided")
        self.assertEqual({p.status for p in ph.values()}, {"present"})
        for st in d.statements:                                    # every statement is a verbatim span of the input
            self.assertEqual(d.source_text[st.source.start:st.source.end], st.text)

    def test_negation_preserved(self):
        ph, _ = pheno("Mother reports that the child does not have seizures.")
        self.assertEqual(ph["seizures"].status, "negated")
        self.assertEqual(ph["seizures"].subject, "patient")

    def test_negation_list_scope(self):
        ph, _ = pheno("No seizures, ataxia or hypotonia. Short stature noted.")
        self.assertEqual([ph[k].status for k in ("seizures", "ataxia", "hypotonia")], ["negated"] * 3)
        self.assertEqual(ph["short stature"].status, "present")

    def test_unmentioned_is_not_absent(self):
        ph, d = pheno("Child has hypotonia.")
        self.assertNotIn("seizures", ph)
        self.assertEqual([p.status for p in d.phenotypes], ["present"])

    def test_uncertainty_and_pending_not_confirmed(self):
        ph, d = pheno("Possible developmental delay; assessment pending.")
        self.assertEqual(ph["developmental delay"].status, "uncertain")
        self.assertEqual(d.sections["known_diagnoses"].status, "not_provided")
        self.assertEqual(d.diagnosis_input, "")                    # uncertain findings are not sent to diagnosis
        self.assertTrue(any("uncertain or pending" in i.text for i in d.sections["missing_or_unverified_information"].items))

    def test_temporal_detail_verbatim(self):
        _, d = pheno("Seizures began around age three.")
        self.assertIn("began around age three", d.statements[0].temporal)
        self.assertNotIn("3", " ".join(d.statements[0].temporal))

    def test_family_history_relationship(self):
        ph, d = pheno("Mother has epilepsy. Child has hypotonia.")
        self.assertEqual(ph["epilepsy"].status, "relative_finding")
        self.assertEqual(ph["epilepsy"].relationship, "mother")
        self.assertEqual(d.sections["family_history"].status, "provided")
        self.assertEqual(d.diagnosis_input, "Patient presents with hypotonia.")

    def test_missing_information_and_no_invention(self):
        _, d = pheno(TEXT)
        for key in ("relevant_medical_history", "family_history", "examination_findings", "investigations_and_results", "known_diagnoses"):
            self.assertEqual(d.sections[key].status, "not_provided", key)
            self.assertEqual(d.sections[key].items, [])
        blob = json.dumps(d.model_dump())
        for invented in ("male", "female", "year-old", "MRI", "EEG", "consanguin"):
            self.assertNotIn(invented.lower(), json.dumps([s.model_dump() for s in d.statements]).lower())
        self.assertIn("not provided", blob)

    def test_investigation_and_exam_not_invented_but_routed(self):
        _, d = pheno("EEG showed generalised spikes. On examination height is below the third centile.")
        self.assertEqual(d.sections["investigations_and_results"].status, "provided")
        self.assertEqual(d.sections["examination_findings"].status, "provided")

    def test_clinician_phenotype_list_kept_separate(self):
        d = S.structure("Child is irritable.", supplied_phenotypes=["hypotonia"])
        u = [s for s in d.statements if s.origin == "clinician_supplied"]
        self.assertEqual(len(u), 1)
        self.assertEqual(u[0].source.input, "clinician_phenotype_list")

    def test_extractor_failure_keeps_text(self):
        def boom(_):
            raise RuntimeError("x")
        d = NoteStructurer(boom).structure("Child has hypotonia.")
        self.assertEqual(d.statements[0].text, "Child has hypotonia")
        self.assertTrue(any("failed" in i.text for i in d.sections["clinician_review_notes"].items))


class TestDraftEditingAndPersistence(unittest.TestCase):
    """Real SQLite database (temp file, Alembic-migrated). Drafts are owned by a user id; there are no draft tokens any more."""

    @classmethod
    def setUpClass(cls):
        from src.db.migrate import upgrade_head
        upgrade_head()
        from fastapi.testclient import TestClient
        # user rows are needed for the owner foreign key; create them through the real auth service
        from src.auth import service
        cls.alice = service.register(f"alice-{os.urandom(3).hex()}@example.test", "Synthetic-Passw0rd-xyz")["id"]
        cls.bob = service.register(f"bob-{os.urandom(3).hex()}@example.test", "Synthetic-Passw0rd-xyz")["id"]

    def setUp(self):
        self.store = DbDraftStore()

    def test_edit_verify_remove(self):
        d = self.store.create(S.structure(TEXT), self.alice)
        self.assertTrue(d.saved)
        sid = d.statements[0].id
        pid = d.phenotypes[0].id
        out = self.store.update(d.draft_id, self.alice, DraftUpdate(statements=[{"id": sid, "text": "Patient presents with hypotonia.", "verified": True}],
                                                                    phenotypes=[{"id": pid, "verified": True}], clinician_notes="checked"))
        st = out.statements[0]
        self.assertTrue(st.edited and st.verified and st.origin == "clinician_edit")
        self.assertEqual(st.source.start, d.statements[0].source.start)      # provenance preserved
        self.assertEqual(self.store.get(d.draft_id, self.alice).clinician_notes, "checked")
        self.assertIn("clinician-reviewed", self.store.update(d.draft_id, self.alice, DraftUpdate(review_state="reviewed")).status)
        self.assertNotIn("signed by", self.store.get(d.draft_id, self.alice).status.lower())

    def test_ownership(self):
        d = self.store.create(S.structure(TEXT), self.alice)
        with self.assertRaises(DraftNotFound):
            self.store.get(d.draft_id, self.bob)
        with self.assertRaises(DraftNotFound):
            self.store.update(d.draft_id, self.bob, DraftUpdate(clinician_notes="x"))
        with self.assertRaises(DraftNotFound):
            self.store.delete(d.draft_id, self.bob)
        with self.assertRaises(DraftNotFound):
            self.store.get("0" * 12, self.alice)
        with self.assertRaises(DraftNotFound):
            self.store.get("../../etc/passwd", self.alice)
        self.assertEqual(self.store.get(d.draft_id, self.alice).draft_id, d.draft_id)      # the owner is unaffected

    def test_persistence_failure_reported(self):
        from unittest import mock
        from src.db.errors import StorageError
        with mock.patch.object(DbDraftStore, "_create", side_effect=StorageError("OperationalError")):
            with self.assertRaises(PersistenceError):
                self.store.create(S.structure(TEXT), self.alice)

    def test_logging_has_no_note_text(self):
        with self.assertLogs("scribe_drafts", level="INFO") as cm:
            self.store.create(S.structure("Child has hypotonia and secret-marker-xyz."), self.alice)
        self.assertNotIn("secret-marker-xyz", "\n".join(cm.output))
        self.assertNotIn("hypotonia", "\n".join(cm.output))


# ----------------------------------------------------------------------------------------------------------------------------
class FixtureNormalizer:
    """FIXTURE normalizer with a tiny vocabulary."""
    VOC = {"HP:0001250": "Seizure", "HP:0001252": "Hypotonia", "HP:0001263": "Global developmental delay", "HP:0004322": "Short stature",
           "HP:0001251": "Ataxia", "HP:0000252": "Microcephaly"}

    class res:
        @staticmethod
        def resolve_id(h):
            return h if h in FixtureNormalizer.VOC else None

        @staticmethod
        def is_phenotypic(h):
            return h != "HP:0000118x"

    def _name(self, h):
        return self.VOC[h]

    def normalize_detailed(self, q):
        ql = q.lower()
        for h, n in self.VOC.items():
            if ql == n.lower():
                return {"status": "exact", "hpo_id": h, "term": n, "score": 1.0, "matching_method": "exact", "is_phenotypic": True}
        if ql == "fits":
            return {"status": "ambiguous", "candidates": [{"hpo_id": "HP:0001250", "name": "Seizure"}, {"hpo_id": "HP:0001251", "name": "Ataxia"}]}
        return {"status": "unmatched", "suggestions": [{"hpo_id": "HP:0001250", "name": "Seizure", "score": 0.5}]}


class FixturePipeline:
    """FIXTURE ranking pipeline: records every call and ranks diseases deterministically from the input HPO set."""
    DISEASES = {"D1": {"HP:0001250", "HP:0001252"}, "D2": {"HP:0001263", "HP:0004322"}, "D3": {"HP:0001251"}, "D4": {"HP:0000252", "HP:0001250"}}

    class disease_ranker:
        weights = {"w_population": 0.0}

    def __init__(self):
        self.calls = []

    def run_from_hpo_terms(self, hpo_terms, top_k_disease=10, exp_config="x", strategy=None):
        self.calls.append([h["hpo_id"] for h in hpo_terms])
        ids = {h["hpo_id"] for h in hpo_terms}
        scored = sorted(((len(ids & v) / max(len(ids), 1), d) for d, v in self.DISEASES.items()), key=lambda x: (-x[0], x[1]))
        ranked = [{"disease_id": d, "disease_name": f"Disease {d}", "retrieval_score": s, "phenotype_score": s, "base_score": s, "final_score": s,
                   "population_contribution": 0.0} for s, d in scored if s > 0][:top_k_disease]
        return {"ranked_candidates": ranked}


BASE = [{"hpo_id": h, "name": FixtureNormalizer.VOC[h], "score": 1.0} for h in ("HP:0001252", "HP:0004322", "HP:0001263", "HP:0001250")]
N = FixtureNormalizer()


class TestScenarioLogic(unittest.TestCase):
    def run_ops(self, ops, top_k=3):
        p = FixturePipeline()
        before = copy.deepcopy(BASE)
        res = sc.run_scenario(p, N, BASE, ops, top_k=top_k)
        self.assertEqual(BASE, before, "baseline must not be mutated")
        return res, p

    def test_add_invokes_pipeline_with_hypothetical_set(self):
        res, p = self.run_ops([{"op": "add", "phenotype": "Ataxia"}])
        self.assertEqual(len(p.calls), 2)
        self.assertIn("HP:0001251", p.calls[1])
        self.assertNotIn("HP:0001251", p.calls[0])
        self.assertTrue(res["hypothetical"])
        self.assertEqual(res["hypothetical_phenotypes"][-1]["origin"], "hypothetical_added")
        self.assertTrue(all(t["origin"] == "observed" for t in res["hypothetical_phenotypes"][:-1]))

    def test_remove(self):
        res, p = self.run_ops([{"op": "remove", "phenotype": "HP:0001250"}])
        self.assertNotIn("HP:0001250", p.calls[1])
        self.assertEqual(res["operations"][0]["status"], "applied")

    def test_modify(self):
        res, p = self.run_ops([{"op": "modify", "phenotype": "Hypotonia", "replacement": "Microcephaly"}])
        ids = [t["hpo_id"] for t in res["hypothetical_phenotypes"]]
        self.assertIn("HP:0000252", ids)
        self.assertNotIn("HP:0001252", ids)
        self.assertEqual(res["operations"][0]["original"]["hpo_id"], "HP:0001252")
        self.assertEqual(res["baseline_phenotypes"][0]["hpo_id"], "HP:0001252")      # original preserved alongside

    def test_invalid_ambiguous_unresolved_not_applied_and_no_invented_id(self):
        res, p = self.run_ops([{"op": "add", "phenotype": "HP:9999999"}, {"op": "add", "phenotype": "fits"}, {"op": "add", "phenotype": "zzzz"},
                               {"op": "add", "phenotype": ""}])
        self.assertEqual([r["status"] for r in res["operations"]], ["invalid", "ambiguous", "unresolved", "invalid"])
        self.assertEqual(res["operations_applied"], 0)
        self.assertEqual(res["status"], "no_operation_applied")
        self.assertEqual(p.calls[0], p.calls[1])                                      # nothing was added
        self.assertEqual(res["operations"][1]["resolution"]["suggestions"][0]["hpo_id"], "HP:0001250")
        self.assertEqual(res["operations"][2]["resolution"]["hpo_id"], None)

    def test_remove_absent_phenotype(self):
        res, _ = self.run_ops([{"op": "remove", "phenotype": "Ataxia"}])
        self.assertEqual(res["operations"][0]["status"], "not_in_case")

    def test_reversible(self):
        add, rem = {"op": "add", "phenotype": "Ataxia"}, {"op": "remove", "phenotype": "Ataxia"}
        res, _ = self.run_ops([add, rem])
        self.assertEqual({t["hpo_id"] for t in res["hypothetical_phenotypes"]}, {t["hpo_id"] for t in BASE})
        self.assertTrue(all(d["rank_displacement"] == 0 for d in res["comparison"]))
        none, _ = self.run_ops([])                                                  # reset == no operations
        self.assertTrue(all(d["magnitude"] == "unchanged" for d in none["comparison"]))

    def test_rank_displacement_sign_and_absence(self):
        base = [{"disease_id": f"D{i}", "disease_name": f"D{i}", "final_score": 1 - i / 10} for i in range(1, 6)]
        cf = [base[4], base[0], base[1], {"disease_id": "DX", "disease_name": "DX", "final_score": 0.1}]
        rows = {r["disease_id"]: r for r in sc.compare_rankings(base, cf, display_k=3)}
        self.assertEqual(rows["D5"]["baseline"]["rank"], 5)
        self.assertEqual(rows["D5"]["counterfactual"]["rank"], 1)
        self.assertEqual(rows["D5"]["rank_displacement"], 4)                         # moved up 4
        self.assertEqual(rows["D5"]["direction"], "up")
        self.assertEqual(rows["D1"]["rank_displacement"], -1)                        # moved down 1
        self.assertEqual(rows["D3"]["presence"], "left_list")
        self.assertIsNone(rows["D3"]["counterfactual"]["final_score"])               # no invented score
        self.assertIsNone(rows["D3"]["rank_displacement"])
        self.assertEqual(rows["DX"]["presence"], "entered_list")
        self.assertIsNone(rows["DX"]["baseline"]["final_score"])
        self.assertEqual(rows["DX"]["magnitude"], "small")                           # entered beyond the displayed top-3
        self.assertEqual(rows["D3"]["magnitude"], "substantial")                     # left from rank 3 (inside top-3)
        self.assertEqual(rows["D5"]["magnitude"], "substantial")
        self.assertEqual(rows["D1"]["magnitude"], "small")

    def test_score_component_consistency(self):
        res, _ = self.run_ops([{"op": "remove", "phenotype": "HP:0001250"}])
        for r in res["comparison"]:
            if r["presence"] == "both":
                for k, d in r["deltas"].items():
                    self.assertAlmostEqual(d, r["counterfactual"][k] - r["baseline"][k], places=5)

    def test_explanations_non_causal(self):
        res, _ = self.run_ops([{"op": "add", "phenotype": "Ataxia"}])
        text = " ".join(res["explanations"]).lower()
        self.assertNotIn("proves", text)
        self.assertNotIn("correct diagnosis", text)
        self.assertIn("population weight is 0", text)
        self.assertIn("hypothetical", res["scenario_label"].lower())

    def test_legacy_delta_has_no_fabricated_values(self):
        d = compute_ranking_deltas([{"disease_id": "A", "disease_name": "A", "rank": 1, "final_score": 0.9}],
                                   [{"disease_id": "B", "disease_name": "B", "rank": 1, "final_score": 0.5}])
        gone = next(x for x in d if x.disease_id == "A")
        new = next(x for x in d if x.disease_id == "B")
        self.assertIsNone(gone.counterfactual_score)
        self.assertIsNone(gone.counterfactual_rank)
        self.assertEqual(gone.trend, "left_list")
        self.assertEqual(new.trend, "entered_list")
        self.assertIsNone(new.original_score)


# ----------------------------------------------------------------------------------------------------------------------------
class TestRealPipelineApi(unittest.TestCase):
    """Real models (BiomedBERT NER, HPO normaliser, S-PubMedBERT + FAISS, Phase 3R ranking, Phase 4R fusion)."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from src.api.main import app
        cls._ctx = TestClient(app)
        cls.client = cls._ctx.__enter__()
        cls.user = authed_client(cls.client)                                # a synthetic user owns everything created below
        d = cls.client.post("/api/diagnose", json={"clinical_text": TEXT, "top_k": 5}).json()
        cls.case_id = d["case_id"]
        cls.diag = d

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def scen(self, ops, **kw):
        r = self.client.post("/api/counterfactual/scenario", json={"case_id": self.case_id, "operations": ops, "top_k": 5, **kw})
        return r

    def test_reset_scenario_equals_baseline_and_diagnose(self):
        r = self.scen([]).json()
        self.assertTrue(all(c["rank_displacement"] == 0 and c["presence"] == "both" for c in r["comparison"][:5]))
        diag_order = [c["disease_id"] for c in self.diag["fused_candidates"]]
        self.assertEqual([c["disease_id"] for c in r["baseline_ranking"]], diag_order)        # same path as /api/diagnose (Phase 2R/3R reuse)
        for a, b in zip(r["baseline_ranking"], self.diag["fused_candidates"]):
            self.assertAlmostEqual(a["final_score"], b["final_score"], places=5)

    def test_remove_changes_real_pipeline_input_and_not_original(self):
        import copy as cp
        from src.api import repo
        uid = self.user["user"]["id"]
        before = json.dumps(repo.get_case(uid, self.case_id)["hpo_terms"], sort_keys=True, default=str)
        r = self.scen([{"op": "remove", "phenotype": "HP:0001250"}]).json()
        after = json.dumps(repo.get_case(uid, self.case_id)["hpo_terms"], sort_keys=True, default=str)
        self.assertEqual(before, after)
        self.assertEqual(r["operations"][0]["status"], "applied")
        self.assertNotIn("HP:0001250", [t["hpo_id"] for t in r["hypothetical_phenotypes"]])
        self.assertIn("HP:0001250", [t["hpo_id"] for t in r["baseline_phenotypes"]])
        self.assertTrue(r["hypothetical"])
        self.assertEqual(r["pipeline"]["function"], "Phase3RankingPipeline.run_from_hpo_terms")
        changed = [c for c in r["comparison"] if c["presence"] == "both" and c["deltas"]["retrieval_score"]]
        self.assertTrue(changed, "removing a phenotype must change at least one real retrieval score")

    def test_add_valid_hpo_and_invalid(self):
        ok = self.scen([{"op": "add", "phenotype": "HP:0001251"}]).json()
        self.assertEqual(ok["operations"][0]["status"], "applied")
        self.assertEqual(ok["hypothetical_phenotypes"][-1]["origin"], "hypothetical_added")
        bad = self.scen([{"op": "add", "phenotype": "HP:9999999"}]).json()
        self.assertEqual(bad["operations"][0]["status"], "invalid")
        self.assertEqual(bad["operations_applied"], 0)
        self.assertIsNone(bad["operations"][0]["resolution"]["hpo_id"])

    def test_unresolved_text_not_applied(self):
        r = self.scen([{"op": "add", "phenotype": "qwertyuiop flarb"}]).json()
        self.assertIn(r["operations"][0]["status"], ("unresolved", "ambiguous"))
        self.assertEqual(r["operations_applied"], 0)

    def test_modify_and_evidence_integration(self):
        r = self.scen([{"op": "modify", "phenotype": "HP:0001252", "replacement": "HP:0001251"}]).json()
        self.assertEqual(r["operations"][0]["status"], "applied")
        self.assertTrue(r["evidence_changes"])
        for ev in r["evidence_changes"].values():
            self.assertTrue(ev["score_breakdown_matches_backend"])
        self.assertIn("population weight is 0", " ".join(r["explanations"]))
        self.assertIn("IndiGen", r["population_note"])

    def test_bad_requests(self):
        self.assertEqual(self.client.post("/api/counterfactual/scenario", json={"operations": []}).status_code, 422)
        r = self.client.post("/api/counterfactual/scenario", json={"case_id": self.case_id, "operations": [{"op": "toggle", "phenotype": "x"}]})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["status"], "invalid_input")

    def test_scenario_retrieval(self):
        sid = self.scen([]).json()["scenario_id"]
        self.assertEqual(self.client.get(f"/api/counterfactual/scenario/{sid}").status_code, 200)
        self.assertEqual(self.client.get("/api/counterfactual/scenario/nope").status_code, 404)

    def test_legacy_counterfactual_contract_kept(self):
        r = self.client.post("/api/counterfactual", json={"case_id": self.case_id, "operation": "remove", "phenotype_id": "HP:0001250", "top_k": 5})
        self.assertEqual(r.status_code, 200)
        self.assertIn("ranking_deltas", r.json())

    # ---- scribe API ----
    def test_draft_api_end_to_end(self):
        r = self.client.post("/api/scribe/draft", json={"clinical_text": TEXT})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["saved"])
        self.assertNotIn("edit_token", d)
        self.assertEqual(d["status"], "Draft — clinician review required")
        self.assertEqual(d["provider"]["language_model"], "not_used")
        hp = {p["mention"].lower(): p for p in d["phenotypes"]}
        for m in ("hypotonia", "short stature", "developmental delay", "recurrent seizures"):
            self.assertIn(m, hp)
            self.assertEqual(hp[m]["status"], "present")
            self.assertTrue(hp[m]["hpo_id"].startswith("HP:"))
        self.assertEqual(d["sections"]["family_history"]["status"], "not_provided")
        self.assertEqual(self.client.get(f"/api/scribe/draft/{d['draft_id']}").status_code, 200)
        self.assertEqual(self.client.get("/api/scribe/draft/ffffffffffff").status_code, 404)
        u = self.client.put(f"/api/scribe/draft/{d['draft_id']}", json={"clinician_notes": "reviewed"})
        self.assertEqual(u.status_code, 200)
        self.assertEqual(u.json()["clinician_notes"], "reviewed")
        from fastapi.testclient import TestClient
        anon = TestClient(self.client.app)
        self.assertEqual(anon.get(f"/api/scribe/draft/{d['draft_id']}").status_code, 401)
        self.assertEqual(anon.put(f"/api/scribe/draft/{d['draft_id']}", json={"clinician_notes": "x"}).status_code, 401)

    def test_draft_negation_real_ner(self):
        d = self.client.post("/api/scribe/draft", json={"clinical_text": "Mother reports that the child does not have seizures. Child has hypotonia.", "save": False}).json()
        st = {p["mention"].lower(): p["status"] for p in d["phenotypes"]}
        self.assertEqual(st.get("seizures"), "negated")
        self.assertEqual(st.get("hypotonia"), "present")
        self.assertNotIn("seizure", d["diagnosis_input"].lower())
        self.assertFalse(d["saved"])

    def test_draft_invalid_input(self):
        r = self.client.post("/api/scribe/draft", json={"clinical_text": "   "})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["status"], "invalid_input")

    def test_old_scribe_contract_has_no_fabricated_confidence(self):
        r = self.client.post("/api/scribe", json={"clinical_text": TEXT}).json()
        self.assertEqual(r["confidence"], {})

    def test_groq_utility_untouched_and_no_key_in_responses(self):
        r = self.client.post("/api/scribe/draft", json={"clinical_text": TEXT, "check_enhancement": True, "save": False})
        blob = r.text.lower()
        self.assertNotIn("groq", blob)
        self.assertNotIn("gsk_", blob)
        self.assertIn("enhancement", r.json()["input_check"])


class TestFrontendStatic(unittest.TestCase):
    """Static checks of the Phase 5R UI contract (the production build is run separately)."""

    @staticmethod
    def read(p):
        with open(os.path.join("frontend", "src", p), encoding="utf-8") as f:
            return f.read()

    def test_scribe_view(self):
        v = self.read("components/ClinicalScribeView.jsx")
        for needle in ("createScribeDraft", "updateScribeDraft", "NOT SAVED", "UNSAVED EDITS", "beforeunload", "window.confirm",
                       "Not provided in the input", "no language model used", "verified"):
            self.assertIn(needle, v)
        self.assertNotRegex(v.lower(), r"groq|signed by|approved by|finalized")

    def test_counterfactual_view(self):
        v = self.read("components/CounterfactualView.jsx")
        for needle in ("runCounterfactualScenario", "scenario_label", "Reset to baseline", "Undo last", "revert this step",
                       "hypothetical_added", "NOT applied", "window.confirm", "rank_displacement"):
            self.assertIn(needle, v.replace("hypothetical_added", "hypothetical_added"))
        self.assertNotRegex(v.lower(), r"groq")


if __name__ == "__main__":
    unittest.main()
