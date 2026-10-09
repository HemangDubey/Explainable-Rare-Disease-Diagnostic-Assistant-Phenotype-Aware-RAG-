import os
import re
import json
import yaml
import pandas as pd
from pathlib import Path

def parse_hp_obo(obo_path):
    """
    Parses OBO format file and returns dict of HPO terms:
    {hpo_id: {hpo_id, name, definition, synonyms, is_a}}
    """
    hpo_terms = {}
    current_term = None

    if not Path(obo_path).exists():
        raise FileNotFoundError(f"hp.obo file not found at {obo_path}")

    with open(obo_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line == "[Term]":
                if current_term and "id" in current_term and current_term["id"].startswith("HP:"):
                    hpo_terms[current_term["id"]] = current_term
                current_term = {
                    "hpo_id": "",
                    "name": "",
                    "definition": "",
                    "synonyms": [],
                    "is_a": [],
                    "alt_ids": [],
                    "is_obsolete": False,
                    "replaced_by": []
                }
            elif line.startswith("[") and line.endswith("]"):
                if current_term and "id" in current_term and current_term["id"].startswith("HP:"):
                    hpo_terms[current_term["id"]] = current_term
                current_term = None
            elif current_term is not None:
                if line.startswith("id:"):
                    current_term["id"] = line.split("id:")[1].strip()
                    current_term["hpo_id"] = current_term["id"]
                elif line.startswith("name:"):
                    current_term["name"] = line.split("name:")[1].strip()
                elif line.startswith("def:"):
                    # Extract definition string between quotes
                    match = re.search(r'"([^"]*)"', line)
                    if match:
                        current_term["definition"] = match.group(1)
                elif line.startswith("synonym:"):
                    match = re.search(r'"([^"]*)"', line)
                    if match:
                        current_term["synonyms"].append(match.group(1))
                elif line.startswith("alt_id:"):
                    current_term["alt_ids"].append(line.split("alt_id:")[1].strip())
                elif line.startswith("is_obsolete:"):
                    current_term["is_obsolete"] = line.split("is_obsolete:")[1].strip().lower() == "true"
                elif line.startswith("replaced_by:"):
                    current_term["replaced_by"].append(line.split("replaced_by:")[1].strip())
                elif line.startswith("is_a:"):
                    parent_id = line.split("is_a:")[1].strip().split()[0]
                    current_term["is_a"].append(parent_id)

    if current_term and "id" in current_term and current_term["id"].startswith("HP:"):
        hpo_terms[current_term["id"]] = current_term

    return hpo_terms

def parse_disease_annotations(hpoa_path, genes_path, hpo_terms):
    """
    Parses phenotype.hpoa and phenotype_to_genes.txt to build disease knowledge base.
    Returns dict of disease records:
    {disease_id: {disease_id, disease_name, hpo_ids, hpo_names, genes, source_db}}
    """
    disease_kb = {}

    # Parse phenotype.hpoa
    if Path(hpoa_path).exists():
        with open(hpoa_path, "r", encoding="utf-8", errors="ignore") as f:
            header = None
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if header is None:
                    header = parts
                    continue
                if len(parts) >= 4:
                    # Typical columns: database_id, disease_name, qualifier, hpo_id...
                    db_id = parts[0].strip() # e.g. OMIM:619340 or ORPHA:586
                    d_name = parts[1].strip() if len(parts) > 1 else ""
                    hpo_id = ""
                    for p in parts[2:]:
                        if p.startswith("HP:"):
                            hpo_id = p
                            break

                    if not db_id or not hpo_id:
                        continue

                    source_db = db_id.split(":")[0] if ":" in db_id else "UNKNOWN"

                    if db_id not in disease_kb:
                        disease_kb[db_id] = {
                            "disease_id": db_id,
                            "disease_name": d_name,
                            "hpo_ids": [],
                            "hpo_names": [],
                            "genes": [],
                            "source_db": source_db
                        }

                    if hpo_id not in disease_kb[db_id]["hpo_ids"]:
                        disease_kb[db_id]["hpo_ids"].append(hpo_id)
                        h_name = hpo_terms.get(hpo_id, {}).get("name", hpo_id)
                        disease_kb[db_id]["hpo_names"].append(h_name)

    # Parse phenotype_to_genes.txt if present
    if Path(genes_path).exists():
        with open(genes_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 4:
                    # hpo_id, hpo_name, gene_id, gene_symbol, disease_id ...
                    hpo_id = parts[0].strip()
                    gene_sym = parts[3].strip() if len(parts) > 3 else ""
                    db_id = parts[4].strip() if len(parts) > 4 else ""

                    if db_id and gene_sym and db_id in disease_kb:
                        if gene_sym not in disease_kb[db_id]["genes"]:
                            disease_kb[db_id]["genes"].append(gene_sym)

    return disease_kb

def build_knowledge_base(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    hpo_raw = Path(config["hpo"]["raw_dir"]) / config["hpo"]["obo_file"]
    hpo_proc_dir = Path(config["hpo"]["processed_dir"])
    hpo_proc_dir.mkdir(parents=True, exist_ok=True)

    disease_raw_hpoa = Path(config["disease"]["raw_dir"]) / config["disease"]["hpoa_file"]
    disease_raw_genes = Path(config["disease"]["raw_dir"]) / config["disease"]["genes_file"]
    disease_proc_dir = Path(config["disease"]["processed_dir"])
    disease_proc_dir.mkdir(parents=True, exist_ok=True)

    print("\n--- 1. Building HPO Terms Knowledge Base ---")
    hpo_terms = parse_hp_obo(hpo_raw)
    hpo_out_file = hpo_proc_dir / config["hpo"]["terms_json"]
    with open(hpo_out_file, "w", encoding="utf-8") as f:
        json.dump(hpo_terms, f, indent=2)
    print(f"Extracted {len(hpo_terms)} HPO terms -> saved to {hpo_out_file}")

    print("\n--- 2. Building Disease Knowledge Base ---")
    disease_kb = parse_disease_annotations(disease_raw_hpoa, disease_raw_genes, hpo_terms)
    disease_out_file = disease_proc_dir / config["disease"]["disease_kb_json"]
    with open(disease_out_file, "w", encoding="utf-8") as f:
        json.dump(disease_kb, f, indent=2)
    print(f"Extracted {len(disease_kb)} disease records -> saved to {disease_out_file}")

    # Summary Stats
    omim_count = sum(1 for d in disease_kb.values() if d["source_db"] == "OMIM")
    orpha_count = sum(1 for d in disease_kb.values() if d["source_db"] == "ORPHA")
    decipher_count = sum(1 for d in disease_kb.values() if d["source_db"] == "DECIPHER")

    print("\n=== KNOWLEDGE BASE SUMMARY ===")
    print(f"Total HPO Terms: {len(hpo_terms)}")
    print(f"Total Disease Records: {len(disease_kb)}")
    print(f"  - OMIM Diseases: {omim_count}")
    print(f"  - Orphanet Diseases: {orpha_count}")
    print(f"  - DECIPHER / Other Diseases: {decipher_count}")

    return hpo_terms, disease_kb

if __name__ == "__main__":
    build_knowledge_base()
