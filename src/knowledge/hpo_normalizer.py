import os
import json
import yaml
import re
from pathlib import Path

class HPONormalizer:
    def __init__(self, config_path="configs/config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        hpo_json_path = Path(self.config["hpo"]["processed_dir"]) / self.config["hpo"]["terms_json"]
        if not hpo_json_path.exists():
            from src.knowledge.build_hpo_knowledge_base import build_knowledge_base
            build_knowledge_base(config_path)

        with open(hpo_json_path, "r", encoding="utf-8") as f:
            self.hpo_terms = json.load(f)

        self.exact_name_map = {}
        self.lower_name_map = {}
        self.synonym_map = {}

        for hpo_id, data in self.hpo_terms.items():
            name = data.get("name", "").strip()
            if name:
                self.exact_name_map[name] = (hpo_id, name)
                self.lower_name_map[name.lower()] = (hpo_id, name)

            for syn in data.get("synonyms", []):
                syn_clean = syn.strip().lower()
                if syn_clean and syn_clean not in self.synonym_map:
                    self.synonym_map[syn_clean] = (hpo_id, name)

        self._term_ids = list(self.hpo_terms.keys())

    def normalize(self, query_text, top_k=3):
        query_clean = query_text.strip()
        query_lower = re.sub(r'[^\w\s]', '', query_clean.lower()).strip()

        # Tier 1: Exact Name
        if query_clean in self.exact_name_map:
            hpo_id, name = self.exact_name_map[query_clean]
            return [{"hpo_id": hpo_id, "name": name, "score": 1.0, "matching_method": "exact_name"}]

        # Tier 2: Case-insensitive Name / Punctuation-stripped Name
        if query_lower in self.lower_name_map:
            hpo_id, name = self.lower_name_map[query_lower]
            return [{"hpo_id": hpo_id, "name": name, "score": 1.0, "matching_method": "case_insensitive_name"}]

        # Tier 3: Synonym Match
        if query_lower in self.synonym_map:
            hpo_id, name = self.synonym_map[query_lower]
            return [{"hpo_id": hpo_id, "name": name, "score": 0.95, "matching_method": "synonym_exact"}]

        # Substring / Keyword Match
        for name_l, (h_id, name_orig) in self.lower_name_map.items():
            if query_lower and (query_lower in name_l or name_l in query_lower):
                return [{"hpo_id": h_id, "name": name_orig, "score": 0.88, "matching_method": "partial_text_match"}]

        # Fast Fallback
        first_id = self._term_ids[0]
        return [{"hpo_id": first_id, "name": self.hpo_terms[first_id]["name"], "score": 0.50, "matching_method": "fallback"}]

if __name__ == "__main__":
    normalizer = HPONormalizer()
    print(normalizer.normalize("hypotonia"))
