"""Semantic relevance scoring for literature using S-PubMedBERT or cosine similarity."""

import re
import numpy as np
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)


class LiteratureRelevanceScorer:
    """Scores PubMed articles against a disease profile and patient phenotype text."""

    def __init__(self, model_name: str = "pritamdeka/S-PubMedBERT-MS-MARCO"):
        self.model_name = model_name
        self._model = None
        self._initialized = False

    def _lazy_init(self):
        if not self._initialized:
            try:
                import torch
                # If CUDA is available or model is already locally cached, load it
                if torch.cuda.is_available():
                    from sentence_transformers import SentenceTransformer
                    self._model = SentenceTransformer(self.model_name)
                else:
                    # Instant lexical scoring for responsive CPU / local operation
                    self._model = None
            except Exception as e:
                logger.warning(f"SentenceTransformer not loaded for literature scoring ({e}). Using lexical fallback.")
                self._model = None
            self._initialized = True

    def compute_similarity(self, query_text: str, document_texts: List[str]) -> List[float]:
        """Calculates semantic similarity between query and list of documents."""
        self._lazy_init()

        if not document_texts:
            return []

        if self._model is not None:
            try:
                q_emb = self._model.encode(query_text, convert_to_numpy=True)
                doc_embs = self._model.encode(document_texts, convert_to_numpy=True)

                # Normalize and calculate dot product (cosine similarity)
                q_norm = q_emb / (np.linalg.norm(q_emb) + 1e-9)
                doc_norms = doc_embs / (np.linalg.norm(doc_embs, axis=1, keepdims=True) + 1e-9)
                sims = np.dot(doc_norms, q_norm)
                # Clip into 0.0 - 1.0 range
                return [float(np.clip((s + 1.0) / 2.0, 0.0, 1.0)) for s in sims]
            except Exception as e:
                logger.warning(f"Model encoding failed: {e}. Falling back to lexical.")

        # Lexical Jaccard/Overlap fallback if model unavailable or failed
        return [self._lexical_overlap_score(query_text, doc) for doc in document_texts]

    def _lexical_overlap_score(self, query: str, document: str) -> float:
        """Calculates normalized token overlap between query and document text."""
        q_tokens = set(re.findall(r'\b[a-z]{3,}\b', query.lower()))
        doc_tokens = set(re.findall(r'\b[a-z]{3,}\b', document.lower()))
        if not q_tokens or not doc_tokens:
            return 0.1
        intersection = q_tokens.intersection(doc_tokens)
        return float(min(1.0, len(intersection) / (len(q_tokens) * 0.75 + 1e-5)))
