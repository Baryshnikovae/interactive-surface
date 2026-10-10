"""Atomic storage outside the checkout; calibration becomes stale when devices change."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


def default_path() -> Path:
    override = os.getenv("INTERACTIVE_SURFACE_CONFIG")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "interactive-surface" / "calibration.json"


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()

    def read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) and data.get("schema") == 1 else {}
        except (OSError, ValueError):
            return {}

    def write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".cal-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"schema": 1, **data}, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
