import json
import pytest
from fastapi.testclient import TestClient
from hermes_hoard.app import create_app


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ("TANTALUS_OFFLINE", "PHILEAS_OFFLINE"):
        monkeypatch.setenv(key, "1")
    for key in ("TANTALUS_BROWSER", "PHILEAS_BROWSER"):
        monkeypatch.setenv(key, "0")
    monkeypatch.setenv("HOARD_HUB_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("HOARD_FAUSTUS_URL", "http://127.0.0.1:1")


def client(app):
    return TestClient(app, base_url="http://127.0.0.1:5221")


def test_defaults_catalog_and_renamed_collision_routes(tmp_path):
    app = create_app(tmp_path, port=5221)
    with client(app) as c:
        assert not any(m["enabled"] for m in c.get("/api/modules").json()["modules"])
        tools = c.get("/api/agent/tools").json()["tools"]
        assert len(tools) == 114
        names = {t["name"] for t in tools}
        for name in ("settings_set", "scheduler_status", "notify_status"):
            assert "products_" + name in names
            assert "shipments_" + name in names
        assert not (tmp_path / "products").exists()
        assert not (tmp_path / "shipments").exists()
        assert c.post("/api/agent/call", json={"name": "hermes_modules"}).status_code == 401


@pytest.mark.parametrize("module", ["products", "shipments"])
def test_full_native_api_and_namespaced_mcp(module, tmp_path):
    app = create_app(tmp_path, port=5221)
    with client(app) as c:
        response = c.put(f"/api/modules/{module}", json={"enabled": True})
        assert response.status_code == 200, response.text
        assert c.get(f"/{module}/api/health").status_code == 200
        assert c.get(f"/{module}/").status_code == 200
        assert c.get(f"/{module}/api/agent/tools").json()["tools"]
        response = c.post("/api/agent/call", headers={"Authorization": "Bearer " + app.state.token},
                          json={"name": module + "_scheduler_status", "arguments": {}})
        assert response.status_code == 200, response.text
        other = "shipments" if module == "products" else "products"
        assert app.state.modules[other].app is None
        assert c.put(f"/api/modules/{module}", json={"enabled": False}).status_code == 200
        assert c.post(f"/{module}/api/agent/call", json={"name": "scheduler_status"}).status_code == 409


def test_persistence_stop_all_and_retained_paths(tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    marker = original / "keep.txt"
    marker.write_text("retained")
    data = tmp_path / "host"
    data.mkdir()
    (data / "modules.json").write_text(json.dumps({"enabled": [], "data_paths": {"products": str(original)}}))
    with client(create_app(data, port=5221)) as c:
        assert c.put("/api/modules/shipments", json={"enabled": True}).status_code == 200
        assert list(original.iterdir()) == [marker]
    with client(create_app(data, port=5221)) as c:
        assert next(m for m in c.get("/api/modules").json()["modules"] if m["id"] == "shipments")["enabled"]
        assert c.post("/api/modules/stop-all").status_code == 200
    with client(create_app(data, port=5221)) as c:
        assert not any(m["enabled"] for m in c.get("/api/modules").json()["modules"])
        assert c.put("/api/modules/products", json={"enabled": "false"}).status_code == 422
        assert c.put("/api/modules/missing", json={"enabled": True}).status_code == 404
        assert c.put("/api/modules/products", json={"enabled": True}, headers={"Origin": "https://example.com"}).status_code == 403
    assert marker.read_text() == "retained"
