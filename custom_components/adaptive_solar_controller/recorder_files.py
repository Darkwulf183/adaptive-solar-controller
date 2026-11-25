"""Flight recorder file helpers (no Home Assistant dependency, unit-testable)."""
from __future__ import annotations

import re
from pathlib import Path

FOLDER = "adaptive_solar_controller"
NAME_RE = re.compile(r"^ASC_v[0-9A-Za-z.]+_FlightRecorder_\d{4}-\d{2}-\d{2}(?:_old\d*)?\.csv$")


def valid_name(name: str) -> bool:
    return bool(name) and NAME_RE.match(name) is not None


def list_files(folder: Path) -> list[dict]:
    """Newest first. Only files that look like recorder files are listed."""
    out: list[dict] = []
    try:
        entries = list(folder.iterdir())
    except OSError:
        return out
    for p in entries:
        if valid_name(p.name) and p.is_file():
            try:
                st = p.stat()
            except OSError:
                continue
            out.append({"name": p.name, "size": st.st_size, "modified": st.st_mtime})
    out.sort(key=lambda f: (f["name"][-14:], f["modified"]), reverse=True)
    return out


def resolve(folder: Path, name: str) -> Path | None:
    """Return the file only when the name is a plain recorder file name inside ``folder``."""
    if not valid_name(name):
        return None
    path = folder / name
    try:
        if path.is_file() and path.resolve().parent == folder.resolve():
            return path
    except OSError:
        return None
    return None
