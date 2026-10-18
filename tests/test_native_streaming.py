import asyncio
import pytest
from fastapi import FastAPI
from starlette.responses import StreamingResponse

from hermes_hoard.native_response import NativeResponse
from hermes_hoard.runtime import Module


@pytest.mark.asyncio
async def test_sse_flows_before_completion_and_off_cancels_stream(tmp_path):
    native = FastAPI()
    blocked = asyncio.Event()

    @native.get("/api/events/live")
    async def live():
        async def chunks():
            yield b"data: first\n\n"
            await blocked.wait()
            yield b"data: second\n\n"
        return StreamingResponse(chunks(), media_type="text/event-stream")

    module = Module({"id": "audio", "name": "Audio"}, tmp_path, lambda *args: native)
    await module.set_enabled(True)
    sent = asyncio.Queue()

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        await sent.put(message)

    response = NativeResponse(module, "api/events/live", name="Talos", product="talos", on_quit=lambda: None)
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "method": "GET",
             "path": "/audio/api/events/live", "root_path": "", "query_string": b"", "headers": [], "http_version": "1.1"}
    task = asyncio.create_task(response(scope, receive, send))
    assert (await asyncio.wait_for(sent.get(), 2))["type"] == "http.response.start"
    assert (await asyncio.wait_for(sent.get(), 2))["body"] == b"data: first\n\n"
    assert not blocked.is_set()
    await asyncio.wait_for(module.set_enabled(False), 2)
    assert module.app is None
    assert task.cancelled()
    assert not module.requests
