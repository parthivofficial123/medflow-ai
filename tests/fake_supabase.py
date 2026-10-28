"""An in-memory stand-in for the parts of supabase-py MedFlow uses.

It enforces what supabase/schema.sql and RLS enforce, so tests catch the app relying
on anything the real database would refuse: each request acts as the user whose
token it carries, sees only that user's rows, can't write another user's user_id,
and gets the same error codes for duplicate ids, broken links and expired tokens.
"""

import copy
import itertools
import time
from types import SimpleNamespace

import httpx
from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError

COLUMNS = {
    "appointments": {
        "id": None, "date": None, "time": None, "provider": None, "location": "", "reason": None,
        "notes": "", "status": "scheduled", "reminder_days_before": None, "reminder_dismissed": False,
        "tasks": [], "created_at": None, "updated_at": None,
    },
    "expenses": {
        "id": None, "date": None, "provider": None, "description": "", "category": None,
        "estimated_cents": None, "actual_cents": None, "paid_cents": 0, "appointment_id": None,
        "appointment_label": None, "source": None, "created_at": None, "updated_at": None,
    },
}


class FakeSupabase:
    def __init__(self):
        self.rows = {name: [] for name in COLUMNS}
        self.tokens = {}       # access token -> user id
        self.codes = {}        # sign-in code -> (verifier, user id, email)
        self.expired = set()
        self.signed_out = []
        self.requests = []     # (table, operation) for every request, in order
        self.fail_on = None    # (table, operation) that raises a network error
        self._counter = itertools.count(1)

    def add_user(self, email):
        n = next(self._counter)
        user_id, token = f"user-{n}", f"token-{n}"
        self.tokens[token] = user_id
        return user_id, token

    def create_client(self, url, key, options=None):
        assert url.startswith("https://") and "/rest/" not in url
        assert key.startswith("sb_publishable_"), "MedFlow must only use the publishable key"
        auth = (options.headers or {}).get("Authorization", "") if options else ""
        token = auth.removeprefix("Bearer ") if auth else None
        return FakeClient(self, token)

    def user_rows(self, table, user_id):
        return [r for r in self.rows[table] if r["user_id"] == user_id]


def api_error(code, message):
    return APIError({"code": code, "message": message, "hint": None, "details": None})


class FakeClient:
    def __init__(self, db, token):
        self.db, self.token = db, token
        self.auth = FakeAuth(db)

    def table(self, name):
        return FakeQuery(self, name)

    def user_id(self):
        if self.token in self.db.expired:
            raise api_error("PGRST303", "JWT expired")
        if self.token not in self.db.tokens:
            raise api_error("42501", "permission denied for table")  # anon has no grants
        return self.db.tokens[self.token]


class FakeQuery:
    def __init__(self, client, table):
        self.client, self.table = client, table
        self.op, self.payload, self.filters = None, None, []

    def select(self, columns):
        self.op = "select"
        return self

    def order(self, column):
        return self

    def insert(self, rows, default_to_null=True):
        assert default_to_null is False, "missing fields must take the column default"
        self.op, self.payload = "insert", rows if isinstance(rows, list) else [rows]
        return self

    def update(self, fields):
        self.op, self.payload = "update", fields
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r[column] == value)
        return self

    def in_(self, column, values):
        self.filters.append(lambda r: r[column] in values)
        return self

    def execute(self):
        db = self.client.db
        db.requests.append((self.table, self.op))
        if db.fail_on == (self.table, self.op):
            raise httpx.ConnectError("fake network failure")
        user_id = self.client.user_id()
        # RLS: every operation only ever sees the caller's own rows.
        visible = [r for r in db.user_rows(self.table, user_id) if all(f(r) for f in self.filters)]
        return SimpleNamespace(data=getattr(self, f"_{self.op}")(db, user_id, visible))

    def _select(self, db, user_id, visible):
        return [copy.deepcopy(r) for r in sorted(visible, key=lambda r: r["id"])]

    def _insert(self, db, user_id, visible):
        new_rows = []
        for row in self.payload:
            unknown = set(row) - set(COLUMNS[self.table]) - {"user_id"}
            if unknown:
                raise api_error("PGRST204", f"unknown columns {sorted(unknown)}")
            if row.get("user_id", user_id) != user_id:
                raise api_error("42501", "new row violates row-level security policy")
            full = {**copy.deepcopy(COLUMNS[self.table]), **copy.deepcopy(row), "user_id": user_id}
            self._check(db, user_id, full, new_rows)
            new_rows.append(full)
        db.rows[self.table].extend(new_rows)
        return copy.deepcopy(new_rows)

    def _update(self, db, user_id, visible):
        if "user_id" in self.payload or "id" in self.payload:
            raise api_error("42501", "MedFlow never changes user_id or id")
        for row in visible:
            self._check(db, user_id, {**row, **self.payload}, [], updating=row)
        for row in visible:
            row.update(copy.deepcopy(self.payload))
        return copy.deepcopy(visible)

    def _delete(self, db, user_id, visible):
        db.rows[self.table] = [r for r in db.rows[self.table] if not any(r is v for v in visible)]
        if self.table == "appointments":
            # on delete set null (appointment_id)
            gone = {r["id"] for r in visible}
            for e in db.user_rows("expenses", user_id):
                if e["appointment_id"] in gone:
                    e["appointment_id"] = None
        return copy.deepcopy(visible)

    def _check(self, db, user_id, row, pending, updating=None):
        others = [r for r in db.user_rows(self.table, user_id) + pending if r is not updating]
        if any(r["id"] == row["id"] for r in others):
            raise api_error("23505", "duplicate key value violates unique constraint")
        if self.table == "expenses" and row["appointment_id"] is not None:
            if not any(a["id"] == row["appointment_id"] for a in db.user_rows("appointments", user_id)):
                raise api_error("23503", "violates foreign key constraint")
        if self.table == "expenses" and row["estimated_cents"] is None and row["actual_cents"] is None:
            raise api_error("23514", "violates check constraint")


class FakeAuth:
    def __init__(self, db):
        self.db = db
        self.admin = SimpleNamespace(sign_out=self.sign_out)

    def exchange_code_for_session(self, params):
        found = self.db.codes.pop(params["auth_code"], None)
        if found is None or found[0] != params["code_verifier"]:
            raise AuthApiError("invalid flow state", 400, "bad_code_verifier")
        _, user_id, email = found
        token = next(t for t, u in self.db.tokens.items() if u == user_id)
        session = SimpleNamespace(access_token=token, refresh_token="refresh-" + token,
                                  expires_at=int(time.time()) + 3600)
        return SimpleNamespace(session=session, user=SimpleNamespace(id=user_id, email=email))

    def sign_out(self, jwt, scope="global"):
        self.db.signed_out.append((jwt, scope))
