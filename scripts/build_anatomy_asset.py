"""Builds the Digital Twin anatomy asset from BodyParts3D (developer tool, not a runtime dependency).

Source data  : BodyParts3D, (c) The Database Center for Life Science, licensed under CC Attribution-Share Alike 2.1 Japan
               (https://creativecommons.org/licenses/by-sa/2.1/jp/deed.en). STL files fetched from the GitHub mirror
               https://github.com/Kevin-Mattheus-Moerman/BodyParts3D (assets/BodyParts3D_data/stl), which redistributes the original data.
Output       : frontend/public/models/anatomy/bodyparts3d_anatomy.glb   (decimated, metres, Y-up, one named node per part)
               frontend/public/models/anatomy/anatomy_manifest.json     (part -> FMA id, name, layer, region, triangles, provenance)
The output is a derivative work and is therefore distributed under the same CC BY-SA 2.1 JP licence (see LICENSE_ANATOMY.md).

Usage: python scripts/build_anatomy_asset.py [--cache data/raw/bodyparts3d] [--skin-faces 60000]
Requires (dev only): trimesh, fast-simplification, numpy.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request

import numpy as np
import trimesh

RAW = "https://raw.githubusercontent.com/Kevin-Mattheus-Moerman/BodyParts3D/main/assets/BodyParts3D_data"
OUT_DIR = "frontend/public/models/anatomy"

# ---- part selection (name rules over parts_list_e.txt) ------------------------------------------------------------------
EXCLUDE = re.compile(r"muscle|tibialis|fibularis|extensor|flexor|retinacul|membrane|ligament|tract|tendon|aponeurosis|\bhead of\b|frontalis|occipitalis|"
                     r"temporoparietalis|subscapularis|infraspinatus|intertransversarius|papillary|disk|nucleus|choroid|commissure|fornix|aqueduct|canal|"
                     r"geniculate|pineal|hippocamp|thymus|sternothyroid|interosseous|tooth", re.I)
BONE = re.compile(r"\b(bone|vertebra|rib|sternum|manubrium|xiphoid|clavicle|scapula|humerus|radius|ulna|femur|patella|tibia|fibula|sacrum|coccyx|mandible|"
                  r"maxilla|phalanx|metacarpal|metatarsal|talus|calcaneus|navicular|cuboid|cuneiform|hamate|capitate|lunate|scaphoid|trapezi|pisiform|"
                  r"triquetr|atlas|axis|costal cartilage|hyoid|concha)\b", re.I)
BRAIN = re.compile(r"gyrus|gyri|lobule|lobe of (?!.*lung)|cerebellum|midbrain|occipital lobe|temporal lobe|frontal lobe|parietal lobe|insula|cuneus|precuneus", re.I)
ORGANS = {  # exact names -> (layer, region)
    "skin": ("skin", "skin"), "eyeball": ("organs", "eyes"), "right optic nerve": ("nervous", "eyes"), "left optic nerve": ("nervous", "eyes"),
    "ear": ("organs", "ears"), "wall of heart": ("organs", "heart"), "ascending aorta": ("organs", "heart"), "arch of aorta": ("organs", "heart"),
    "descending aorta": ("organs", "heart"), "superior vena cava": ("organs", "heart"), "inferior vena cava": ("organs", "heart"),
    "upper lobe of right lung": ("organs", "lungs"), "middle lobe of lung": ("organs", "lungs"), "lower lobe of right lung": ("organs", "lungs"),
    "upper lobe of left lung": ("organs", "lungs"), "lower lobe of left lung": ("organs", "lungs"), "trachea": ("organs", "lungs"),
    "liver": ("organs", "liver"), "gallbladder": ("organs", "liver"), "stomach": ("organs", "abdomen"), "esophagus": ("organs", "abdomen"),
    "duodenum": ("organs", "abdomen"), "jejunum": ("organs", "abdomen"), "ileum": ("organs", "abdomen"), "colon, nsn": ("organs", "abdomen"),
    "spleen": ("organs", "abdomen"), "pancreas, nsn": ("organs", "abdomen"), "right kidney": ("organs", "kidneys"), "left kidney": ("organs", "kidneys"),
    "urinary bladder": ("organs", "kidneys"),
}
SKULL = re.compile(r"frontal bone|occipital bone|parietal bone|temporal bone|sphenoid|ethmoid|zygomatic|maxilla|mandible|nasal|lacrimal|palatine|vomer|concha|hyoid", re.I)
SPINE = re.compile(r"vertebra|sacrum|coccyx|atlas|axis", re.I)
THORAX = re.compile(r"\brib\b|sternum|manubrium|xiphoid|costal", re.I)
UPPER = re.compile(r"clavicle|scapula|humerus|radius|ulna|carp|finger|thumb|hamate|capitate|lunate|scaphoid|trapezi|pisiform|triquetr", re.I)


def classify(name):
    if name in ORGANS:
        return ORGANS[name]
    if EXCLUDE.search(name):
        return None
    if BRAIN.search(name):
        return ("nervous", "brain")
    if BONE.search(name):
        if SKULL.search(name):
            return ("skeleton", "skull")
        if SPINE.search(name):
            return ("skeleton", "spine")
        if THORAX.search(name):
            return ("skeleton", "thorax")
        if UPPER.search(name):
            return ("skeleton", "upper_limbs")
        return ("skeleton", "lower_limbs")
    return None


def target_faces(layer, region, n):
    if layer == "skin":
        return ARGS.skin_faces
    if region == "brain":
        return min(n, 2500)
    if layer == "skeleton":
        return min(n, 900)
    return min(n, 4000)


def fetch(fid, cache):
    path = os.path.join(cache, fid + ".stl")
    if not os.path.exists(path):
        urllib.request.urlretrieve(f"{RAW}/stl/{fid}.stl", path)
    return path


def main():
    os.makedirs(ARGS.cache, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    plist = os.path.join(ARGS.cache, "parts_list_e.txt")
    if not os.path.exists(plist):
        urllib.request.urlretrieve(f"{RAW}/parts_list_e.txt", plist)
    tree = json.load(urllib.request.urlopen("https://api.github.com/repos/Kevin-Mattheus-Moerman/BodyParts3D/git/trees/main?recursive=1"))
    available = {x["path"].split("/")[-1][:-4] for x in tree["tree"] if x["path"].endswith(".stl")}
    names = {}
    for line in open(plist, encoding="utf-8", errors="ignore").read().splitlines()[1:]:
        p = line.split("\t")
        if len(p) >= 2:
            names[p[0]] = p[1]
    chosen = []
    for fid in sorted(available):
        if fid not in names:
            continue
        c = classify(names[fid])
        if c:
            chosen.append((fid, names[fid], c[0], c[1]))
    print(f"{len(chosen)} parts selected")
    scene = trimesh.Scene()
    # BodyParts3D: millimetres, Z up. Convert to metres, Y up, feet near y=0, body centred on x/z.
    R = trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])
    meshes, manifest = [], []
    for fid, name, layer, region in chosen:
        m = trimesh.load(fetch(fid, ARGS.cache), force="mesh")
        n0 = len(m.faces)
        tf = target_faces(layer, region, n0)
        if tf < n0:
            m = m.simplify_quadric_decimation(face_count=tf)
        m.apply_scale(0.001)
        m.apply_transform(R)
        meshes.append((fid, name, layer, region, m, n0))
    lo = np.min([m.bounds[0] for *_, m, _ in meshes], axis=0)
    hi = np.max([m.bounds[1] for *_, m, _ in meshes], axis=0)
    shift = np.array([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
    for fid, name, layer, region, m, n0 in meshes:
        m.apply_translation(shift)
        node = f"{layer}__{region}__{fid}"
        scene.add_geometry(m, node_name=node, geom_name=node)
        manifest.append({"node": node, "fma_id": fid, "name": name, "layer": layer, "region": region,
                         "faces_source": int(n0), "faces_asset": int(len(m.faces)),
                         "center": [round(float(v), 4) for v in m.bounds.mean(axis=0)],
                         "bounds": [[round(float(v), 4) for v in m.bounds[0]], [round(float(v), 4) for v in m.bounds[1]]]})
    out = os.path.join(OUT_DIR, "bodyparts3d_anatomy.glb")
    data = scene.export(file_type="glb")
    open(out, "wb").write(data)
    sha = hashlib.sha256(data).hexdigest()
    height = float(hi[1] - lo[1])
    json.dump({"asset": "bodyparts3d_anatomy.glb", "bytes": len(data), "sha256": sha, "units": "metres", "up": "+Y", "body_height_m": round(height, 3),
               "source": "BodyParts3D (Database Center for Life Science, Japan), via github.com/Kevin-Mattheus-Moerman/BodyParts3D",
               "licence": "CC BY-SA 2.1 JP - https://creativecommons.org/licenses/by-sa/2.1/jp/deed.en",
               "credit": "BodyParts3D, (c) The Database Center for Life Science licensed under CC Attribution-Share Alike 2.1 Japan",
               "modifications": "selected parts only; quadric decimation (fast-simplification); scaled mm->m; rotated Z-up->Y-up; recentred",
               "build_script": "scripts/build_anatomy_asset.py", "parts": manifest}, open(os.path.join(OUT_DIR, "anatomy_manifest.json"), "w"), indent=1)
    by = {}
    for p in manifest:
        by[p["layer"]] = by.get(p["layer"], 0) + 1
    print(json.dumps({"bytes": len(data), "parts": len(manifest), "by_layer": by, "height_m": round(height, 3)}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="data/raw/bodyparts3d")
    ap.add_argument("--skin-faces", type=int, default=60000)
    ARGS = ap.parse_args()
    sys.exit(main())
