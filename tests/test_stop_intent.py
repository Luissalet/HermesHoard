import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI

from hermes_hoard.runtime import create_runtime


@pytest.mark.asyncio
async def test_off_is_saved_before_slow_shutdown_and_dashboard_stays_available(tmp_path):
    release, closing = asyncio.Event(), asyncio.Event()

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            closing.set()
            await release.wait()

    web = tmp_path / "web"
    web.mkdir()
    (tmp_path / "catalog.json").write_text("[]")
    data = tmp_path / "data"
    app = create_runtime(name="Fixture", product="fixture", root=tmp_path, data_dir=data,
                         specs=[{"id": "work", "name": "Fixture"}], factory=lambda *args: FastAPI(lifespan=lifespan), port=5220)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:5220") as client:
            assert (await client.put("/api/modules/work", json={"enabled": True})).status_code == 200
            task = asyncio.create_task(client.put("/api/modules/work", json={"enabled": False}))
            try:
                await asyncio.wait_for(closing.wait(), 2)
                assert json.loads((data / "modules.json").read_text())["enabled"] == []
                assert not task.done()
                assert (await asyncio.wait_for(client.get("/api/health"), 2)).status_code == 200
            finally:
                release.set()
            assert (await task).json()["enabled"] is False
