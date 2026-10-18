# Native assistant identities and conversation spaces

The shared launcher may fetch `/api/copilot/info` and `/api/copilot/proxy` at the root. When Referer belongs to this same origin and points inside an existing native module path, these requests dispatch directly into that module. Explicit `/<module>/api/copilot/*` routes also dispatch natively without redirecting to the central shell. Root, missing-module, foreign or malformed Referer requests retain the central assistant. Shared launcher/panel assets can still use the central transport.

Each original engine retains its `app_id`, `tool_server_id`, mapped data folder’s saved `copilot-space-id`, and frontend context. A disabled module returns409 before opening its engine, token or conversation history. No assistant query enables a module. No shared SDK, launcher or compiled client code changes are required.

Hermes origins: products→tantalus and shipments→phileas. Their conversation spaces and tool-server identities remain independent.

Verification: synthetic native ASGI apps use the real copilot transport with httpx.MockTransport, exercise every original identity, persisted space, root/prefixed info/proxy, context injection and OFF file/engine invariance. Tests do not start recorders, audio engines, hardware backends, production services or real model calls. Existing stream/shutdown/MCP tests cover the surrounding module lifetime. Talos additionally exercises its disk adapter with a synthetic engine and checks audio construction order with a synthetic factory.
