# Hermes verification

Verified on Windows with isolated synthetic histories and offline provider mode. Original histories were not opened by the test servers.

- Product suite: 8 passed, including independent OFF defaults, saved state, retained external data locations, native APIs, streaming lifecycle and MCP result contracts.
- Shutdown: OFF intent persists before a deliberately blocked shutdown; the dashboard remains responsive.
- Actual stdio MCP: discovery of 114 tools, disabled call rejection, products enable/call/disable and rejection after disable all passed. Discovery does not launch the server.
- Native tool parity: all 57 Tantalus and 55 Phileas tools remain available. Seven colliding names receive products_/shipments_ prefixes and dispatch to their original native names.
- Incorporated regression suites: Tantalus 58 and Phileas 57 passed. Native lane workers finish before their databases close.
- Both native UI builds completed; products and shipments/travel pages opened in the browser. The duplicate Faustus launcher in products was corrected and a single common control was verified.
- Desktop and mobile controls use the canonical family theme, local fonts, a family-style Hermes icon and the common Faustus control. The independent finish review records its precise scope separately.

Live purchases, external mail ingestion, carrier requests, notifications and browser automation were not triggered in these checks. Existing provider tests and static tool parity preserve those capabilities; these checks do not claim a fresh live validation of every provider or account.

Source commits and native tool inventory are recorded in `provenance/`. Data adoption only writes the central module-to-folder mapping, with every module OFF. Private preservation receipts are kept outside the public repository.
