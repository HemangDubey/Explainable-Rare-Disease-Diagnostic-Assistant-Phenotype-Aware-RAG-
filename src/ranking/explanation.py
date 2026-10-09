import json

def generate_ranking_explanation(ranked_candidate):
    """
    Generates structured, clinically safe human-readable evidence explanations for a ranked candidate disease.
    Follows strict non-diagnostic safety guidelines.
    """
    d_name = ranked_candidate.get("disease_name", "Unknown Disease")
    d_id = ranked_candidate.get("disease_id", "")
    p_score = ranked_candidate.get("phenotype_score", 0.0)
    r_score = ranked_candidate.get("retrieval_score", 0.0)
    ind_signal = ranked_candidate.get("indian_population_signal")
    gno_signal = ranked_candidate.get("global_population_signal")
    contrib = ranked_candidate.get("population_contribution")
    rank_change = ranked_candidate.get("rank_change")
    final_score = ranked_candidate.get("final_score", 0.0)
    matched_hpo = ranked_candidate.get("matched_hpo_ids", [])
    genes = ranked_candidate.get("associated_genes", [])
    status = ranked_candidate.get("population_evidence_status", "unavailable")

    lines = []
    lines.append(f"PRIORITIZED CANDIDATE [{ranked_candidate.get('rank', 'N/A')}]: {d_name} ({d_id})")
    lines.append(f"Overall Composite Priority Score: {final_score:.4f}")

    # 1. Phenotype Evidence
    lines.append(f"  • Phenotype Evidence (Score: {p_score:.4f}):")
    if matched_hpo:
        lines.append(f"    Matches {len(matched_hpo)} extracted HPO term(s): {', '.join(matched_hpo)}.")
    else:
        lines.append(f"    No direct HPO term overlap identified with current extracted phenotypes.")

    # 2. Dense Semantic Retrieval Evidence
    lines.append(f"  • Dense Retrieval Evidence (Score: {r_score:.4f}):")
    lines.append(f"    Score reflects HPO-level semantic similarity between the patient's phenotypes and the disease's annotated phenotypes.")

    # 3. Population Evidence
    fmt = lambda x: "unavailable" if x is None else f"{x:.3f}"
    sas_signal = ranked_candidate.get("south_asian_population_signal")
    # Each source is reported under its own name. IndiGen is only listed when an authorised export supplied a value; gnomAD South Asian
    # is never relabelled as Indian data.
    parts = [f"gnomAD global: {fmt(gno_signal)}", f"gnomAD South Asian (not India-specific): {fmt(sas_signal)}",
             f"IndiGen: {fmt(ind_signal)}" if ind_signal is not None else "IndiGen: unavailable (access required; nothing substituted)"]
    lines.append(f"  • Population Evidence ({'; '.join(parts)}):")
    if contrib is not None:
        lines.append(f"    Population evidence contributed {contrib:+.4f} to the final score"
                     + (f" and moved the candidate {abs(rank_change)} place(s) {'up' if rank_change > 0 else 'down'}." if rank_change else " (no rank change)."))
    if status == "available":
        lines.append(f"    Gene-level population frequency evidence found for: {', '.join(genes)}.")
    elif status == "not_found":
        lines.append(f"    No usable population frequency record for associated gene(s): {', '.join(genes) or 'none'}. No adjustment applied.")
    else:
        lines.append(f"    Population evidence unavailable. No adjustment applied.")

    # 4. Clinical Limitations & Disclaimer
    lines.append(f"  • Scientific & Diagnostic Limitations:")
    lines.append(f"    Population allele frequency reflects ancestral genetic prevalence and DOES NOT establish disease causality or diagnosis.")
    lines.append(f"    This output is an evidence-supported research prioritization candidate and REQUIRES explicit clinical and molecular genetic confirmation.")

    return "\n".join(lines)

if __name__ == "__main__":
    dummy = {
        "rank": 1,
        "disease_name": "Neurodevelopmental disorder with hypotonia and seizures",
        "disease_id": "OMIM:620790",
        "phenotype_score": 0.5,
        "retrieval_score": 0.9469,
        "indian_population_signal": 0.6412,
        "global_population_signal": 0.5210,
        "final_score": 0.7812,
        "matched_hpo_ids": ["HP:0001252", "HP:0001263"],
        "associated_genes": ["OTUD7A"],
        "population_evidence_status": "available"
    }
    print(generate_ranking_explanation(dummy))
