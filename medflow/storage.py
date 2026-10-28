"""The only module that reads or writes stored data. Two backends, chosen by config STORAGE:

``json`` (offline development and most tests): each collection is a list of flat
objects in ``<DATA_DIR>/<name>.json``. Writes are atomic: ``save`` writes a temp
file in the same folder, flushes it to disk, then swaps it in with ``os.replace``.

``supabase`` (the primary database): each collection is a Postgres table. Every
request uses the publishable key plus the signed-in user's access token, so
Row-Level Security (supabase/schema.sql) limits it to that user's rows. No
privileged key is used anywhere. Rows come back without ``user_id``; the
database fills it in from the token on insert.

Every change goes through ``modify``, which loads, lets the caller change the
records, and saves, all while holding one lock. ``flask run`` serves requests on
several threads, so without this two requests could both load the same data and
the second save would silently drop the first change. ``load`` takes the same
lock in JSON mode because on Windows ``os.replace`` fails while another thread
has the file open for reading.

Limits:
- The lock lives in this process. It is right for ``flask run`` (one process,
  many threads), not for several server processes, two apps sharing a folder,
  or several Vercel instances.
- JSON: each file write is atomic, but a change that spans two collections is
  two writes. A crash between them can leave the files out of step, so pages
  must tolerate references to records that no longer exist.
- Supabase: ``modify`` saves by comparing the records before and after the
  block and sending the differences: deletes, then one update per changed row,
  then inserts. These are separate requests, not one transaction, so a failure
  part-way can leave some of a change saved (the error page says to reload and
  check). Two requests changing the same row at once: the last write wins.
  Two creating a record at once can pick the same id; the second gets a
  primary-key error and nothing of it is saved. A table read returns at most
  1000 rows (Supabase's default), far more than a demo user has.
"""

import copy
import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager

import httpx
from flask import current_app, g
from postgrest.exceptions import APIError
from supabase import ClientOptions, create_client

_NAME = re.compile(r"[a-z_]+")
# Re-entrant so modify() can call load()/save(), and one modify() can nest another.
_lock = threading.RLock()


class StorageError(Exception):
    """A data file exists but is corrupt. Never overwritten automatically."""

    def __init__(self, collection: str, detail: str):
        super().__init__(f"{collection}.json {detail}")
        self.collection = collection


class DatabaseError(Exception):
    """Supabase refused or couldn't be reached. The detail is for the server log only."""


class SignedOut(DatabaseError):
    """Supabase rejected the user's access token (usually because it expired)."""


def _supabase() -> bool:
    return current_app.config["STORAGE"] == "supabase"


def _path(name: str, folder: str | None = None) -> str:
    # Collection names come from code, never from users; the check keeps it that way.
    if not _NAME.fullmatch(name):
        raise ValueError(f"Invalid collection name: {name!r}")
    return os.path.join(folder or current_app.config["DATA_DIR"], f"{name}.json")


def load(name: str) -> list[dict]:
    """Return all records in a collection; a missing file is an empty collection."""
    if _supabase():
        return _sb_load(name)
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
    """Replace a collection's file atomically. JSON backend only; routes use modify() instead."""
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
        if _supabase():
            before = copy.deepcopy(records)
            yield records
            _sb_save(name, before, records)
        else:
            yield records
            save(name, records)


def next_id(records: list[dict]) -> int:
    return max((r["id"] for r in records), default=0) + 1


def changes(before: list[dict], after: list[dict]) -> tuple[list[dict], dict[int, dict], list[int]]:
    """What turns ``before`` into ``after``: (new records, {id: changed fields}, deleted ids)."""
    old = {r["id"]: r for r in before}
    new = {}
    for r in after:
        if r["id"] in new:
            raise ValueError(f"Two records share id {r['id']}")
        new[r["id"]] = r
    inserts = [r for i, r in new.items() if i not in old]
    updates = {}
    for i, r in new.items():
        if i in old:
            changed = {k: v for k, v in r.items() if k not in old[i] or old[i][k] != v}
            if changed:
                updates[i] = changed
    deletes = [i for i in old if i not in new]
    return inserts, updates, deletes


def _client():
    """This request's Supabase client, acting as the signed-in user."""
    if "supabase_client" not in g:
        token = g.get("access_token")
        if not token:
            raise RuntimeError("Supabase storage was used without a signed-in user.")
        g.supabase_client = create_client(
            current_app.config["SUPABASE_URL"],
            current_app.config["SUPABASE_PUBLISHABLE_KEY"],
            ClientOptions(headers={"Authorization": f"Bearer {token}"},
                          auto_refresh_token=False, persist_session=False),
        )
    return g.supabase_client


def _run(query, name: str):
    try:
        return query.execute().data
    except APIError as e:
        # PGRST30x: the token is missing, invalid or expired. Only codes go to the log, never data.
        if (e.code or "").startswith("PGRST30"):
            raise SignedOut(f"{name}: {e.code}") from e
        raise DatabaseError(f"{name}: {e.code} {e.message}") from e
    except httpx.HTTPError as e:
        raise DatabaseError(f"{name}: {type(e).__name__}") from e


def _sb_load(name: str) -> list[dict]:
    if not _NAME.fullmatch(name):
        raise ValueError(f"Invalid collection name: {name!r}")
    rows = _run(_client().table(name).select("*").order("id"), name)
    for row in rows:
        row.pop("user_id", None)
    return rows


def _sb_save(name: str, before: list[dict], after: list[dict]) -> None:
    inserts, updates, deletes = changes(before, after)
    table = _client().table(name)
    # Deletes first so an id that is freed and reused in one change can't collide.
    if deletes:
        _run(table.delete().in_("id", deletes), name)
    for record_id, fields in updates.items():
        if not _run(table.update(fields).eq("id", record_id), name):
            raise DatabaseError(f"{name}: row {record_id} was deleted elsewhere")
    if inserts:
        # Missing fields take the column default rather than null.
        _run(table.insert(inserts, default_to_null=False), name)


def _seed_names() -> list[str]:
    # Sorted order is also dependency order: expenses link to appointments.
    seed_dir = current_app.config["SEED_DIR"]
    return sorted(f[:-5] for f in os.listdir(seed_dir) if f.endswith(".json"))


def _load_seed(name: str) -> list[dict]:
    with open(_path(name, current_app.config["SEED_DIR"]), encoding="utf-8") as f:
        return json.load(f)


def seed_missing() -> None:
    """JSON backend: copy seed collections that don't exist yet; never touch existing data."""
    for name in _seed_names():
        if not os.path.exists(_path(name)):
            save(name, _load_seed(name))


def seed_if_empty() -> bool:
    """Give a user with no data at all the fictional demo data. True if it was added."""
    names = _seed_names()
    if any(load(name) for name in names):
        return False
    for name in names:
        with modify(name) as records:
            records.extend(_load_seed(name))
    return True


def reset() -> None:
    """Replace every seeded collection with its fictional demo data (this user's, on Supabase)."""
    names = _seed_names()
    if not _supabase():
        for name in names:
            save(name, _load_seed(name))
        return
    # Linking records go first and come back last, so no link ever points at a missing row.
    for name in reversed(names):
        with modify(name) as records:
            records.clear()
    for name in names:
        with modify(name) as records:
            records.extend(_load_seed(name))
