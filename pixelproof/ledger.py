"""Tamper-evident audit log: append-only JSON lines, each entry hashing the previous one.
Editing or deleting any past line breaks the chain, which `verify()` reports."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from .provenance import GENESIS, canonical, sha256_hex


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._lock = threading.Lock()

    def _head(self) -> str:
        last = GENESIS
        for line in self.path.read_text().splitlines():
            if line.strip():
                last = json.loads(line)["hash"]
        return last

    def append(self, event: dict) -> dict:
        with self._lock:
            prev = self._head()
            body = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "prev": prev, **event}
            entry = {**body, "hash": sha256_hex(canonical(body))}
            with self.path.open("a") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
            return entry

    def entries(self) -> list[dict]:
        return [json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]

    def verify(self) -> tuple[bool, int | None]:
        prev = GENESIS
        for i, e in enumerate(self.entries()):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("prev") != prev or sha256_hex(canonical(body)) != e.get("hash"):
                return False, i
            prev = e["hash"]
        return True, None
