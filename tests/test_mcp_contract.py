import json
from types import SimpleNamespace

import httpx
import pytest
import mcp_server as bridge


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_declared_long_timeout_structured_results_and_no_replay(tmp_path, monkeypatch, fail):
    (tmp_path / "mcp-token").write_text("synthetic-token")
    monkeypatch.setenv(bridge.PRODUCT.upper() + "_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(bridge, "catalog", lambda: [{"name": "long_write", "inputSchema": {"x-timeout-s": 1800}, "annotations": {"readOnlyHint": False}}])
    monkeypatch.setattr(bridge, "app", SimpleNamespace(request_context=SimpleNamespace(meta=None)))
    original_client = httpx.AsyncClient
    seen = []

    def respond(request):
        seen.append(json.loads(request.content))
        if fail:
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return httpx.Response(200, json={"text": "áéí — preserved", "count": 7})

    def client(**kwargs):
        assert kwargs["timeout"].read == 1800
        return original_client(**kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(httpx, "AsyncClient", client)
    result = await bridge.call_tool("long_write", {})
    assert len(seen) == 1
    assert result.isError is fail
    assert json.loads(result.content[0].text) == result.structuredContent
    if fail:
        assert result.structuredContent["outcome_unknown"] is True
    else:
        assert result.structuredContent["count"] == 7
