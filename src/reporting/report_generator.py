"""Clinical Case Report Generator (Phase 6 Module 16), rebuilt in Phase 6R so every statement is derived from the case's computed data.

Nothing here is invented: no default patient demographics, no template literature, no fixed fusion weights or "rank adjustments",
no test / treatment / referral recommendations. Items the system does not compute are reported as "not provided" / "not assessed".
All user-supplied and model-derived text is HTML-escaped in the export.
"""
import html
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.reporting.report_schema import (
    CandidateSummaryItem, CounterfactualSensitivitySummary, ClinicalCaseReport, ClinicalNextSteps, IndianGeneticsContext,
    LiteratureEvidenceSummary, ReportHeader)

NOT_PROVIDED = "Not provided"
NOT_ASSESSED = "Not assessed by this system"
e = html.escape


def _pop_note(c: Dict[str, Any]) -> Optional[str]:
    pop = c.get("population") or {}
    if not isinstance(pop, dict) or not pop:
        return None
    genes = ", ".join(c.get("genes", [])) or "no associated gene"
    if pop.get("status") != "available":
        return f"{c.get('disease_name')} ({genes}): population frequency evidence {pop.get('status', 'unavailable')}."
    sas, glob = (pop.get("gnomad_south_asian") or {}), (pop.get("gnomad_global") or {})
    ind = pop.get("indigen") or {}
    ind_txt = f"; IndiGen {ind.get('caf')}" if ind.get("status") == "available" and ind.get("caf") is not None else ""
    return (f"{c.get('disease_name')} ({genes}): gnomAD v4.1 gene-level cumulative allele frequency of ClinVar pathogenic/likely-pathogenic variants — "
            f"South Asian {sas.get('caf')}, global {glob.get('caf')}{ind_txt}. Frequency is evidence about the population, not a disease probability.")


def _indigen_status(raw) -> str:
    """'available' only if the ranking run actually carried IndiGen evidence for some candidate; never inferred from other sources."""
    states = {((c.get("population") or {}).get("indigen") or {}).get("status") for c in raw or [] if isinstance(c, dict)}
    return "available" if "available" in states else "unavailable"


class CaseReportGenerator:
    """Synthesizes the case's computed results into a structured 11-section report (no template clinical content)."""

    @classmethod
    def generate_report(cls, case_data: Dict[str, Any], literature_summary: Optional[Dict[str, Any]] = None,
                        report_id: Optional[str] = None, indigen_demo_appendix: Optional[Dict[str, Any]] = None) -> ClinicalCaseReport:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        rep_id = report_id or f"CR-{uuid.uuid4().hex[:8].upper()}"

        clinical_text = case_data.get("clinical_text", "")
        meta = case_data.get("patient_metadata", {}) or {}
        sec1 = {
            "presentation_summary": clinical_text[:600] + ("..." if len(clinical_text) > 600 else ""),
            "full_clinical_presentation": clinical_text,
            "patient_age": meta.get("age", NOT_PROVIDED), "patient_gender": meta.get("gender", NOT_PROVIDED),
            "ancestry": meta.get("ancestry", NOT_PROVIDED), "consanguinity": meta.get("consanguinity", NOT_PROVIDED),
        }

        extracted = case_data.get("extracted_phenotypes") or case_data.get("phenotypes", [])
        hpo_terms = case_data.get("hpo_terms", [])
        sec2 = {"total_extracted_phenotypes": len(extracted), "phenotypes": extracted, "mapped_hpo_terms": hpo_terms}

        raw = case_data.get("fused_candidates") or case_data.get("ranked_candidates", [])
        top: List[CandidateSummaryItem] = []
        for idx, c in enumerate(raw[:5]):
            f_score = float(c.get("final_score", c.get("score", 0.0)) or 0.0)
            p_ev = c.get("phenotype_evidence", c.get("phenotype_score", 0.0))
            p_score = float(p_ev.get("score", 0.0)) if isinstance(p_ev, dict) else float(p_ev or 0.0)
            r_ev = c.get("retrieval_evidence", c.get("retrieval_score", 0.0))
            r_score = float(r_ev.get("score", 0.0)) if isinstance(r_ev, dict) else float(r_ev or 0.0)
            # the population CONTRIBUTION to the final score (0.0 while w_population = 0), never the raw signal
            pop_contrib = c.get("population_contribution")
            pop_score = float(pop_contrib) if isinstance(pop_contrib, (int, float)) else 0.0
            label = (c.get("labels") or {}).get("label") or (p_ev.get("label") if isinstance(p_ev, dict) else None) or "Descriptive label unavailable"

            clean_ev: List[str] = []
            for itm in c.get("evidence_items", []):
                if isinstance(itm, dict):
                    clean_ev.append(itm.get("description") or itm.get("aspect") or str(itm))
                elif isinstance(itm, str):
                    clean_ev.append(itm)
            if not clean_ev:
                clean_ev = [f"Phenotype overlap score: {round(p_score, 3)}"]

            matched: List[str] = []
            for p in c.get("matched_hpo_ids") or c.get("matched_phenotypes", []) or (p_ev.get("matched_phenotypes", []) if isinstance(p_ev, dict) else []):
                if isinstance(p, dict):
                    matched.append(p.get("name") or p.get("hpo_id") or str(p))
                elif isinstance(p, str):
                    matched.append(p)
            top.append(CandidateSummaryItem(
                rank=idx + 1, disease_id=c.get("disease_id", f"DIS-{idx + 1}"), disease_name=c.get("disease_name", f"Candidate {idx + 1}"),
                final_score=round(f_score, 4), phenotype_score=round(p_score, 4), retrieval_score=round(r_score, 4), population_score=round(pop_score, 4),
                matched_phenotypes=matched, genes=c.get("genes", []), key_evidence=clean_ev[:4], confidence_tier=label))

        # 4. fusion: report the weights the ranking really used
        sb = ((raw[0] or {}).get("score_breakdown") or {}) if raw else {}
        w = sb.get("weights") or {}
        sec4 = {
            "fusion_weights": {"phenotype_weight": w.get("w_phenotype"), "retrieval_weight": w.get("w_retrieval"), "population_weight": w.get("w_population")},
            "fusion_model": "Phase 3R ranking: weighted phenotype + retrieval score; population weight configured separately",
            "top_candidate_name": top[0].disease_name if top else "None", "composite_score": top[0].final_score if top else 0.0,
            "note": "Scores are rank-based prioritization scores, not probabilities. Weights are taken from the ranking run; 'None' means the case data did not include them.",
        }

        # 5. population context: real values only
        weight = w.get("w_population")
        notes = [n for n in (_pop_note(c) for c in raw[:5]) if n]
        ind_status = _indigen_status(raw)
        sec5 = IndianGeneticsContext(
            population_priors_applied=bool(weight) and weight > 0,
            relevant_subpopulations=["gnomAD v4.1 South Asian (SAS) — not an India-specific dataset", "gnomAD v4.1 global",
                                     "IndiGen — available (authorised export)" if ind_status == "available"
                                     else "IndiGen — UNAVAILABLE (no verified access to the data)"],
            carrier_frequency_notes=notes or ["No population-frequency evidence was available for these candidates."],
            founder_mutation_evidence=[],
            indigen_gnomad_comparison={"indigen": ind_status, "population_weight_in_ranking": weight,
                                       "effect_on_ranking": "none" if not weight else "see score breakdown"})

        # 6. literature: only what the literature module returned for this case
        lit = literature_summary or {}
        sec6 = LiteratureEvidenceSummary(
            total_papers_analyzed=int(lit.get("total_articles", 0) or 0), top_pubmed_references=list(lit.get("top_articles", [])),
            phenotype_matrix_preview=list(lit.get("matrix_preview", [])), indian_cohort_studies=list(lit.get("indian_cohort_articles", [])))

        # 7. reasoning: factual statements about the computed ranking
        te = case_data.get("top_explanation") or {}
        if top:
            t0 = top[0]
            summary = (te.get("summary") if isinstance(te.get("summary"), str) and not te.get("fallback") else None) or (
                f"{t0.disease_name} was ranked first by the computational pipeline (final score {t0.final_score}; descriptive label: {t0.confidence_tier}). "
                "This is a prioritization, not a diagnosis.")
        else:
            summary = "No candidate was produced for this case."
        sec7 = {"executive_summary": summary,
                "hallmark_features": [f"Patient findings matched to annotations of {top[0].disease_name}: " + (", ".join(top[0].matched_phenotypes[:6]) or "none")] if top else [],
                "mechanistic_pathway": NOT_ASSESSED}

        # 8. differential: real comparison data when available
        diff = case_data.get("differential") or {}
        matrix = diff.get("comparisons") or diff.get("comparison") or [
            {"disease": c.disease_name, "rank": c.rank, "overlap_pct": f"{int(c.phenotype_score * 100)}%",
             "distinguishing_feature": "Phenotypes annotated to this disease but not stated in the record are listed in the evidence cards (annotations, not patient findings)."}
            for c in top[:3]]
        sec8 = {"differential_matrix": matrix, "discriminative_testing": "Not generated: this system does not recommend tests."}

        # 9. counterfactual: not computed here
        sec9 = CounterfactualSensitivitySummary(
            rank_stability_score=None, critical_anchor_phenotypes=[], borderline_phenotypes=[], top_counterfactual_shifts=[],
            note="Not computed for this report. Use the Counterfactual Lab; its results are hypothetical sensitivity analyses.")

        # 10. no recommendations
        sec10 = ClinicalNextSteps(confirmatory_genetic_tests=[], biochemical_metabolic_workup=[], multidisciplinary_referrals=[], contraindicated_treatments=[],
                                  note="Intentionally empty: this system does not recommend tests, treatment, referrals or contraindications. Any such decision belongs to the treating clinician.")

        sec11 = [
            "Phenotype extraction uses NLP on the supplied note; it does not reliably detect negation, so negated findings may appear as phenotypes.",
            ("IndiGen data are unavailable. " if ind_status != "available" else "IndiGen evidence comes from an authorised export and is reported under its own name. ")
            + "gnomAD South Asian frequencies are not an India-specific reference; "
            + ("the population weight is 0, so population evidence does not change the ranking." if not weight else f"the population weight is {weight}."),
            "Ranking scores come from simulated-query retrieval design choices and are not calibrated probabilities; no expert-labelled clinical validation exists.",
            "Literature evidence is limited to what the literature module retrieved for this case; absence of articles does not mean absence of evidence.",
            "This report is a computational prioritization aid and is not a diagnosis; it requires interpretation by a qualified clinician and molecular confirmation.",
        ]
        return ClinicalCaseReport(
            header=ReportHeader(report_id=rep_id, generated_at=now_str), section_1_case_summary=sec1, section_2_phenotype_extraction=sec2,
            section_3_top_differentials=top, section_4_evidence_fusion=sec4, section_5_indian_population_context=sec5, appendix_indigen_demo=indigen_demo_appendix, section_6_literature_evidence=sec6,
            section_7_explainable_reasoning=sec7, section_8_differential_diagnosis=sec8, section_9_counterfactual_sensitivity=sec9,
            section_10_recommended_workup=sec10, section_11_limitations_and_gaps=sec11)

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _demo_appendix_html(app, e) -> str:
        if not app:
            return ""
        rows = "".join(f"<tr><td style='padding:6px;font-family:monospace;'>{e(str(g.get('gene')))}</td><td style='padding:6px;'>{e(str(g.get('status')))}</td>"
                       f"<td style='padding:6px;font-family:monospace;'>{e('%.3e' % g['demo_caf']) if g.get('demo_caf') is not None else '—'}</td>"
                       f"<td style='padding:6px;'>{e(str(g.get('n_variants') or 0))}</td></tr>" for g in app.get("genes", []))
        return f"""<div style="margin-top:28px;padding:14px;border:2px dashed #c026d3;border-radius:8px;
background:repeating-linear-gradient(45deg,#fdf4ff,#fdf4ff 10px,#fae8ff 10px,#fae8ff 20px);">
<div style="font-weight:800;color:#86198f;font-size:14px;">APPENDIX — {e(app.get('label', ''))}</div>
<div style="font-size:12px;color:#701a75;margin:6px 0;">{e(app.get('statement', ''))} {e(app.get('note', ''))}</div>
<table><tr><th>Gene</th><th>Demo status</th><th>Simulated cumulative AF</th><th>Demo records</th></tr>{rows}</table>
<div style="font-size:11px;color:#701a75;">Generator: {e(str(app.get('generator', '')))} · seed {e(str(app.get('seed', '')))}</div></div>"""

    @classmethod
    def export_to_html(cls, report: ClinicalCaseReport) -> str:
        """Print-ready HTML. Every dynamic value is escaped."""
        rows = "".join(
            f"""<tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding:10px;font-weight:bold;">#{c.rank}</td>
            <td style="padding:10px;"><div style="font-weight:600;color:#1e293b;">{e(c.disease_name)}</div>
            <div style="font-size:12px;color:#64748b;">ID: {e(c.disease_id)} | Genes: {e(', '.join(c.genes)) if c.genes else 'none recorded'}</div></td>
            <td style="padding:10px;text-align:center;">{c.final_score:.4f}</td><td style="padding:10px;text-align:center;">{c.phenotype_score:.4f}</td>
            <td style="padding:10px;text-align:center;">{c.population_score:+.4f}</td>
            <td style="padding:10px;font-size:12px;">{e(c.confidence_tier)}</td></tr>""" for c in report.section_3_top_differentials)
        lit_blocks = []
        for p in report.section_6_literature_evidence.top_pubmed_references[:4]:
            pmid = str(p.get("pmid", ""))
            url = e(str(p.get("url") or f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"))
            lit_blocks.append(f"""<div style="margin-bottom:12px;padding:10px;background:#f8fafc;border-left:3px solid #3b82f6;">
            <div style="font-weight:600;font-size:13px;"><a href="{url}" target="_blank" rel="noopener noreferrer">{e(str(p.get('title', 'PubMed publication')))}</a></div>
            <div style="font-size:11px;color:#64748b;">PMID: {e(pmid)} | {e(str(p.get('journal', '')))} ({e(str(p.get('pub_year') or p.get('year', '')))})</div></div>""")
        literature_html = "".join(lit_blocks) or '<p style="font-size:13px;color:#64748b;">No literature was retrieved for this case.</p>'
        hpo_tags = "".join(
            f"""<span style="display:inline-block;background:#f1f5f9;border:1px solid #cbd5e1;border-radius:4px;padding:3px 8px;margin:3px;font-size:12px;">
            <b>{e(str(h.get('name') or h.get('term', '')))}</b> <span style="color:#64748b;">({e(str(h.get('hpo_id') or h.get('id', '')))})</span></span>"""
            for h in report.section_2_phenotype_extraction.get("mapped_hpo_terms", []))
        s1 = report.section_1_case_summary
        notes = "".join(f"<li>{e(n)}</li>" for n in report.section_5_indian_population_context.carrier_frequency_notes)
        lims = "".join(f"<li>{e(x)}</li>" for x in report.section_11_limitations_and_gaps)
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Clinical Case Report - {e(report.header.report_id)}</title>
<style>
body {{ font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color:#1e293b; margin:0; padding:40px; line-height:1.5; }}
.report-card {{ max-width:900px; margin:0 auto; border:1px solid #e2e8f0; border-radius:10px; padding:36px; }}
.header {{ border-bottom:2px solid #0284c7; padding-bottom:20px; margin-bottom:24px; display:flex; justify-content:space-between; }}
.title {{ font-size:22px; font-weight:700; }} .subtitle {{ font-size:13px; color:#64748b; margin-top:4px; }}
.meta-tag {{ font-size:12px; background:#f0f9ff; color:#0369a1; padding:4px 10px; border-radius:6px; border:1px solid #bae6fd; }}
.section-heading {{ font-size:15px; font-weight:700; color:#0369a1; text-transform:uppercase; margin-top:28px; margin-bottom:12px; border-bottom:1px solid #f1f5f9; padding-bottom:6px; }}
table {{ width:100%; border-collapse:collapse; margin:10px 0 16px; }} th {{ background:#f8fafc; padding:8px 10px; font-size:12px; text-transform:uppercase; color:#475569; border-bottom:2px solid #cbd5e1; text-align:left; }}
.disclaimer-box {{ margin-top:36px; padding:16px; background:#fffbeb; border:1px solid #fef3c7; border-left:4px solid #f59e0b; border-radius:6px; font-size:11px; color:#92400e; }}
@media print {{ body {{ padding:0; }} .report-card {{ border:none; padding:10px; }} button, .no-print {{ display:none; }} }}
</style></head>
<body><div class="report-card">
<div class="header"><div><div class="title">Clinical Diagnostic Prioritization Report</div>
<div class="subtitle">Computational research prototype — candidate prioritization, not diagnosis</div></div>
<div style="text-align:right;"><div class="meta-tag">REPORT: {e(report.header.report_id)}</div><div style="font-size:11px;color:#94a3b8;margin-top:4px;">{e(report.header.generated_at)}</div></div></div>
<div class="section-heading">1. Case summary</div>
<div style="background:#f8fafc;padding:14px;border-radius:6px;font-size:13px;"><p style="margin-top:0;"><b>Clinical text:</b> {e(str(s1.get('full_clinical_presentation')))}</p>
<div style="font-size:12px;color:#64748b;">Age: {e(str(s1.get('patient_age')))} · Sex: {e(str(s1.get('patient_gender')))} · Ancestry: {e(str(s1.get('ancestry')))} · Consanguinity: {e(str(s1.get('consanguinity')))}</div></div>
<div class="section-heading">2. Phenotypes and HPO terms</div><div>{hpo_tags or '<p style="font-size:13px;color:#64748b;">No HPO terms were mapped.</p>'}</div>
<div class="section-heading">3. Prioritized candidates (not diagnoses)</div>
<table><thead><tr><th>Rank</th><th>Disease and genes</th><th style="text-align:center;">Final score</th><th style="text-align:center;">Phenotype score</th><th style="text-align:center;">Population contribution</th><th>Descriptive label</th></tr></thead><tbody>{rows}</tbody></table>
<p style="font-size:11px;color:#64748b;">Scores are rank-based and uncalibrated; they are not probabilities.</p>
<div class="section-heading">4. Population-frequency context</div>
<div style="background:#f0fdf4;border-left:3px solid #22c55e;padding:12px;font-size:12px;color:#166534;"><div style="font-weight:600;">IndiGen: {e(str(report.section_5_indian_population_context.indigen_gnomad_comparison.get('indigen', 'unavailable')))} · gnomAD South Asian is not India-specific · population weight in ranking: {e(str(report.section_4_evidence_fusion.get('fusion_weights', {}).get('population_weight')))}</div><ul style="margin:6px 0 0;padding-left:20px;">{notes}</ul></div>
<div class="section-heading">5. Literature</div><div>{literature_html}</div>
<div class="section-heading">6. Reasoning summary</div>
<div style="font-size:13px;background:#f8fafc;padding:14px;border-radius:6px;"><p style="margin:0;">{e(str(report.section_7_explainable_reasoning.get('executive_summary')))}</p></div>
<div class="section-heading">7. Tests, treatment and referrals</div>
<p style="font-size:12px;color:#475569;">{e(report.section_10_recommended_workup.note or '')}</p>
<div class="section-heading">8. Limitations</div><ul style="font-size:12px;color:#64748b;margin:0;padding-left:20px;">{lims}</ul>
{cls._demo_appendix_html(report.appendix_indigen_demo, e)}
<div class="disclaimer-box"><b>RESEARCH DISCLAIMER:</b><br>{e(report.disclaimer)}</div>
<div style="margin-top:24px;text-align:center;" class="no-print"><button onclick="window.print()" style="background:#0284c7;color:white;border:none;padding:8px 18px;border-radius:6px;font-weight:600;cursor:pointer;">Print / Save as PDF</button></div>
</div></body></html>
"""
