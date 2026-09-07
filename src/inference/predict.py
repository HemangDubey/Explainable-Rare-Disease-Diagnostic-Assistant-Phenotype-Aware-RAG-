import argparse
import json
import yaml
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForTokenClassification

def predict_phenotypes(model_path, text, config_path="configs/config.yaml"):
    model_dir = Path(model_path)
    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    # Load label mapping
    meta_path = model_dir / "metadata.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        id2label = {int(k): v for k, v in meta["id2label"].items()}
    else:
        id2label = {0: "O", 1: "B-PHENOTYPE", 2: "I-PHENOTYPE"}

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForTokenClassification.from_pretrained(str(model_dir))
    model.eval()

    inputs = tokenizer(
        text,
        return_offsets_mapping=True,
        return_tensors="pt",
        truncation=True,
        max_length=512
    )

    offset_mapping = inputs["offset_mapping"][0].tolist()
    input_ids = inputs["input_ids"][0].tolist()
    attention_mask = inputs["attention_mask"]

    with torch.no_grad():
        outputs = model(input_ids=inputs["input_ids"], attention_mask=attention_mask)
        preds = torch.argmax(outputs.logits, dim=2)[0].tolist()

    # Extract phenotype mentions and spans
    extracted_phenotypes = []
    current_entity_tokens = []
    current_entity_spans = []
    current_bio_labels = []

    for idx, (tok_id, (start, end), pred_id) in enumerate(zip(input_ids, offset_mapping, preds)):
        if start == end: # Special token
            continue
        
        label = id2label.get(pred_id, "O")
        tok_str = text[start:end]

        if label == "B-PHENOTYPE":
            if current_entity_tokens:
                full_span_text = text[current_entity_spans[0][0]:current_entity_spans[-1][1]]
                extracted_phenotypes.append({
                    "phenotype": full_span_text,
                    "span": f"{current_entity_spans[0][0]}-{current_entity_spans[-1][1]}",
                    "bio": " / ".join(current_bio_labels)
                })
                current_entity_tokens = []
                current_entity_spans = []
                current_bio_labels = []
            
            current_entity_tokens.append(tok_str)
            current_entity_spans.append((start, end))
            current_bio_labels.append("B-PHENOTYPE")

        elif label == "I-PHENOTYPE":
            if current_entity_tokens:
                current_entity_tokens.append(tok_str)
                current_entity_spans.append((start, end))
                current_bio_labels.append("I-PHENOTYPE")
            else: # Fallback if I starts without B
                current_entity_tokens.append(tok_str)
                current_entity_spans.append((start, end))
                current_bio_labels.append("B-PHENOTYPE")
        else: # O
            if current_entity_tokens:
                full_span_text = text[current_entity_spans[0][0]:current_entity_spans[-1][1]]
                extracted_phenotypes.append({
                    "phenotype": full_span_text,
                    "span": f"{current_entity_spans[0][0]}-{current_entity_spans[-1][1]}",
                    "bio": " / ".join(current_bio_labels)
                })
                current_entity_tokens = []
                current_entity_spans = []
                current_bio_labels = []

    if current_entity_tokens:
        full_span_text = text[current_entity_spans[0][0]:current_entity_spans[-1][1]]
        extracted_phenotypes.append({
            "phenotype": full_span_text,
            "span": f"{current_entity_spans[0][0]}-{current_entity_spans[-1][1]}",
            "bio": " / ".join(current_bio_labels)
        })

    return extracted_phenotypes

def main():
    parser = argparse.ArgumentParser(description="Phenotype Extraction Inference")
    parser.add_argument("--model", type=str, required=True, help="Path to saved transformer model directory")
    parser.add_argument("--text", type=str, required=True, help="Clinical observation text")
    args = parser.parse_args()

    print(f"\n--- Input Text ---")
    print(args.text)
    print(f"\n--- Extracted Phenotypes ---")

    results = predict_phenotypes(args.model, args.text)

    if not results:
        print("No phenotype mentions detected.")
    else:
        for item in results:
            print(f"Phenotype: {item['phenotype']}")
            print(f"Span: {item['span']}")
            print(f"BIO: {item['bio']}\n")

if __name__ == "__main__":
    main()
