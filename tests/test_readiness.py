from fastapi.testclient import TestClient

from app.main import create_app


def test_readiness_checks_database_without_creating_it(tmp_path):
    path = tmp_path / "data" / "test.db"
    app = create_app(path)
    # Without ASGI startup, the probe must not create or migrate the database.
    assert TestClient(app).get("/ready").status_code == 503
    assert not path.exists()

    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        assert client.get("/vm").status_code == 200
