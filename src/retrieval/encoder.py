"""Real text encoder for retrieval (S-PubMedBERT primary, MiniLM baseline).

Both models are sentence-transformers checkpoints whose pipeline is
Transformer -> mean pooling (-> L2 normalise for MiniLM). This module runs that
same pipeline directly with Hugging Face ``transformers`` + ``torch`` so it does not
need the ``sentence_transformers`` package (which imports ``datasets`` -> ``pyarrow.dataset``;
that DLL is blocked by Windows Application Control on the development machine).

There is NO fallback of any kind: if the model cannot be loaded, ``EncoderUnavailableError``
is raised. Vectors always come from the model; nothing is random or hash-seeded.
All returned vectors are L2-normalised float32, so inner product == cosine similarity.
"""
import threading
from typing import List, Optional

import numpy as np
import torch
import yaml
from transformers import AutoModel, AutoTokenizer


class EncoderUnavailableError(RuntimeError):
    """Raised when the real embedding model cannot be loaded or produces invalid output."""


_ENCODERS = {}
_LOCK = threading.Lock()


def get_encoder(model_key: str = "primary", config_path: str = "configs/config.yaml") -> "TextEncoder":
    """Process-wide cached encoder (model weights are loaded once)."""
    cache_key = (model_key, config_path)
    with _LOCK:
        if cache_key not in _ENCODERS:
            _ENCODERS[cache_key] = TextEncoder(model_key, config_path)
        return _ENCODERS[cache_key]


class TextEncoder:
    def __init__(self, model_key: str = "primary", config_path: str = "configs/config.yaml", device: Optional[str] = None):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        info = config["retrieval"]["models"][model_key]
        self.model_key = model_key
        self.name = info["name"]
        self.hf_id = info["hf_id"]
        self.dim = int(info["dim"])
        self.max_seq_length = int(info["max_seq_length"])
        if info.get("pooling", "mean") != "mean":
            raise EncoderUnavailableError(f"Unsupported pooling '{info.get('pooling')}' for {self.name}.")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.hf_id)
            self.model = AutoModel.from_pretrained(self.hf_id).to(self.device).eval()
        except Exception as e:  # noqa: BLE001 - re-raised with context
            raise EncoderUnavailableError(f"Could not load embedding model '{self.hf_id}': {e}") from e
        hidden = int(self.model.config.hidden_size)
        if hidden != self.dim:
            raise EncoderUnavailableError(
                f"Model '{self.hf_id}' hidden size {hidden} does not match configured dim {self.dim}."
            )

    def count_tokens(self, texts: List[str]) -> List[int]:
        enc = self.tokenizer(list(texts), add_special_tokens=True, truncation=False)
        return [len(ids) for ids in enc["input_ids"]]

    @torch.inference_mode()
    def encode(self, texts: List[str], batch_size: int = 32, progress=None) -> np.ndarray:
        """Encode texts to an (n, dim) float32 array of L2-normalised mean-pooled embeddings."""
        texts = list(texts)
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        if not texts:
            return out
        # Length-sorted batching minimises padding; order is restored afterwards.
        lengths = [len(t) for t in texts]
        order = np.argsort(lengths)
        done = 0
        for start in range(0, len(texts), batch_size):
            idx = order[start:start + batch_size]
            batch = [texts[i] for i in idx]
            enc = self.tokenizer(
                batch, padding=True, truncation=True, max_length=self.max_seq_length, return_tensors="pt"
            ).to(self.device)
            hidden = self.model(**enc).last_hidden_state              # (b, t, d)
            mask = enc["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)   # mean pooling
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            out[idx] = pooled.float().cpu().numpy()
            done += len(idx)
            if progress is not None:
                progress(done, len(texts))
        if not np.isfinite(out).all():
            raise EncoderUnavailableError("Encoder produced non-finite values.")
        return out

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]
