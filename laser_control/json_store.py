from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def read_json_object(path: str | Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return dict(default or {})
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        backup = source.with_suffix(source.suffix + ".corrupt")
        try:
            source.replace(backup)
        except OSError:
            pass
        raise ValueError(f"JSON-Datei ist beschaedigt: {source}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON-Datei enthaelt kein Objekt: {source}")
    return data


def write_json_object(path: str | Path, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        try:
            backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, target)

