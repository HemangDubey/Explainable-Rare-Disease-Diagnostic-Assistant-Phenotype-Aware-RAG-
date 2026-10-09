"""Deterministic, explainable phenotype -> anatomical-region mapping for the Clinical Digital Twin.

Provenance: the HPO ontology itself (data/processed/hpo/hpo_terms.json, is_a hierarchy). A finding is mapped to a region only if one of
the organ-system terms below is an ancestor of (or equal to) its HPO term. When several entries match, an entry is dropped if a MORE
SPECIFIC matching entry descends from it (e.g. "Abnormality of the liver" suppresses "Abnormality of the digestive system").
No match -> the finding is "unassigned" (never guessed). The table is explicit and versioned here; it is not learned.
"""
from typing import Dict, List

# (HPO organ-system term, region key). Order is irrelevant: specificity is decided by the ontology.
ORGAN_SYSTEM_TABLE = [
    ("HP:0001392", "liver"),        # Abnormality of the liver
    ("HP:0000077", "kidneys"),      # Abnormality of the kidney
    ("HP:0000079", "kidneys"),      # Abnormality of the urinary system
    ("HP:0000929", "skull"),        # Abnormal skull morphology
    ("HP:0000925", "spine"),        # Abnormality of the vertebral column
    ("HP:0040064", "limbs"),        # Abnormality of limbs
    ("HP:0000707", "brain"),        # Abnormality of the nervous system (incl. neurodevelopmental, seizures)
    ("HP:0000478", "eyes"),         # Abnormality of the eye
    ("HP:0000598", "ears"),         # Abnormality of the ear
    ("HP:0001626", "heart"),        # Abnormality of the cardiovascular system
    ("HP:0002086", "lungs"),        # Abnormality of the respiratory system
    ("HP:0025031", "abdomen"),      # Abnormality of the digestive system
    ("HP:0000924", "skeleton"),     # Abnormality of the skeletal system
    ("HP:0003011", "musculature"),  # Abnormality of the musculature
    ("HP:0001574", "skin"),         # Abnormality of the integument
    ("HP:0000152", "head"),         # Abnormality of head or neck
    ("HP:0001507", "systemic"),     # Growth abnormality (e.g. short stature): not localisable
    ("HP:0001939", "systemic"),     # Abnormality of metabolism/homeostasis
    ("HP:0001871", "systemic"),     # Abnormality of blood and blood-forming tissues
    ("HP:0002715", "systemic"),     # Abnormality of the immune system
]

# Region -> which asset meshes represent it ("mesh_regions" are the region tags written into the anatomy asset manifest).
REGIONS: Dict[str, Dict] = {
    "brain": {"label": "Brain / nervous system", "mesh_regions": ["brain"], "system": "nervous"},
    "eyes": {"label": "Eyes", "mesh_regions": ["eyes"], "system": "sensory"},
    "ears": {"label": "Ears", "mesh_regions": ["ears"], "system": "sensory"},
    "heart": {"label": "Heart / cardiovascular", "mesh_regions": ["heart"], "system": "cardiovascular"},
    "lungs": {"label": "Lungs / respiratory", "mesh_regions": ["lungs"], "system": "respiratory"},
    "liver": {"label": "Liver", "mesh_regions": ["liver"], "system": "digestive"},
    "abdomen": {"label": "Digestive system", "mesh_regions": ["abdomen", "liver"], "system": "digestive"},
    "kidneys": {"label": "Kidneys / urinary", "mesh_regions": ["kidneys"], "system": "urinary"},
    "skull": {"label": "Skull", "mesh_regions": ["skull"], "system": "skeletal"},
    "head": {"label": "Head and neck", "mesh_regions": ["skull", "eyes", "ears"], "system": "skeletal"},
    "spine": {"label": "Vertebral column", "mesh_regions": ["spine"], "system": "skeletal"},
    "limbs": {"label": "Limbs", "mesh_regions": ["upper_limbs", "lower_limbs"], "system": "skeletal"},
    "skeleton": {"label": "Skeletal system", "mesh_regions": ["skull", "spine", "thorax", "upper_limbs", "lower_limbs"], "system": "skeletal"},
    "musculature": {"label": "Musculature", "mesh_regions": [], "system": "muscular",
                    "note": "The anatomy asset contains no muscle meshes; shown as a marker on the limbs."},
    "skin": {"label": "Skin / integument", "mesh_regions": ["skin"], "system": "integumentary"},
    "systemic": {"label": "Systemic (not localisable)", "mesh_regions": [], "system": "systemic",
                 "note": "Findings such as growth or metabolic abnormalities have no single anatomical site; shown as a whole-body state."},
}


class AnatomyMapper:
    def __init__(self, hpo_terms: Dict[str, Dict]):
        self.terms = hpo_terms
        self._anc: Dict[str, frozenset] = {}
        self.table = [(h, r) for h, r in ORGAN_SYSTEM_TABLE if h in hpo_terms]       # silently drops ids absent from this HPO release
        self.dropped = [h for h, _ in ORGAN_SYSTEM_TABLE if h not in hpo_terms]

    def ancestors(self, hid: str) -> frozenset:
        """Ancestor-or-self set over is_a."""
        if hid not in self._anc:
            seen, stack = {hid}, [hid]
            while stack:
                for p in self.terms.get(stack.pop(), {}).get("is_a", []):
                    if p not in seen:
                        seen.add(p)
                        stack.append(p)
            self._anc[hid] = frozenset(seen)
        return self._anc[hid]

    def regions_for(self, hpo_id: str) -> List[Dict]:
        if not hpo_id or hpo_id not in self.terms:
            return []
        anc = self.ancestors(hpo_id)
        hits = [(h, r) for h, r in self.table if h in anc]
        keep = [(h, r) for h, r in hits if not any(h2 != h and h in self.ancestors(h2) for h2, _ in hits)]
        out, seen = [], set()
        for h, r in keep:
            if r in seen:
                continue
            seen.add(r)
            out.append({"region": r, "label": REGIONS[r]["label"], "system": REGIONS[r]["system"], "via_hpo_id": h,
                        "via_hpo_name": self.terms[h]["name"], "rule": "HPO is_a ancestor in ORGAN_SYSTEM_TABLE (most specific kept)"})
        return out
