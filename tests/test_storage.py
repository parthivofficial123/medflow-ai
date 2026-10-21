import json

import pytest

from medflow import storage


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
