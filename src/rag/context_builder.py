import json

def build_rag_context(clinical_text, extracted_phenotypes, hpo_mappings, candidate_diseases):
    context_data = {
        "clinical_case": clinical_text,
        "extracted_phenotypes": extracted_phenotypes,
        "hpo_normalized_evidence": hpo_mappings,
        "candidate_diseases": candidate_diseases
    }
    md = []
    md.append("=== CLINICAL CASE OBSERVATION ===")
    md.append(clinical_text)
    md.append("")
    md.append("=== EXTRACTED PHENOTYPES (NER) ===")
    for p in extracted_phenotypes:
        p_t = p.get("phenotype", p)
        md.append(f"- Mention: {p_t} (Span: {p.get('span', 'N/A')})")

    md.append("")
    md.append("=== HPO NORMALIZATION EVIDENCE ===")
    for h in hpo_mappings:
        md.append(f"- Term: {h.get('name')} [{h.get('hpo_id')}] (Method: {h.get('matching_method')}, Score: {h.get('score')})")

    md.append("")
    md.append("=== RETRIEVED CANDIDATE DISEASES ===")
    for idx, d in enumerate(candidate_diseases, 1):
        md.append(f"[{idx}] {d.get('disease_name')} ({d.get('disease_id')}) - Source: {d.get('source_db')}")
        md.append(f"    Vector Sim: {d.get('embedding_similarity')} | HPO Match: {d.get('hpo_match_score')}")
        if d.get("matched_hpo_ids"):
            md.append(f"    Matched HPO Terms: {', '.join(d.get('matched_hpo_ids'))}")
        if d.get("associated_genes"):
            md.append(f"    Associated Genes: {', '.join(d.get('associated_genes'))}")

    context_data["structured_markdown_context"] = "\n".join(md)
    return context_data
