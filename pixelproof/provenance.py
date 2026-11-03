"""Trust layer (Deliverable 2): digest, time/source claim, verification chain.

1. DIGEST     SHA-256 over a canonical encoding of the decoded pixel array
              (b"PXP1" | dtype | shape | raw bytes). Re-encoding the file without changing a
              pixel keeps the digest; changing one bit of one pixel changes it.
2. CLAIM      a manifest {product_id, source, sensor, capture_time, bands, shape, digest, ...}
              signed with Ed25519 by the source key (software trust anchor, allowed by the rules).
3. CHAIN      every processing step after capture (crop, band selection, format conversion)
              appends a record {op, params, input_digest, output_digest} signed by the processor
              key and linked to the previous record's hash. Captures from one source are also
              linked: seq (monotonic) + prev_hash (hash of the previous manifest).

The verifier trusts only a registry of PUBLIC keys and PINS the algorithms (sha256 + ed25519):
a manifest that claims another algorithm (e.g. "md5" or "none") is rejected outright.

Integrity statuses (first failing check wins):
  NO_PROVENANCE      no manifest supplied              -> content analysis decides
  MALFORMED          missing/invalid fields
  WEAK_ALGORITHM     algorithm not in the pinned set (algorithm-substitution attack)
  UNKNOWN_KEY        signer not in the trusted registry (attacker re-signed with own key)
  REVOKED_KEY        signer key revoked
  BAD_SIGNATURE      manifest content changed after signing (e.g. capture date replaced)
  CHAIN_BROKEN       a processing record is unsigned, unlinked or inconsistent
  PIXELS_ALTERED     pixel digest differs from the last signed digest (post-capture edit)
  REPLAY             product already seen with other content/date, or seq not increasing
  TIME_IMPLAUSIBLE   capture time in the future or before the sensor existed
  VERIFIED           all checks passed
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

HASH_ALG, SIG_ALG, FORMAT = "sha256", "ed25519", "pixelproof-manifest/1"
GENESIS = "0" * 64
SENSOR_EPOCH = {"Sentinel-2": datetime(2015, 6, 23, tzinfo=timezone.utc)}  # Sentinel-2A launch
CLAIM_FIELDS = ("format", "product_id", "source", "sensor", "capture_time", "bands", "shape", "dtype",
                "pixel_digest", "hash_alg", "sig_alg", "key_id", "seq", "prev_hash")


# ------------------------------------------------------------------------ helpers
def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode()


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode(), validate=True)


def pixel_digest(img: np.ndarray) -> str:
    a = np.ascontiguousarray(img)
    head = f"PXP1|{a.dtype.str}|{'x'.join(map(str, a.shape))}|".encode()
    return sha256_hex(head + a.tobytes())


def manifest_hash(m: dict) -> str:
    return sha256_hex(canonical({k: m[k] for k in (*CLAIM_FIELDS, "signature", "processing") if k in m}))


def _parse_time(s: str) -> datetime:
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------------- keys
class Keystore:
    """File-backed private keys, kept OUTSIDE the repository (default ~/.pixelproof/keys).
    Upgrade path: the same Signer interface backed by SoftHSM2 / a TPM via PKCS#11."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.environ.get("PIXELPROOF_KEYS", Path.home() / ".pixelproof" / "keys"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key_id: str) -> Path:
        if not key_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"invalid key id {key_id!r}")
        return self.root / f"{key_id}.pem"

    def create(self, key_id: str) -> Ed25519PublicKey:
        p = self._path(key_id)
        if p.exists():
            return self.load(key_id).public_key()
        sk = Ed25519PrivateKey.generate()
        p.write_bytes(sk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        return sk.public_key()

    def load(self, key_id: str) -> Ed25519PrivateKey:
        return serialization.load_pem_private_key(self._path(key_id).read_bytes(), password=None)


def pub_b64(pk: Ed25519PublicKey) -> str:
    return b64e(pk.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


@dataclass
class Registry:
    """What the ground station trusts: key_id -> {role, owner, public_key, revoked}."""

    keys: dict = field(default_factory=dict)

    def add(self, key_id: str, pk: Ed25519PublicKey, role: str, owner: str):
        self.keys[key_id] = {"role": role, "owner": owner, "public_key": pub_b64(pk), "revoked": False}

    def revoke(self, key_id: str):
        self.keys[key_id]["revoked"] = True

    def public(self, key_id: str) -> Ed25519PublicKey:
        return Ed25519PublicKey.from_public_bytes(b64d(self.keys[key_id]["public_key"]))

    def save(self, path):
        Path(path).write_text(json.dumps(self.keys, indent=2))

    @classmethod
    def load(cls, path):
        # read bytes: json.loads(bytes) accepts a UTF-8 BOM, which Windows editors and PowerShell add when saving
        return cls(json.loads(Path(path).read_bytes()))


# ---------------------------------------------------------------------- signing
class SourceSigner:
    """Runs at the capture source (satellite / payload emulator)."""

    def __init__(self, key_id: str, sk: Ed25519PrivateKey, source: str, sensor: str = "Sentinel-2"):
        self.key_id, self._sk, self.source, self.sensor = key_id, sk, source, sensor
        self.seq, self.head = 0, GENESIS

    def capture(self, img: np.ndarray, product_id: str, capture_time: str, bands=("B4", "B3", "B2")) -> dict:
        self.seq += 1
        claim = {"format": FORMAT, "product_id": product_id, "source": self.source, "sensor": self.sensor,
                 "capture_time": capture_time, "bands": list(bands), "shape": list(img.shape),
                 "dtype": str(img.dtype), "pixel_digest": pixel_digest(img), "hash_alg": HASH_ALG,
                 "sig_alg": SIG_ALG, "key_id": self.key_id, "seq": self.seq, "prev_hash": self.head}
        m = {**claim, "signature": b64e(self._sk.sign(canonical(claim))), "processing": []}
        self.head = sha256_hex(canonical({**claim, "signature": m["signature"]}))
        return m


class ProcessorSigner:
    """Runs at a ground processing step; appends one signed, linked record per operation."""

    def __init__(self, key_id: str, sk: Ed25519PrivateKey):
        self.key_id, self._sk = key_id, sk

    def record(self, manifest: dict, op: str, params: dict, output: np.ndarray) -> dict:
        steps = manifest.get("processing", [])
        prev = steps[-1] if steps else None
        body = {"op": op, "params": params,
                "input_digest": prev["output_digest"] if prev else manifest["pixel_digest"],
                "output_digest": pixel_digest(output), "key_id": self.key_id, "hash_alg": HASH_ALG,
                "sig_alg": SIG_ALG, "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "prev_record": sha256_hex(canonical(prev)) if prev else sha256_hex(canonical(
                    {k: manifest[k] for k in (*CLAIM_FIELDS, "signature")}))}
        rec = {**body, "signature": b64e(self._sk.sign(canonical(body)))}
        return {**manifest, "processing": [*steps, rec]}


# --------------------------------------------------------------------- verifying
@dataclass
class IntegrityResult:
    status: str
    ok: bool
    reasons: list[str]
    claim: dict | None = None


@dataclass
class Verifier:
    registry: Registry
    now: callable = lambda: datetime.now(timezone.utc)
    max_future: timedelta = timedelta(minutes=10)
    seen: dict = field(default_factory=dict)      # product_id -> (capture_time, pixel_digest)
    last_seq: dict = field(default_factory=dict)  # source key -> last seq

    def _sig_ok(self, key_id, body, sig) -> tuple[bool, str | None]:
        k = self.registry.keys.get(key_id)
        if k is None:
            return False, "UNKNOWN_KEY"
        if k["revoked"]:
            return False, "REVOKED_KEY"
        try:
            self.registry.public(key_id).verify(b64d(sig), canonical(body))
            return True, None
        except (InvalidSignature, ValueError, TypeError):
            return False, "BAD_SIGNATURE"

    def verify(self, img: np.ndarray, manifest: dict | None, record: bool = True) -> IntegrityResult:
        """record=True: live downlink (registers the product; duplicates are replays).
        record=False: analyst look-up of an archived product (no state change)."""
        if not manifest:
            return IntegrityResult("NO_PROVENANCE", False, ["no provenance record supplied"])
        try:
            claim = {k: manifest[k] for k in CLAIM_FIELDS}
            sig, steps = manifest["signature"], manifest.get("processing", [])
        except (KeyError, TypeError):
            return IntegrityResult("MALFORMED", False, ["manifest is missing required fields"])
        if claim["format"] != FORMAT:
            return IntegrityResult("MALFORMED", False, [f"unknown manifest format {claim['format']!r}"])
        algs = [(claim["hash_alg"], claim["sig_alg"])] + [(s.get("hash_alg"), s.get("sig_alg")) for s in steps]
        if any(a != (HASH_ALG, SIG_ALG) for a in algs):
            return IntegrityResult("WEAK_ALGORITHM", False,
                                   [f"only {HASH_ALG}+{SIG_ALG} are accepted, got {sorted(set(map(str, algs)))}"], claim)
        ok, err = self._sig_ok(claim["key_id"], claim, sig)
        if not ok:
            why = {"UNKNOWN_KEY": f"signer {claim['key_id']!r} is not a trusted source",
                   "REVOKED_KEY": f"signer {claim['key_id']!r} was revoked",
                   "BAD_SIGNATURE": "claim (date, source, digest...) was modified after signing"}[err]
            return IntegrityResult(err, False, [why], claim)
        if self.registry.keys[claim["key_id"]]["role"] != "source":
            return IntegrityResult("UNKNOWN_KEY", False, ["capture claim not signed by a source key"], claim)
        # processing chain
        expected_in = claim["pixel_digest"]
        prev_link = sha256_hex(canonical({**claim, "signature": sig}))
        for i, s in enumerate(steps):
            body = {k: v for k, v in s.items() if k != "signature"}
            ok, err = self._sig_ok(s.get("key_id"), body, s.get("signature", ""))
            if not ok or s.get("input_digest") != expected_in or s.get("prev_record") != prev_link:
                return IntegrityResult("CHAIN_BROKEN", False, [f"processing step {i + 1} ({s.get('op')}) is "
                                       f"{'not validly signed' if not ok else 'not linked to the previous step'}"], claim)
            expected_in, prev_link = s["output_digest"], sha256_hex(canonical(s))
        if pixel_digest(img) != expected_in:
            return IntegrityResult("PIXELS_ALTERED", False,
                                   ["pixels differ from the last signed digest: modified after capture/processing"],
                                   claim)
        t = _parse_time(claim["capture_time"])
        epoch = SENSOR_EPOCH.get(claim["sensor"].split()[0], None)
        if t > self.now() + self.max_future or (epoch and t < epoch):
            return IntegrityResult("TIME_IMPLAUSIBLE", False, [f"capture time {claim['capture_time']} is impossible "
                                                               f"for {claim['sensor']}"], claim)
        prior = self.seen.get(claim["product_id"])
        if prior and prior != (claim["capture_time"], claim["pixel_digest"]):
            return IntegrityResult("REPLAY", False, ["product already registered with a different date or content "
                                                     "(re-dated or substituted image)"], claim)
        if record and prior is not None:  # live downlink: the same product must not arrive twice
            return IntegrityResult("REPLAY", False, ["this signed product was already received (replayed message)"],
                                   claim)
        if record and claim["seq"] <= self.last_seq.get(claim["key_id"], 0):
            return IntegrityResult("REPLAY", False, [f"sequence number {claim['seq']} already used by this source"],
                                   claim)
        if record:
            self.seen[claim["product_id"]] = (claim["capture_time"], claim["pixel_digest"])
            self.last_seq[claim["key_id"]] = max(claim["seq"], self.last_seq.get(claim["key_id"], 0))
        return IntegrityResult("VERIFIED", True, [f"signed by {claim['source']} ({claim['key_id']}), "
                                                  f"{len(steps)} processing step(s), digest matches"], claim)


def demo_setup(keys_dir: str | Path | None = None):
    """One source key + one processor key, and the matching public registry."""
    ks = Keystore(keys_dir)
    reg = Registry()
    reg.add("sat-01", ks.create("sat-01"), "source", "Sentinel-2 emulator")
    reg.add("proc-01", ks.create("proc-01"), "processor", "ground processing")
    src = SourceSigner("sat-01", ks.load("sat-01"), source="ESA Copernicus (emulated)")
    proc = ProcessorSigner("proc-01", ks.load("proc-01"))
    return ks, reg, src, proc
