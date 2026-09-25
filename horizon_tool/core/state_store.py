"""Per-script step state, persisted atomically for Resume (AC-06/AC-07)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from horizon_tool.core.statuses import STATUS_DONE, STATUS_SKIPPED, STATUS_REJECTED

# Steps that are considered finished and are NOT redone on Resume. A FAILED or
# absent step is unfinished and will be retried.
TERMINAL = {STATUS_DONE, STATUS_SKIPPED, STATUS_REJECTED}


class StateStore:
    """Tracks each script's per-step status + metadata, saved atomically.

    Layout: {"scripts": {"<ordinal>": {"steps": {...}, "meta": {...}}}}.
    Every mutation persists immediately so a crash mid-run is resumable.

    Single-writer assumption: one StateStore instance is mutated from a single
    thread (the run worker). It is not safe to write from two threads at once —
    a concurrent mutation during ``_save``'s ``json.dump`` could raise. The GUI
    thread should read state only after the worker has finished, not during a run.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._data: dict[str, Any] = {"scripts": {}}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._data = {"scripts": {}}
            return
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._data = data if isinstance(data, dict) and "scripts" in data else {"scripts": {}}
        except (json.JSONDecodeError, OSError):
            self._data = {"scripts": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _script(self, ordinal: int) -> dict[str, Any]:
        return self._data["scripts"].setdefault(str(ordinal), {"steps": {}, "meta": {}})

    def set_step(self, ordinal: int, step: str, status: str) -> None:
        self._script(ordinal)["steps"][step] = status
        self._save()

    def get_step(self, ordinal: int, step: str) -> str | None:
        return self._data["scripts"].get(str(ordinal), {}).get("steps", {}).get(step)

    def is_done(self, ordinal: int, step: str) -> bool:
        return self.get_step(ordinal, step) in TERMINAL

    def set_meta(self, ordinal: int, key: str, value: Any) -> None:
        self._script(ordinal)["meta"][key] = value
        self._save()

    def get_meta(self, ordinal: int, key: str) -> Any:
        return self._data["scripts"].get(str(ordinal), {}).get("meta", {}).get(key)
