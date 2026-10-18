"""Rebuild the static MCP catalogue without creating services or reading user data."""
import asyncio
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def main():
    product = "talos" if (ROOT / "talos_hoard").exists() else "hermes"
    packages = [("argus", "screen"), ("echo", "clipboard"), ("cassandra_hoard", "services"),
                ("funes_hoard.audio_memory", "audio")] if product == "talos" else [
                ("tantalus_hoard", "products"), ("phileas_hoard", "shipments")]
    tools = []
    for package, module in packages:
        catalog = importlib.import_module(package + ".agent_tools").tool_catalog()
        tools.extend({**t, "module": module} for t in catalog)
    if product == "talos":
        from funes_hoard.mcp_server import mcp
        from funes_hoard.api import AGENT_TOOLS
        for tool in await mcp.list_tools():
            if tool.name in AGENT_TOOLS:
                tools.append({**tool.model_dump(exclude_none=True, mode="json"), "module": "activity"})
        from diskhoard.agent import CATALOG
        tools.extend({**t, "module": "disk"} for t in CATALOG)
    names = [t["name"] for t in tools]
    if product == "hermes":
        from collections import Counter
        duplicates = {n for n, count in Counter(names).items() if count > 1}
        for tool in tools:
            if tool["name"] in duplicates:
                tool["native_name"] = tool["name"]
                tool["name"] = tool["module"] + "_" + tool["name"]
        names = [t["name"] for t in tools]
    assert len(names) == len(set(names)), "Duplicate tool names"
    target = ROOT / (product + "_hoard") / "catalog.json"
    target.write_text(json.dumps(tools, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(tools)} tools: {target}")


if __name__ == "__main__":
    asyncio.run(main())
