"""Unit and integration tests for Phase 6 Clinical Case Report Generator."""

from src.reporting.report_generator import CaseReportGenerator
from src.reporting.report_schema import ClinicalCaseReport


def test_report_generator():
    mock_case_data = {
        "case_id": "TEST_CASE_01",
        "clinical_text": "2-year-old child presenting with severe hypotonia, short stature, and global developmental delay.",
        "patient_metadata": {
            "age": "2 years",
            "gender": "Male",
            "ancestry": "South Asian / Indian"
        },
        "phenotypes": [{"text": "hypotonia"}, {"text": "short stature"}],
        "hpo_terms": [{"id": "HP:0001252", "name": "Hypotonia"}, {"id": "HP:0004322", "name": "Short stature"}],
        "fused_candidates": [
            {
                "disease_id": "OMIM:176270",
                "disease_name": "Prader-Willi Syndrome",
                "final_score": 0.89,
                "phenotype_evidence": 0.85,
                "retrieval_evidence": 0.90,
                "population_evidence": 0.92,
                "matched_hpo_ids": ["HP:0001252", "HP:0004322"],
                "genes": ["SNRPN", "MAGEL2"],
                "evidence_items": ["Strong phenotype correspondence"]
            }
        ],
        "top_explanation": {
            "reasoning_summary": "Marked concordance with Prader-Willi presentation."
        }
    }

    report = CaseReportGenerator.generate_report(mock_case_data)

    assert isinstance(report, ClinicalCaseReport)
    assert report.header.patient_id == "PT-RD-CURRENT"
    assert len(report.section_3_top_differentials) == 1
    assert report.section_3_top_differentials[0].disease_name == "Prader-Willi Syndrome"
    # Phase 6R correction: the earlier assertions encoded fabricated behaviour (priors always 'applied', template test
    # recommendations, a fixed limitation count). The stronger, truthful assertions below replace them.
    assert report.section_5_indian_population_context.population_priors_applied is False      # no ranking weight was supplied
    assert "unavailable" in " ".join(report.section_5_indian_population_context.relevant_subpopulations).lower()
    assert report.section_10_recommended_workup.confirmatory_genetic_tests == []
    assert report.section_10_recommended_workup.contraindicated_treatments == []
    assert "does not recommend" in report.section_10_recommended_workup.note
    assert report.section_9_counterfactual_sensitivity.rank_stability_score is None
    assert report.section_1_case_summary["ancestry"] == "South Asian / Indian"          # only what the caller supplied
    assert len(report.section_11_limitations_and_gaps) >= 4
    assert not report.section_6_literature_evidence.top_pubmed_references                # no template literature
    assert "18.4%" not in report.model_dump_json() and "1,029" not in report.model_dump_json()

    html = CaseReportGenerator.export_to_html(report)
    assert "<!DOCTYPE html>" in html
    assert "Prader-Willi Syndrome" in html
    assert "RESEARCH DISCLAIMER" in html
    assert "IndiGen: unavailable" in html


def test_html_export_escapes_untrusted_text():
    data = {"case_id": "X", "clinical_text": "<script>alert(1)</script> hypotonia", "fused_candidates": [{"disease_id": "D:1", "disease_name": "<img src=x onerror=alert(2)>", "final_score": 0.5}]}
    html = CaseReportGenerator.export_to_html(CaseReportGenerator.generate_report(data))
    assert "<script>alert(1)" not in html and "<img src=x" not in html
    assert "&lt;script&gt;" in html
