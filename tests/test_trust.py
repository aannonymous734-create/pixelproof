import copy

import numpy as np
import pytest

from pixelproof.integrity_attacks import ATTACKS
from pixelproof.ledger import Ledger
from pixelproof.provenance import Verifier, demo_setup, pixel_digest
from pixelproof.verdict import combine


def test_windows_utf8_bom_in_manifest_and_registry_is_accepted(tmp_path, capsys):
    """PowerShell 5.1 and Notepad save JSON with a UTF-8 BOM; the tools must still read it."""
    import json
    from pixelproof import cli
    from pixelproof.imageio import to_png_bytes
    _, reg, src, _proc = demo_setup(tmp_path / "keys")
    img = textured(21)
    (tmp_path / "p.png").write_bytes(to_png_bytes(img))
    (tmp_path / "m.json").write_text(json.dumps(src.capture(img, "BOM-1", "2026-09-01T10:00:00+00:00")),
                                     encoding="utf-8-sig")
    reg.save(tmp_path / "r.json")
    (tmp_path / "r.json").write_text((tmp_path / "r.json").read_text(), encoding="utf-8-sig")
    with pytest.raises(SystemExit) as e:  # `verify` exits 0 when VERIFIED
        cli.main(["verify", "--image", str(tmp_path / "p.png"), "--manifest", str(tmp_path / "m.json"),
                  "--registry", str(tmp_path / "r.json")])
    assert e.value.code == 0 and "VERIFIED" in capsys.readouterr().out


def test_cli_fingerprints_match_the_registry_and_contain_no_private_key(tmp_path, capsys):
    """The out-of-band check: the fingerprint printed from a registry equals SHA-256 of each public key."""
    from pixelproof import cli
    from pixelproof.provenance import b64d, sha256_hex
    _, reg, _, _ = demo_setup(tmp_path / "keys")
    reg.save(tmp_path / "registry.json")
    cli.main(["fingerprints", "--registry", str(tmp_path / "registry.json")])
    out = capsys.readouterr().out
    for kid, k in reg.keys.items():
        assert kid in out and sha256_hex(b64d(k["public_key"])) in out
    assert "PRIVATE" not in out


def textured(seed):
    rng = np.random.default_rng(seed)
    base = np.cumsum(np.cumsum(rng.normal(0, 3, (64, 64, 3)), 0), 1)
    base = (base - base.min()) / (np.ptp(base) + 1e-6) * 200 + 20
    return np.clip(base + rng.normal(0, 4, base.shape), 0, 255).astype(np.uint8)


@pytest.fixture()
def setup(tmp_path):
    _, reg, src, proc = demo_setup(tmp_path / "keys")
    return reg, src, proc


def signed(src, proc, img, i):
    m = src.capture(img, f"P{i}", f"2026-09-01T10:{i:02d}:00+00:00")
    return proc.record(m, "export", {"format": "png"}, img)


def test_digest_is_pixel_based():
    img = textured(0)
    assert pixel_digest(img) == pixel_digest(img.copy())
    img2 = img.copy()
    img2[10, 10, 1] ^= 1
    assert pixel_digest(img) != pixel_digest(img2)


def test_genuine_verifies(setup):
    reg, src, proc = setup
    v = Verifier(reg)
    for i in range(3):
        img = textured(i)
        assert v.verify(img, signed(src, proc, img, i)).status == "VERIFIED"


@pytest.mark.parametrize("name", sorted(ATTACKS))
def test_every_attack_is_caught(setup, name):
    reg, src, proc = setup
    v = Verifier(reg)
    imgs = [textured(i) for i in range(2)]
    ms = [signed(src, proc, im, i) for i, im in enumerate(imgs)]
    for im, m in zip(imgs, ms):
        assert v.verify(im, m).status == "VERIFIED"
    fn, expected, _ = ATTACKS[name]
    a_img, a_m = fn(imgs[0], ms[0], np.random.default_rng(1), other=imgs[1])
    assert v.verify(a_img, a_m).status == expected


def test_revoked_key(setup):
    reg, src, proc = setup
    img = textured(5)
    m = signed(src, proc, img, 5)
    reg.revoke("sat-01")
    assert Verifier(reg).verify(img, m).status == "REVOKED_KEY"


def test_future_date_rejected(setup):
    reg, src, proc = setup
    img = textured(6)
    m = src.capture(img, "PF", "2099-01-01T00:00:00+00:00")
    assert Verifier(reg).verify(img, m).status == "TIME_IMPLAUSIBLE"


def test_lookup_mode_does_not_flag_reverification(setup):
    reg, src, proc = setup
    v = Verifier(reg)
    img = textured(7)
    m = signed(src, proc, img, 7)
    assert v.verify(img, m).status == "VERIFIED"
    assert v.verify(img, copy.deepcopy(m), record=False).status == "VERIFIED"  # analyst re-check
    assert v.verify(img, copy.deepcopy(m), record=True).status == "REPLAY"     # second downlink


def test_ledger_detects_tampering(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    for i in range(5):
        led.append({"i": i, "verdict": "VERIFIED"})
    assert led.verify() == (True, None)
    lines = led.path.read_text().splitlines()
    lines[2] = lines[2].replace("VERIFIED", "ALTERED")
    led.path.write_text("\n".join(lines) + "\n")
    ok, bad = led.verify()
    assert not ok and bad == 2


def test_two_axis_verdicts(setup):
    reg, src, proc = setup
    v = Verifier(reg)
    img = textured(8)
    good = v.verify(img, signed(src, proc, img, 8))
    clean = {"manipulated": False, "type": "authentic", "manipulation_score": .1, "threshold": .5}
    dirty = {"manipulated": True, "type": "copy_move", "manipulation_score": .9, "threshold": .5}
    assert combine(good, clean)["verdict"] == "VERIFIED"
    assert combine(good, dirty)["verdict"] == "SIGNED_BUT_SUSPICIOUS"
    none = v.verify(img, None)
    assert combine(none, clean)["verdict"] == "UNVERIFIED_NO_TRACES"
    assert combine(none, dirty)["action"] == "QUARANTINE"
