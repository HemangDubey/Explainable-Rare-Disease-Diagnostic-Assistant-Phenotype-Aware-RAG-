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
    assert report.section_5_indian_population_context.population_priors_applied is True
    assert len(report.section_10_recommended_workup.confirmatory_genetic_tests) > 0
    assert len(report.section_11_limitations_and_gaps) == 4

    html = CaseReportGenerator.export_to_html(report)
    assert "<!DOCTYPE html>" in html
    assert "Prader-Willi Syndrome" in html
    assert "CONFIDENTIAL MEDICAL AI DECISION SUPPORT REPORT" in html
