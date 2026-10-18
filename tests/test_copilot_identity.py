import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hermes_hoard.runtime import create_runtime
from hermes_hoard.native import SPECS, install_copilot

PORT = 5221
IDENTITIES = {'products': 'tantalus', 'shipments': 'phileas'}


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    requests = []
    original_client = httpx.AsyncClient
    def respond(request):
        requests.append(request)
        if request.url.path == "/api/hoard-copilot/capabilities":
            return httpx.Response(200, json={"contract_version": "1.0"})
        if request.url.path == "/api/hoard-copilot/sessions":
            return httpx.Response(200, json=json.loads(request.content))
        raise AssertionError("Unexpected transport: " + str(request.url))
    def client(*args, **kwargs):
        if "transport" not in kwargs:
            kwargs["transport"] = httpx.MockTransport(respond)
        return original_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    root = tmp_path / "surface"
    (root / "web").mkdir(parents=True)
    (root / "catalog.json").write_text("[]", encoding="utf-8")
    native_paths = {}
    def factory(key, path):
        native = FastAPI()
        native.state.sources_registry = SimpleNamespace()
        if key == "audio":
            from funes_hoard.hoard_link import family
            state = family.status()
            assert state["app"] == "funes", "Configure the shared Funes identity before building audio"
            path = Path(state["token_file"]).parent
        native_paths[key] = path
        install_copilot(native, IDENTITIES[key], str(path), app_name=key, faustus_urls=["http://fixture.invalid"], token="", inject=False)
        return native
    app = create_runtime(name="hermes", product="hermes", root=root, data_dir=tmp_path / "data",
                         specs=SPECS, factory=factory, port=PORT)
    # Existing saved conversation IDs must be adopted, never regenerated.
    for key, module in app.state.modules.items():
        module.data_dir.mkdir(parents=True, exist_ok=True)
        (module.data_dir / "copilot-space-id").write_text("saved-" + key, encoding="utf-8")
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as connection:
        yield app, connection, native_paths, requests


def test_every_native_assistant_keeps_origin_history_tools_and_proxy_context(synthetic):
    app, client, paths, requests = synthetic
    central = client.get("/api/copilot/info").json()
    assert central["app_id"] == "hermes"
    for key, app_id in IDENTITIES.items():
        response = client.put(f"/api/modules/{key}", json={"enabled": True})
        assert response.status_code == 200, response.text
        expected_path = app.state.modules["activity"].data_dir if key == "audio" else app.state.modules[key].data_dir
        expected_space = (expected_path / "copilot-space-id").read_text(encoding="utf-8")
        headers = {"Referer": f"http://127.0.0.1:{PORT}/{key}/#/history"}
        info = client.get("/api/copilot/info", headers=headers)
        assert info.status_code == 200, info.text
        info = info.json()
        assert info["app_id"] == info["tool_server_id"] == app_id
        assert info["data_space_id"] == expected_space
        direct = client.get(f"/{key}/api/copilot/info", follow_redirects=False)
        assert direct.status_code == 200 and direct.json() == info
        envelope = {"path": "/api/hoard-copilot/sessions", "method": "POST", "body": {"context": {"origin": {"selection": "kept"}}}}
        for url, referer in [("/api/copilot/proxy", headers), (f"/{key}/api/copilot/proxy", {})]:
            result = client.post(url, headers=referer, json=envelope, follow_redirects=False)
            assert result.status_code == 200, result.text
            origin = result.json()["context"]["origin"]
            assert origin == {"selection": "kept", "app_id": app_id, "data_space_id": expected_space}
    assert client.get("/api/copilot/info").json() == central
    for referer in ("http://elsewhere.invalid/screen/", f"http://127.0.0.1:{PORT}/missing/", "http://[invalid/"):
        assert client.get("/api/copilot/info", headers={"Referer": referer}).json() == central
    assert requests


def test_off_queries_cannot_open_native_history_or_start_an_engine(synthetic):
    app, client, paths, requests = synthetic
    def files():
        return {str(p): p.read_bytes() for p in app.state.data_dir.rglob("*") if p.is_file()}
    before = files()
    for key in IDENTITIES:
        headers = {"Referer": f"http://127.0.0.1:{PORT}/{key}/"}
        for url in ("/api/copilot/info", f"/{key}/api/copilot/info"):
            assert client.get(url, headers=headers, follow_redirects=False).status_code == 409
        for url in ("/api/copilot/proxy", f"/{key}/api/copilot/proxy"):
            assert client.post(url, headers=headers, json={"path": "/api/hoard-copilot/sessions"}, follow_redirects=False).status_code == 409
    assert not paths and not requests
    assert files() == before and all(module.app is None for module in app.state.modules.values())
    assert not list(app.state.data_dir.rglob("*.db"))
