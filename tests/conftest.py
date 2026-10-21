import re

import pytest

from medflow import create_app


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "instance"


@pytest.fixture
def app(data_dir):
    # Each test gets its own copy of the seed data; instance/ is never touched.
    return create_app({"TESTING": True, "SECRET_KEY": "test-secret", "DATA_DIR": str(data_dir)})


@pytest.fixture
def client(app):
    return app.test_client()


def get_csrf_token(client, path="/appointments/"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
