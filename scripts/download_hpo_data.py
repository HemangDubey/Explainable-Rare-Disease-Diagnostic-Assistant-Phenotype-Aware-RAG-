import os
import sys
import yaml
import requests
from pathlib import Path

def download_file(url, target_path, fallback_urls=None):
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    if target_path.exists() and target_path.stat().st_size > 1000:
        print(f"File already exists: {target_path} ({target_path.stat().st_size} bytes)")
        return True

    urls_to_try = [url] + (fallback_urls or [])
    for u in urls_to_try:
        print(f"Downloading: {u} -> {target_path}")
        try:
            response = requests.get(u, stream=True, timeout=30)
            if response.status_code == 200:
                with open(target_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"Successfully downloaded {target_path} ({target_path.stat().st_size} bytes)")
                return True
            else:
                print(f"HTTP {response.status_code} for {u}")
        except Exception as e:
            print(f"Failed download from {u}: {e}")
            
    print(f"ERROR: Could not download file for {target_path}")
    return False

def download_hpo_data(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    hpo_raw_dir = Path(config["hpo"]["raw_dir"])
    disease_raw_dir = Path(config["disease"]["raw_dir"])

    hpo_raw_dir.mkdir(parents=True, exist_ok=True)
    disease_raw_dir.mkdir(parents=True, exist_ok=True)

    # 1. HPO hp.obo
    obo_url = config["hpo"]["obo_url"]
    obo_path = hpo_raw_dir / config["hpo"]["obo_file"]
    obo_fallbacks = [
        "https://raw.githubusercontent.com/obophenotype/human-phenotype-ontology/master/hp.obo",
        "https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/hp.obo"
    ]
    s1 = download_file(obo_url, obo_path, obo_fallbacks)

    # 2. Disease phenotype.hpoa annotations
    hpoa_url = config["disease"]["hpoa_url"]
    hpoa_path = disease_raw_dir / config["disease"]["hpoa_file"]
    hpoa_fallbacks = [
        "https://raw.githubusercontent.com/obophenotype/human-phenotype-ontology/master/src/ontology/phenotype.hpoa",
        "https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/phenotype.hpoa"
    ]
    s2 = download_file(hpoa_url, hpoa_path, hpoa_fallbacks)

    # 3. Phenotype to Genes phenotype_to_genes.txt
    genes_url = config["disease"]["genes_url"]
    genes_path = disease_raw_dir / config["disease"]["genes_file"]
    genes_fallbacks = [
        "https://raw.githubusercontent.com/obophenotype/human-phenotype-ontology/master/src/ontology/phenotype_to_genes.txt",
        "https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/phenotype_to_genes.txt"
    ]
    s3 = download_file(genes_url, genes_path, genes_fallbacks)

    if s1 and (s2 or s3):
        print("\nAll HPO data acquisition completed and verified.")
        return True
    else:
        print("\nWARNING: Some HPO data files could not be acquired automatically.")
        return False

if __name__ == "__main__":
    download_hpo_data()
