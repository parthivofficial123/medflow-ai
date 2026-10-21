"""JSON file storage: the only module that reads or writes data files.

Each collection is a list of flat objects in ``<DATA_DIR>/<name>.json``.

Writes are atomic: ``save`` writes a temp file in the same folder, flushes it to
disk, then swaps it in with ``os.replace``. A crash or error mid-write leaves the
previous file intact, never a half-written one.

NOT protected: concurrent updates. A route does load -> change -> save, so two
requests changing the same collection at the same moment can lose one of the
changes (last write wins). That is acceptable for a single-user local demo on the
Flask dev server; anything multi-user needs a file lock or a real database.
"""

import json
import os
import re
import tempfile

from flask import current_app

_NAME = re.compile(r"[a-z_]+")


class StorageError(Exception):
    """A data file exists but cannot be used. Never overwritten automatically."""


def _path(name: str, folder: str | None = None) -> str:
    # Collection names come from code, never from users; the check keeps it that way.
    if not _NAME.fullmatch(name):
        raise ValueError(f"Invalid collection name: {name!r}")
    return os.path.join(folder or current_app.config["DATA_DIR"], f"{name}.json")


def load(name: str) -> list[dict]:
    """Return all records in a collection; a missing file is an empty collection."""
    path = _path(name)
    try:
        with open(path, encoding="utf-8") as f:
            records = json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as e:
        raise StorageError(
            f"{path} is not valid JSON ({e}). Fix it by hand or run "
            "'flask --app medflow reset-demo'."
        ) from e
    if not isinstance(records, list):
        raise StorageError(f"{path} must contain a JSON list.")
    return records


def save(name: str, records: list[dict]) -> None:
    """Replace a collection's file atomically."""
    path = _path(name)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=f".{name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.remove(tmp)
        raise


def next_id(records: list[dict]) -> int:
    return max((r["id"] for r in records), default=0) + 1


def _seed_names() -> list[str]:
    seed_dir = current_app.config["SEED_DIR"]
    return sorted(f[:-5] for f in os.listdir(seed_dir) if f.endswith(".json"))


def _load_seed(name: str) -> list[dict]:
    with open(_path(name, current_app.config["SEED_DIR"]), encoding="utf-8") as f:
        return json.load(f)


def seed_missing() -> None:
    """Copy seed collections that don't exist yet; never touch existing data."""
    for name in _seed_names():
        if not os.path.exists(_path(name)):
            save(name, _load_seed(name))


def reset() -> None:
    """Overwrite every seeded collection with its fictional demo data."""
    for name in _seed_names():
        save(name, _load_seed(name))
