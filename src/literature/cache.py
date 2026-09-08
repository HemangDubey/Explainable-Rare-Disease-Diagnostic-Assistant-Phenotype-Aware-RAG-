"""Local disk caching for PubMed queries and articles to adhere to NCBI E-Utilities policies."""

import os
import json
import hashlib
from typing import Optional, Dict, Any, List
from pathlib import Path


class LiteratureCache:
    """Manages persistent cache of PubMed searches and article payloads in data/cache/pubmed/."""

    def __init__(self, cache_dir: str = "data/cache/pubmed"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.queries_dir = self.cache_dir / "queries"
        self.articles_dir = self.cache_dir / "articles"
        self.queries_dir.mkdir(exist_ok=True)
        self.articles_dir.mkdir(exist_ok=True)

    def _hash_key(self, key: str) -> str:
        return hashlib.sha256(key.strip().lower().encode("utf-8")).hexdigest()

    def get_query_results(self, query: str) -> Optional[List[str]]:
        """Returns cached list of PMIDs for a search query string if available."""
        h = self._hash_key(query)
        cache_file = self.queries_dir / f"{h}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("pmids", [])
            except Exception:
                return None
        return None

    def set_query_results(self, query: str, pmids: List[str]) -> None:
        """Saves search query result PMIDs to cache."""
        h = self._hash_key(query)
        cache_file = self.queries_dir / f"{h}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"query": query, "pmids": pmids}, f, indent=2)
        except Exception:
            pass

    def get_article(self, pmid: str) -> Optional[Dict[str, Any]]:
        """Returns cached article dict by PMID."""
        cache_file = self.articles_dir / f"{pmid}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def set_article(self, pmid: str, article_data: Dict[str, Any]) -> None:
        """Saves article data dict by PMID."""
        cache_file = self.articles_dir / f"{pmid}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(article_data, f, indent=2)
        except Exception:
            pass
