# Native assistant identities and conversation spaces

The shared launcher may fetch `/api/copilot/info` and `/api/copilot/proxy` at the root. When Referer belongs to this same origin and points inside an existing native module path, these requests dispatch directly into that module. Explicit `/<module>/api/copilot/*` routes also dispatch natively without redirecting to the central shell. Root, missing-module, foreign or malformed Referer requests retain the central assistant. Shared launcher/panel assets can still use the central transport.

Each original engine retains its `app_id`, `tool_server_id`, mapped data folder’s saved `copilot-space-id`, and frontend context. A disabled module returns409 before opening its engine, token or conversation history. No assistant query enables a module. No shared SDK, launcher or compiled client code changes are required.

Hermes origins: products→tantalus and shipments→phileas. Their conversation spaces and tool-server identities remain independent.

Verification: synthetic native ASGI apps use the real copilot transport with httpx.MockTransport, exercise every original identity, persisted space, root/prefixed info/proxy, context injection and OFF file/engine invariance. Tests do not start recorders, audio engines, hardware backends, production services or real model calls. Existing stream/shutdown/MCP tests cover the surrounding module lifetime. Talos additionally exercises its disk adapter with a synthetic engine and checks audio construction order with a synthetic factory.


## Outgoing mail identification

Hermes notification mail is identified in the canonical Hoard Link `mail_helper.py` and `notify_channels.send_smtp`, with the same files synchronized into both native modules and the family vendors. The helper remains standalone and standard-library-only. Products supplies `products.<event type>`; Shipments and Trips supply `shipments.<event type>` or `trips.<event type>`. Shared Hub notices default to `notification`. Every message gets one `[Hermes]` subject prefix plus `X-Hermes: 1` and `X-Hermes-Kind`.

After SMTP succeeds, Gmail IMAP locates the exact Message-ID in the mailbox advertised with the special-use `\All` flag (with All Mail/Todos fallbacks), creates Hermes when absent, and adds it with `UID STORE +X-GM-LABELS`. Three searches accommodate delayed appearance. It adds no Seen flag and replaces no other label. Failure remains best-effort and does not change SMTP success or trigger a second send. Other mail-reading paths remain read-only. No historical messages are relabelled. Gmail searches: `label:hermes` and `subject:[Hermes]`.

Regression coverage lives in Hoard Link `tests/commons/test_hermes_mail.py` and both native notification suites. A real self-addressed Gmail SMTP/IMAP test on 2026-11-10 verified the prefix, both headers, Hermes label, retained Inbox/Sent labels and no Seen flag.
