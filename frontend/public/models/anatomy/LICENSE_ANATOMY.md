# Anatomy asset — provenance and licence

`bodyparts3d_anatomy.glb` (and `anatomy_manifest.json`) are derived from **BodyParts3D**.

- Credit: **BodyParts3D, © The Database Center for Life Science licensed under CC Attribution-Share Alike 2.1 Japan**
- Licence: Creative Commons Attribution-ShareAlike 2.1 Japan — https://creativecommons.org/licenses/by-sa/2.1/jp/deed.en
- Original source: https://lifesciencedb.jp/bp3d/ (DBCLS). STL files were obtained from the mirror
  https://github.com/Kevin-Mattheus-Moerman/BodyParts3D (repository code MIT; the anatomy data keeps the CC BY-SA licence above).
- Modifications (this is an adapted work): selection of 277 parts (skin, skeleton, brain, eyes, ear, heart and great vessels, lungs,
  trachea, digestive organs, kidneys, bladder); quadric mesh decimation; scaling from millimetres to metres; rotation to +Y up;
  recentring with the feet at y = 0; packing into one binary glTF with one node per part named `layer__region__FMAid`.
- Build: `python scripts/build_anatomy_asset.py` (reproducible; downloads the source STLs into the git-ignored `data/raw/bodyparts3d/`).
  Size and SHA-256 of the built file are recorded in `anatomy_manifest.json`.

**Share-alike:** this derived asset is distributed under the same CC BY-SA 2.1 JP licence. It is a reference adult anatomy model; it is
not a model of any patient. Phenotype markers drawn on it are placed by the deterministic HPO → region table in `src/twin/anatomy.py`.
