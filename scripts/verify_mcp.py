"""Exercise the actual stdio bridge against an explicitly started synthetic server."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
PRODUCT = "talos" if (ROOT / "talos_hoard").exists() else "hermes"


async def verify(data_dir):
    env = dict(os.environ, **{PRODUCT.upper() + "_DATA_DIR": str(data_dir)})
    parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server.py")], env=env)
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == (93 if PRODUCT == "talos" else 114)
            status = await session.call_tool(PRODUCT + "_modules", {})
            assert not status.isError
            body = json.loads(status.content[0].text)
            assert not any(m["enabled"] for m in body["modules"])
            module, tool = ("clipboard", "clip_status") if PRODUCT == "talos" else ("products", "products_scheduler_status")
            assert (await session.call_tool(tool, {})).isError
            assert not (await session.call_tool(PRODUCT + "_set_module", {"module": module, "enabled": True})).isError
            result = await session.call_tool(tool, {})
            assert not result.isError, result
            assert not (await session.call_tool(PRODUCT + "_set_module", {"module": module, "enabled": False})).isError
            assert (await session.call_tool(tool, {})).isError
            print(json.dumps({"product": PRODUCT, "transport": "stdio", "tools": len(tools.tools), "native_tool": tool,
                              "discovery": "PASS", "off_on_off": "PASS", "default_all_off": "PASS"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    asyncio.run(verify(parser.parse_args().data_dir))
