"""BiomedBERT phenotype NER inference (the single source of phenotype mentions).

`PhenotypeNER` loads the fine-tuned checkpoint once and returns structured mentions:
    {"mention", "start", "end", "label": "PHENOTYPE", "confidence", ...legacy keys}
`predict_phenotypes(model_path, text)` is kept as a thin wrapper for existing callers.
Long notes are processed in sentence-aligned chunks so nothing beyond 512 tokens is silently dropped.
"""
import argparse
import json
import re
import threading
from pathlib import Path

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

_INSTANCES = {}
_LOCK = threading.Lock()
_CHUNK_CHARS = 1200


def get_ner(model_path):
    key = str(Path(model_path).resolve())
    with _LOCK:
        if key not in _INSTANCES:
            _INSTANCES[key] = PhenotypeNER(model_path)
        return _INSTANCES[key]


def _chunks(text):
    """Yield (offset, chunk_text) pieces of <= ~_CHUNK_CHARS, split on sentence boundaries."""
    if len(text) <= _CHUNK_CHARS:
        yield 0, text
        return
    pieces = [(m.start(), m.end()) for m in re.finditer(r"[^.!?\n]+[.!?\n]*", text)]
    cur_start, cur_end = None, None
    for s, e in pieces:
        if cur_start is None:
            cur_start, cur_end = s, e
        elif e - cur_start <= _CHUNK_CHARS:
            cur_end = e
        else:
            yield cur_start, text[cur_start:cur_end]
            cur_start, cur_end = s, e
    if cur_start is not None:
        yield cur_start, text[cur_start:cur_end]


class PhenotypeNER:
    def __init__(self, model_path):
        model_dir = Path(model_path)
        if not model_dir.exists():
            raise FileNotFoundError(f"NER model directory not found: {model_dir}")
        meta_path = model_dir / "metadata.json"
        if meta_path.exists():
            meta = json.load(open(meta_path, encoding="utf-8"))
            self.id2label = {int(k): v for k, v in meta["id2label"].items()}
        else:
            self.id2label = {0: "O", 1: "B-PHENOTYPE", 2: "I-PHENOTYPE"}
        self.model_dir = str(model_dir)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
        self.model = AutoModelForTokenClassification.from_pretrained(self.model_dir).eval()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)

    @torch.inference_mode()
    def _extract_chunk(self, text, offset):
        inputs = self.tokenizer(text, return_offsets_mapping=True, return_tensors="pt", truncation=True, max_length=512)
        offsets = inputs.pop("offset_mapping")[0].tolist()
        logits = self.model(**{k: v.to(self.device) for k, v in inputs.items()}).logits[0]
        probs = torch.softmax(logits, dim=-1).cpu()
        preds = probs.argmax(-1).tolist()

        mentions, cur = [], None

        def flush():
            nonlocal cur
            if cur:
                s, e = cur["spans"][0][0], cur["spans"][-1][1]
                mentions.append({
                    "mention": text[s:e], "start": offset + s, "end": offset + e, "label": "PHENOTYPE",
                    "confidence": round(sum(cur["conf"]) / len(cur["conf"]), 4),
                    "bio": " / ".join(cur["bio"]),
                })
                cur = None

        for idx, ((s, e), pred) in enumerate(zip(offsets, preds)):
            if s == e:           # special tokens
                continue
            label = self.id2label.get(pred, "O")
            conf = float(probs[idx][pred])
            if label == "B-PHENOTYPE":
                flush()
                cur = {"spans": [(s, e)], "conf": [conf], "bio": ["B-PHENOTYPE"]}
            elif label == "I-PHENOTYPE":
                if cur is None:
                    cur = {"spans": [(s, e)], "conf": [conf], "bio": ["B-PHENOTYPE"]}
                else:
                    cur["spans"].append((s, e)); cur["conf"].append(conf); cur["bio"].append("I-PHENOTYPE")
            else:
                flush()
        flush()
        return mentions

    def extract(self, text):
        out = []
        for offset, chunk in _chunks(text):
            if chunk.strip():
                out.extend(self._extract_chunk(chunk, offset))
        for m in out:   # legacy keys used by existing callers
            m["phenotype"] = m["mention"]
            m["span"] = f"{m['start']}-{m['end']}"
        return out


def predict_phenotypes(model_path, text, config_path="configs/config.yaml"):
    return get_ner(model_path).extract(text)


def main():
    parser = argparse.ArgumentParser(description="Phenotype Extraction Inference")
    parser.add_argument("--model", type=str, required=True, help="Path to saved transformer model directory")
    parser.add_argument("--text", type=str, required=True, help="Clinical observation text")
    args = parser.parse_args()
    for item in predict_phenotypes(args.model, args.text):
        print(f"{item['mention']!r} [{item['start']}-{item['end']}] conf={item['confidence']}")


if __name__ == "__main__":
    main()
