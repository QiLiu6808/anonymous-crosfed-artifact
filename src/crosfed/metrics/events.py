from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MetricEvent:
    run_id: str
    phase: str
    actor_id: str
    round_id: int
    wall_seconds: float
    logical_bytes: int = 0
    wire_bytes: int = 0
    metadata: dict[str, Any] | None = None


class EventRecorder:
    def __init__(self, path: str | Path | None = None, truncate: bool = False) -> None:
        self.path = Path(path) if path is not None else None
        self.events: list[MetricEvent] = []
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if truncate:
                self.path.write_text("", encoding="utf-8")

    def record(self, event: MetricEvent) -> None:
        self.events.append(event)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(event), sort_keys=True) + "\n")


class PhaseTimer:
    def __init__(
        self,
        recorder: EventRecorder,
        run_id: str,
        phase: str,
        actor_id: str,
        round_id: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.recorder = recorder
        self.run_id = run_id
        self.phase = phase
        self.actor_id = actor_id
        self.round_id = round_id
        self.metadata = metadata
        self.logical_bytes = 0
        self.wire_bytes = 0
        self._started = 0.0

    def __enter__(self) -> "PhaseTimer":
        self._started = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type is None:
            self.recorder.record(
                MetricEvent(
                    self.run_id,
                    self.phase,
                    self.actor_id,
                    self.round_id,
                    time.perf_counter() - self._started,
                    self.logical_bytes,
                    self.wire_bytes,
                    self.metadata,
                )
            )
