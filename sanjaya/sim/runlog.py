"""Run logging and replay.

Every run writes an append-only JSONL file: one event per line, with a
monotonically increasing sequence number. Anything the advisor saw or decided
is an event. The reader returns the events in order, so any run can be
replayed bit-for-bit. This is the audit trail the whole system rests on.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def _jsonable(x: Any) -> Any:
    if is_dataclass(x) and not isinstance(x, type):
        return asdict(x)
    return x


class RunLogger:
    def __init__(self, path: Path | str, run_id: str):
        self.path = Path(path)
        self.run_id = run_id
        self._seq = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("w", encoding="utf-8")

    def log(self, t: float, kind: str, payload: Any) -> int:
        self._seq += 1
        event = {"seq": self._seq, "run_id": self.run_id, "t": t, "kind": kind, "payload": _jsonable(payload)}
        self._f.write(json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n")
        return self._seq

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> "RunLogger":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_run(path: Path | str) -> Iterator[dict[str, Any]]:
    """Yield events in order, verifying the sequence is unbroken."""
    expected = 1
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            ev = json.loads(line)
            if ev["seq"] != expected:
                raise ValueError(f"run log corrupted: expected seq {expected}, got {ev['seq']}")
            expected += 1
            yield ev
