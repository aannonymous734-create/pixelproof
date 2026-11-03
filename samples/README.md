# Sample patches

`authentic/` holds **30 unmodified files from the official EuroSAT RGB release** (Sentinel-2, 64×64, MIT licence; Helber et al.,
*EuroSAT*, IEEE JSTARS, 2019): 3 patches for each of the 10 land-cover classes.

* They come from the **held-out test split** (so none was used to train or tune the detector), and were chosen by a hash of their
  id, not by hand: `python scripts/make_samples.py --data-dir data/eurosat`.
* They exist so that the attack lab, the VM lab, the demo and the tests run **without** the 2 GB dataset.
* They are **demonstration images, not an evaluation set**. The evaluation uses the full official data (`docs/DATASET_CARD.md`).
* The files are copies of the originals and carry no personal metadata.
