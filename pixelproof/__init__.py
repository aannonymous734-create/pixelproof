"""PixelProof: provenance binding and manipulation detection for EuroSAT (Sentinel-2) patches.

Two separate answers are produced for every patch (TSYP14 Track 3, "Trust the Pixel"):

* integrity  - were these exact pixels and claims produced by a trusted source?  (cryptography)
* content    - does the patch carry traces of resampling/splicing, copy-move or
               generation/inpainting?                                            (forensics + ML)
"""

__version__ = "1.0.0"

LABELS = ["authentic", "resampled_spliced", "copy_move", "generated_inpainted"]
