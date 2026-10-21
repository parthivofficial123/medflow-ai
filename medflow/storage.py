"""JSON file storage: the only module that reads or writes data files.

Each collection is a list of flat objects in ``<DATA_DIR>/<name>.json``.

Writes are atomic: ``save`` writes a temp file in the same folder, flushes it to
disk, then swaps it in with ``os.replace``. A crash or error mid-write leaves the
previous file intact, never a half-written one.

Every change goes through ``modify``, which loads, lets the caller change the
records, and saves, all while holding one lock. ``flask run`` serves requests on
several threads, so without this two requests could both load the same data and
the second save would silently drop the first change. ``load`` takes the same
lock because on Windows ``os.replace`` fails while another thread has the file
open for reading.

Limits:
- The lock lives in this process. It is right for ``flask run`` (one process,
  many threads), not for several server processes or two apps sharing a folder.
- Each file write is atomic, but a change that spans two collections is two
  writes. A crash between them can leave the files out of step, so pages must
  tolerate references to records that no longer exist.
"""

import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager

from flask import current_app

_NAME = re.compile(r"[a-z_]+")
# Re-entrant so modify() can call load()/save(), and one modify() can nest another.
_lock = threading.RLock()


class StorageError(Exception):
    """A data file exists but is corrupt. Never overwritten automatically."""

    def __init__(self, collection: str, detail: str):
        super().__init__(f"{collection}.json {detail}")
        self.collection = collection


def _path(name: str, folder: str | None = None) -> str:
    # Collection names come from code, never from users; the check keeps it that way.
    if not _NAME.fullmatch(name):
        raise ValueError(f"Invalid collection name: {name!r}")
    return os.path.join(folder or current_app.config["DATA_DIR"], f"{name}.json")


def load(name: str) -> list[dict]:
    """Return all records in a collection; a missing file is an empty collection."""
    path = _path(name)
    try:
        with _lock, open(path, encoding="utf-8") as f:
            records = json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as e:
        raise StorageError(name, f"is not valid JSON ({e}). Path: {path}") from e
    if not isinstance(records, list):
        raise StorageError(name, f"must contain a JSON list. Path: {path}")
    return records


def save(name: str, records: list[dict]) -> None:
    """Replace a collection's file atomically. Routes use modify() instead."""
    path = _path(name)
    with _lock:
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


@contextmanager
def modify(name: str):
    """Load -> change -> save as one locked step.

        with storage.modify("appointments") as records:
            records.append(...)

    If the block raises (including abort(404)), nothing is saved.
    """
    with _lock:
        records = load(name)
        yield records
        save(name, records)


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
