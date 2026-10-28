import json

import pytest
from flask import g

from medflow import storage
from tests.conftest import sign_in


@pytest.fixture(autouse=True)
def ctx(app):
    with app.app_context():
        yield


def test_round_trip():
    records = [{"id": 1, "name": "Café visit"}]
    storage.save("things", records)
    assert storage.load("things") == records


def test_missing_file_loads_as_empty_list():
    assert storage.load("nothing_here") == []


def test_corrupt_file_raises_and_is_left_alone(data_dir):
    path = data_dir / "broken.json"
    path.write_text("[{not json", encoding="utf-8")
    with pytest.raises(storage.StorageError, match="not valid JSON"):
        storage.load("broken")
    assert path.read_text(encoding="utf-8") == "[{not json"


def test_non_list_file_raises(data_dir):
    (data_dir / "obj.json").write_text('{"id": 1}', encoding="utf-8")
    with pytest.raises(storage.StorageError, match="JSON list"):
        storage.load("obj")


def test_failed_save_keeps_previous_file_and_leaves_no_temp_file(data_dir, monkeypatch):
    storage.save("things", [{"id": 1}])

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", explode)
    with pytest.raises(OSError):
        storage.save("things", [{"id": 1}, {"id": 2}])

    monkeypatch.undo()
    assert storage.load("things") == [{"id": 1}]
    assert not list(data_dir.glob("*.tmp"))


@pytest.mark.parametrize("name", ["../secrets", "Appointments", "a/b", "", "x.json"])
def test_rejects_unsafe_collection_names(name):
    with pytest.raises(ValueError):
        storage.load(name)


def test_modify_saves_changes():
    storage.save("things", [{"id": 1}])
    with storage.modify("things") as records:
        records.append({"id": 2})
    assert storage.load("things") == [{"id": 1}, {"id": 2}]


def test_modify_saves_nothing_if_the_block_fails():
    storage.save("things", [{"id": 1}])
    with pytest.raises(RuntimeError):
        with storage.modify("things") as records:
            records.append({"id": 2})
            raise RuntimeError("validation failed halfway")
    assert storage.load("things") == [{"id": 1}]


def test_next_id():
    assert storage.next_id([]) == 1
    assert storage.next_id([{"id": 1}, {"id": 7}, {"id": 3}]) == 8


def test_seed_missing_does_not_overwrite_existing_data(app):
    storage.save("appointments", [{"id": 99}])
    storage.seed_missing()
    assert storage.load("appointments") == [{"id": 99}]


def test_reset_restores_seed(app):
    storage.save("appointments", [])
    storage.reset()
    with open(f"{app.config['SEED_DIR']}/appointments.json", encoding="utf-8") as f:
        assert storage.load("appointments") == json.load(f)


def test_changes_lists_new_changed_and_deleted_records():
    before = [{"id": 1, "a": 1}, {"id": 2, "a": 2}, {"id": 3, "a": 3}]
    after = [{"id": 1, "a": 1}, {"id": 2, "a": 20, "b": None}, {"id": 4, "a": 4}]
    assert storage.changes(before, after) == ([{"id": 4, "a": 4}], {2: {"a": 20, "b": None}}, [3])


def test_changes_compares_nested_values():
    before = [{"id": 1, "tasks": [{"id": 1, "done": False}]}]
    after = [{"id": 1, "tasks": [{"id": 1, "done": True}]}]
    assert storage.changes(before, after)[1] == {1: {"tasks": [{"id": 1, "done": True}]}}


def test_changes_refuses_duplicate_ids():
    with pytest.raises(ValueError):
        storage.changes([], [{"id": 1}, {"id": 1}])


def test_supabase_load_hides_user_id(sb_app, fake_db):
    sign_in(sb_app, fake_db)
    with sb_app.test_request_context():
        g.access_token = next(iter(fake_db.tokens))
        records = storage.load("appointments")
    assert records and all("user_id" not in r for r in records)


def test_supabase_modify_saves_nothing_if_the_block_fails(sb_app, fake_db):
    sign_in(sb_app, fake_db)
    fake_db.requests.clear()
    with sb_app.test_request_context():
        g.access_token = next(iter(fake_db.tokens))
        with pytest.raises(RuntimeError):
            with storage.modify("appointments") as records:
                records.clear()
                raise RuntimeError("stop")
    assert fake_db.requests == [("appointments", "select")]


def test_supabase_storage_needs_a_signed_in_user(sb_app):
    with sb_app.test_request_context():
        with pytest.raises(RuntimeError, match="signed-in"):
            storage.load("appointments")
