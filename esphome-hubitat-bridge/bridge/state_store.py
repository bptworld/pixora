from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._state: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if not self._path.exists():
            self._state = {}
            return
        try:
            self._state = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._state = {}

    def get(self, key: str) -> Any:
        return self._state.get(key)

    def set(self, key: str, value: Any) -> None:
        self._state[key] = value
        self.save()

    def snapshot(self) -> dict[str, Any]:
        return dict(self._state)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(self._path.suffix + ".tmp")
        temp.write_text(json.dumps(self._state, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(self._path)
