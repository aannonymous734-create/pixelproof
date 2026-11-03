"""Attack lab for the trust layer (Deliverable 5: adversarial validation).

Each attack takes a genuine (image, manifest) pair as it travels from the source to the ground
station and returns what the attacker delivers. They are the attacks named at the info session
(integrity, algorithm substitution, inpainting/embedding, date replacement, cryptographic
signature) plus replay, manifest swap and a forged processing step.

`expected` is the integrity status a correct verifier must return.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta

import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import manipulations as M
from .provenance import CLAIM_FIELDS, b64e, canonical, pixel_digest, sha256_hex

_ATTACKER_KEY = Ed25519PrivateKey.generate()  # the attacker's own key (not trusted)


def _shift_date(m, days):
    t = datetime.fromisoformat(m["capture_time"].replace("Z", "+00:00")) + timedelta(days=days)
    return t.isoformat(timespec="seconds")


def pixel_inpaint(img, m, rng, **_):
    return M.inpaint(img, rng, "heldout")[0], copy.deepcopy(m)


def pixel_copy_move(img, m, rng, **_):
    return M.copy_move(img, rng, "dev")[0], copy.deepcopy(m)


def pixel_resample(img, m, rng, **_):
    return M.resample(img, rng, "dev")[0], copy.deepcopy(m)


def lsb_embed(img, m, rng, **_):
    """Hide 512 bits in least-significant bits: invisible, content detectors cannot see it."""
    out = img.copy().reshape(-1)
    idx = rng.choice(out.size, 512, replace=False)
    out[idx] = (out[idx] & 0xFE) | rng.integers(0, 2, 512).astype(np.uint8)
    return out.reshape(img.shape), copy.deepcopy(m)


def date_replace(img, m, rng, **_):
    m2 = copy.deepcopy(m)
    m2["capture_time"] = _shift_date(m, -365)
    return img, m2


def date_replace_resign(img, m, rng, **_):
    """Re-date AND re-sign with the attacker's own key (pretending to be the source)."""
    m2 = copy.deepcopy(m)
    m2["capture_time"] = _shift_date(m, 30)
    m2["key_id"] = "sat-99"  # claims the same source name, but signs with an untrusted key
    claim = {k: m2[k] for k in CLAIM_FIELDS}
    m2["signature"] = b64e(_ATTACKER_KEY.sign(canonical(claim)))
    return img, m2


def algorithm_downgrade(img, m, rng, **_):
    """Edit pixels, then claim a weak hash and recompute it (algorithm substitution)."""
    out = M.inpaint(img, rng, "dev")[0]
    m2 = copy.deepcopy(m)
    m2["hash_alg"] = "md5"
    import hashlib
    m2["pixel_digest"] = hashlib.md5(out.tobytes()).hexdigest()
    return out, m2


def strip_manifest(img, m, rng, **_):
    """Edit pixels and drop the provenance record entirely."""
    return M.inpaint(img, rng, "heldout")[0], None


def manifest_swap(img, m, rng, other=None, **_):
    """Deliver a different genuine image under this valid manifest."""
    return other, copy.deepcopy(m)


def forged_processing(img, m, rng, **_):
    """Cover a pixel edit with a fake 'crop' step signed by the attacker."""
    out = M.copy_move(img, rng, "dev")[0]
    m2 = copy.deepcopy(m)
    body = {"op": "radiometric_correction", "params": {}, "input_digest": m["pixel_digest"],
            "output_digest": pixel_digest(out), "key_id": "proc-01", "hash_alg": "sha256", "sig_alg": "ed25519",
            "time": m["capture_time"], "prev_record": sha256_hex(canonical({k: m[k] for k in (*CLAIM_FIELDS,
                                                                                               "signature")}))}
    m2["processing"] = [{**body, "signature": b64e(_ATTACKER_KEY.sign(canonical(body)))}]
    return out, m2


def replay(img, m, rng, **_):
    """Re-send a genuine product that was already delivered."""
    return img, copy.deepcopy(m)


ATTACKS = {
    # name: (function, expected integrity status, what it demonstrates)
    "pixel_inpaint": (pixel_inpaint, "PIXELS_ALTERED", "region erased and filled after capture"),
    "pixel_copy_move": (pixel_copy_move, "PIXELS_ALTERED", "region duplicated after capture"),
    "pixel_resample": (pixel_resample, "PIXELS_ALTERED", "patch rescaled/rotated after capture"),
    "lsb_embed": (lsb_embed, "PIXELS_ALTERED", "invisible bit-level embedding (no visual trace)"),
    "date_replace": (date_replace, "BAD_SIGNATURE", "capture date changed, signature kept"),
    "date_replace_resign": (date_replace_resign, "UNKNOWN_KEY", "date changed and re-signed with attacker key"),
    "algorithm_downgrade": (algorithm_downgrade, "WEAK_ALGORITHM", "claims md5 to forge a matching digest"),
    "forged_processing": (forged_processing, "CHAIN_BROKEN", "fake processing step hides an edit"),
    "manifest_swap": (manifest_swap, "PIXELS_ALTERED", "valid manifest attached to another image"),
    "replay": (replay, "REPLAY", "already-delivered product sent again"),
    "strip_manifest": (strip_manifest, "NO_PROVENANCE", "edit + provenance removed: content analysis must decide"),
}
