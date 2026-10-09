"""Phenotype phrase -> HPO term normalisation with explicit, honest statuses.

Cascade: ID -> exact name -> synonym -> lexical (token Jaccard) -> semantic (real S-PubMedBERT
embedding search over the HPO index). Possible statuses:

    exact | synonym | lexical | semantic | ambiguous | unmatched

An unmatched phrase is NEVER assigned a term (in particular never HP:0000001 "All"); an
ambiguous phrase returns all tied candidates instead of silently choosing one.
Obsolete HPO terms are not matchable; alternate IDs resolve to the current term.
"""
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import yaml

_STOP = {"of", "the", "a", "an", "and", "in", "with", "to", "or", "on", "at", "is"}
_ID_RE = re.compile(r"^HP:\d{7}$", re.IGNORECASE)
_RESOURCES = {}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _tok(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") and not token.endswith("ss") else token


def _tokens(text: str) -> frozenset:
    return frozenset(_tok(t) for t in _norm(text).split() if t not in _STOP)


class _Resources:
    def __init__(self, hpo_terms):
        self.terms = hpo_terms
        self.active = {i: t for i, t in hpo_terms.items() if not t.get("is_obsolete")}
        self._pheno_cache = {}
        self.alt = {}
        for i, t in hpo_terms.items():
            for a in t.get("alt_ids", []):
                self.alt[a] = i
        self.name_map = defaultdict(set)
        self.syn_map = defaultdict(set)
        self.labels = []                 # (hpo_id, token_frozenset)
        self.token_index = defaultdict(list)
        for i, t in self.active.items():
            self.name_map[_norm(t["name"])].add(i)
            for lab in [t["name"]] + t.get("synonyms", []):
                toks = _tokens(lab)
                if toks:
                    self.labels.append((i, toks))
                    for tk in toks:
                        self.token_index[tk].append(len(self.labels) - 1)
            for s in t.get("synonyms", []):
                self.syn_map[_norm(s)].add(i)

    def is_phenotypic(self, hid: str) -> bool:
        """True iff the term descends from HP:0000118 'Phenotypic abnormality'.
        Modifiers (e.g. 'Recurrent', frequency, inheritance terms) are not clinical findings."""
        if hid not in self._pheno_cache:
            seen, stack = set(), [hid]
            while stack:
                cur = stack.pop()
                if cur == "HP:0000118":
                    self._pheno_cache[hid] = True
                    return True
                for par in self.terms.get(cur, {}).get("is_a", []):
                    if par not in seen:
                        seen.add(par)
                        stack.append(par)
            self._pheno_cache[hid] = False
        return self._pheno_cache[hid]

    def resolve_id(self, hid: str) -> Optional[str]:
        hid = hid.upper()
        hid = self.alt.get(hid, hid)
        t = self.terms.get(hid)
        if t is None:
            return None
        if t.get("is_obsolete"):
            rep = [r for r in t.get("replaced_by", []) if r in self.active]
            return rep[0] if len(rep) == 1 else None
        return hid


def _get_resources(config):
    path = Path(config["hpo"]["processed_dir"]) / config["hpo"]["terms_json"]
    key = str(path.resolve())
    if key not in _RESOURCES:
        if not path.exists():
            from src.knowledge.build_hpo_knowledge_base import build_knowledge_base
            build_knowledge_base()
        _RESOURCES[key] = _Resources(json.load(open(path, encoding="utf-8")))
    return _RESOURCES[key]


class HPONormalizer:
    def __init__(self, config_path="configs/config.yaml", use_semantic=True, model_key="primary", search_engine=None):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        cfg = self.config.get("hpo_normalization", {})
        self.lexical_threshold = float(cfg.get("lexical_threshold", 0.75))
        self.semantic_threshold = float(cfg.get("semantic_threshold", 0.80))
        self.semantic_margin = float(cfg.get("semantic_margin", 0.0))
        self.semantic_top_k = int(cfg.get("semantic_top_k", 5))
        self.res = _get_resources(self.config)
        self.search = None
        if use_semantic:
            if search_engine is None:
                from src.retrieval.hpo_search import HPOSearchEngine
                search_engine = HPOSearchEngine(model_key=model_key, config_path=config_path)
            self.search = search_engine   # raises loudly if real embeddings are unavailable

    # ---- helpers -------------------------------------------------------------------------
    def _name(self, hid):
        return self.res.terms[hid]["name"]

    def _result(self, phrase, status, ids=None, score=0.0, method=None, suggestions=None):
        ids = ids or []
        res = {"input": phrase, "status": status, "hpo_id": None, "term": None,
               "score": float(score), "matching_method": method or status, "candidates": []}
        if status == "ambiguous":
            res["candidates"] = [{"hpo_id": i, "name": self._name(i)} for i in sorted(ids)]
            res["matching_method"] = "ambiguous"
        elif status != "unmatched":
            res["hpo_id"], res["term"] = ids[0], self._name(ids[0])
            res["is_phenotypic"] = self.res.is_phenotypic(ids[0])
        else:
            res["score"] = 0.0
            res["matching_method"] = "none"
            res["suggestions"] = suggestions or []
        return res

    def _lexical_stages(self, phrase):
        q = phrase.strip()
        if _ID_RE.match(q):
            hid = self.res.resolve_id(q)
            return self._result(phrase, "exact", [hid], 1.0, "id") if hid else self._result(phrase, "unmatched")
        qn = _norm(q)
        if not qn:
            return self._result(phrase, "unmatched")
        ids = self.res.name_map.get(qn)
        if ids:
            return self._result(phrase, "exact", list(ids), 1.0) if len(ids) == 1 else self._result(phrase, "ambiguous", ids, 1.0)
        ids = self.res.syn_map.get(qn)
        if ids:
            return self._result(phrase, "synonym", list(ids), 0.95) if len(ids) == 1 else self._result(phrase, "ambiguous", ids, 0.95)
        qt = _tokens(q)
        if qt:
            cand = set()
            for tk in qt:
                cand.update(self.res.token_index.get(tk, ()))
            best, best_ids = 0.0, set()
            for li in cand:
                hid, lt = self.res.labels[li]
                j = len(qt & lt) / len(qt | lt)
                if j > best + 1e-9:
                    best, best_ids = j, {hid}
                elif abs(j - best) <= 1e-9:
                    best_ids.add(hid)
            if best >= self.lexical_threshold:
                return (self._result(phrase, "lexical", list(best_ids), best) if len(best_ids) == 1
                        else self._result(phrase, "ambiguous", best_ids, best))
        return None

    # ---- public API ----------------------------------------------------------------------
    def normalize_many(self, phrases: List[str]) -> List[Dict]:
        results = [self._lexical_stages(p) for p in phrases]
        pending = [i for i, r in enumerate(results) if r is None]
        if pending and self.search is not None:
            vecs = self.search.store.encoder.encode([phrases[i] for i in pending])
            hits = self.search.search_vectors(vecs, self.semantic_top_k)
            for i, hs in zip(pending, hits):
                results[i] = self._semantic_decision(phrases[i], hs)
        for i in pending:
            if results[i] is None:
                results[i] = self._result(phrases[i], "unmatched")
        return results

    def _semantic_decision(self, phrase, hits):
        if not hits:
            return self._result(phrase, "unmatched")
        top = hits[0]
        if top["score"] < self.semantic_threshold:
            return self._result(phrase, "unmatched", suggestions=hits[:3])
        if self.semantic_margin > 0 and len(hits) > 1 and (top["score"] - hits[1]["score"]) < self.semantic_margin:
            tied = [h["hpo_id"] for h in hits if top["score"] - h["score"] < self.semantic_margin]
            return self._result(phrase, "ambiguous", tied, top["score"])
        return self._result(phrase, "semantic", [top["hpo_id"]], top["score"])

    def normalize_detailed(self, phrase: str) -> Dict:
        return self.normalize_many([phrase])[0]

    def normalize(self, query_text, top_k=1):
        """Backward-compatible API: list of matched terms (empty for unmatched/ambiguous)."""
        r = self.normalize_detailed(query_text)
        if r["status"] in ("exact", "synonym", "lexical", "semantic"):
            return [{"hpo_id": r["hpo_id"], "name": r["term"], "score": r["score"], "matching_method": r["matching_method"]}]
        return []


if __name__ == "__main__":
    n = HPONormalizer(use_semantic=False)
    for q in ["hypotonia", "developmental delay", "xyzzy blorp"]:
        print(n.normalize_detailed(q))
