"""Final decision: two independent answers, as the track requires
("distinguish post-capture integrity from semantic truth"), plus the response.

                      content: no traces            content: manipulation found
integrity VERIFIED    VERIFIED                      SIGNED_BUT_SUSPICIOUS  (faked before signing?)
integrity FAILED      ALTERED_AFTER_CAPTURE         ALTERED_AFTER_CAPTURE  (+ type, heatmap)
no provenance         UNVERIFIED_NO_TRACES          SUSPICIOUS             (+ type, heatmap)

UNVERIFIED_NO_TRACES is never called "authentic": absence of traces is not proof.
Response: everything except VERIFIED and UNVERIFIED_NO_TRACES is QUARANTINED (kept, not deleted,
withheld from downstream products, released only by an analyst decision that is logged).
"""
from __future__ import annotations

from .provenance import IntegrityResult

RELEASED = {"VERIFIED", "UNVERIFIED_NO_TRACES"}


def combine(integrity: IntegrityResult, content: dict | None) -> dict:
    manipulated = bool(content and content.get("manipulated"))
    if integrity.status == "VERIFIED":
        verdict = "SIGNED_BUT_SUSPICIOUS" if manipulated else "VERIFIED"
    elif integrity.status == "NO_PROVENANCE":
        verdict = "SUSPICIOUS" if manipulated else "UNVERIFIED_NO_TRACES"
    else:
        verdict = "ALTERED_AFTER_CAPTURE"
    reasons = list(integrity.reasons)
    if content:
        reasons += [f"content: {content['type']} (score {content['manipulation_score']:.2f} vs threshold "
                    f"{content['threshold']:.2f})"] + content.get("evidence", [])
    return {
        "verdict": verdict,
        "action": "RELEASE" if verdict in RELEASED else "QUARANTINE",
        "integrity": {"status": integrity.status, "ok": integrity.ok},
        "content": {k: v for k, v in (content or {}).items() if k != "heatmap"},
        "reasons": reasons,
    }
