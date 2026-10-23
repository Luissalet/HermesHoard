# Hermes's Hoard

In **Products → Second-hand**, **Mark as gone** sets a listing's local `gone` status. It leaves the active list and remains under the watcher's **Gone** filter; **Save** returns it to Saved. This uses existing `listing_set` API/MCP without checking or changing the listing on its platform or pausing the watcher. Only status changes: identity, zero/unknown prices, stored dates, content and price history remain intact. No removal date is inferred.

In **Trips → Plan**, select some bookings and choose **Split off** to review the selection and optionally name the new trip. Leaving the name blank retains native automatic naming. The receipt shows returned IDs, dates and segment counts for the original and new trips, with an explicit **Open created trip** link and no automatic navigation. Bookings retain their identity and associated mail. People and recorded expenses, including expenses for moved bookings, remain in the original trip. Cancel writes nothing; errors retain the name and selection. Uses existing API/MCP `trip_update(split_segments, split_title)` without contacting providers or reading mail.

In **Trips → Expenses → People**, **Rename person** changes the selected participant through the existing `trip_people` API/MCP `rename` map, keyed by the visible person ID. The trip/person identities are shown before saving. Equal names remain separate people; the existing person ID, “me” mark, position, expenses, payers and splits stay intact. Cancel or a failed save keeps the name draft, and a later edit made while saving remains pending after refresh. Only saving writes the native local name; no external account profile changes.

**Shipments → Look up a number** runs a one-off carrier lookup without adding a shipment or scheduling tracking. The native `track_number` API/MCP capability returns status, source, carrier estimate and up to 40 events, distinguishing not found, unavailable source and failure. Only **Look up** triggers a request. Configured sources may use external services and their quota; no mail is read or shipment saved. Editing either field removes the previous result; closing or failure keeps the draft.

Availability watcher details offer **Mark as bought**, with an optional local purchase reference. This manual record stops scheduled checks while preserving products and history, and shows the recorded date/reference without verifying an external purchase. The existing **Enabled** switch resumes watching and clears the purchase mark. The UI uses the existing `watcher_mark_bought` and `watcher_update` API/MCP operations; opening or cancelling the form does not change the watcher, and cancelling or a failed save keeps the reference draft.

<img src="app-icon.png" width="96" alt="Hermes icon">

Product watching, shopping alerts, shipment tracking and travel in one local process. Incorporates Tantalus and Phileas, including their complete native tools, interfaces and stored histories.

Shipment details offer **Merge duplicate record** for two local records of the same parcel. The open record keeps its identity; choose the other record manually and review both identities and the seven fields that can fill empty values. Existing values win. The native `shipment_merge` API/MCP operation moves linked mail, non-duplicate events and recorded notifications, removes the selected record and quietly recomputes the local delivery estimate. Notes, names and other fields are not combined; the normal confirmation describes the removal and absence of undo. Opening/cancelling only reads, and search or save errors preserve the selection and existing unsaved shipment edits. No carrier request, mail scan or external order change occurs.

[Castellano](README.es.md) · [Complete tool inventory](provenance/CAPABILITIES.md) · [Source provenance](provenance/sources.json)

## Independent modules

Both modules are **OFF on first start**. Opening Hermes or discovering its MCP catalogue starts no scheduler, browser, mail scan or model. Enable only the module you want; choices persist. Disabling a module stops its scheduler and waits for its current work before closing the database. The dashboard remains available during shutdown.

| Module | Preserved functions |
|---|---|
| Products and deals | Stock, prices, pre-orders, releases, discovery, second-hand search and scoring, web/news watches, mail deals, radar, browser fetch lanes, notifications, schedules and history |
| Shipments and travel | Mail parsing/import, shipment identifiers, carriers, tracking and ETA, delivery dashboard, incidents, notifications, trips and segments, check-in/departure reminders, travel mail, budgets and currency/time helpers |

Native interfaces are under `/products/` and `/shipments/`. They share the Hoard theme, Hermes icon and Faustus copilot. Individual native settings remain available within each module.

## Run

Python 3.11+. Windows notifications and desktop browser integrations require Windows.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m hermes_hoard --no-browser
```

Open `http://127.0.0.1:5221`. `Start.cmd` creates the environment when absent. No window opens automatically. Hoard Hub discovers `faustus-plugin.json` and launches Hermes explicitly. Browser-based fetching retains the native installed-browser requirements; install the Playwright browser with `python -m playwright install chromium` if that backend needs it.

## Existing data

With both modules OFF:

```powershell
.venv\Scripts\python.exe scripts\adopt_data.py --parent "C:\path\to\Hoards"
```

Only the central map `data/modules.json` is written. Original databases, mail watermarks, cached pages, browser profiles, evidence, settings and tokens stay in their original Tantalus/Phileas folders. Their `.env` secrets are read in place when a module starts; they are not copied into this repository. Keep the old data folders. Without adoption, fresh data goes to `data/products` and `data/shipments`.

`HERMES_DATA_DIR`, `HERMES_PORT` and `--port` override the central data folder and port. Original module environment variables still configure native behaviour. `HERMES_URL` and `HERMES_TOKEN_FILE` configure the stdio bridge.

## API and MCP

`GET /api/modules`, `PUT /api/modules/{id}` with `{"enabled":true|false}`, and `POST /api/modules/stop-all` control the modules. The combined API exposes **115 tools**: 113 native functions plus `hermes_modules` and `hermes_set_module`. Calls to OFF modules return `module_disabled` without starting them.

**Delivery calendar:** Shipments has a date-range preview and ICS download for stored estimated delivery dates and recorded pickup deadlines. Deliveries are marked tentative, deadlines confirmed, and all events are all-day and transparent. Undated parcels and dates outside the selected period are counted; completed, archived and history-only parcels are excluded. The downloaded file is a snapshot, not a live subscription. `shipments_ics` exposes the same dates, complete ICS and download URL through native/combined MCP and API; `GET /shipments/api/shipments/ics?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` downloads it. Defaults: today through 90 days ahead. Existing storage lists at most 2,000 active parcels; reaching that boundary is shown. No carrier lookup, mail scan, model request or shipment mutation occurs.

Seven names occurred in both source catalogues: `settings_set`, `secret_set`, `scheduler_status`, `notify_status`, `notify_test`, `telegram_find_chat_id` and `runs_list`. In the combined catalogue they use `products_` or `shipments_` prefixes; their original schemas and behaviour remain intact. Each module's own API keeps its native names. The [inventory](provenance/CAPABILITIES.md) gives every mapping.

`GET /api/agent/tools` lists tools; `POST /api/agent/call` requires the central bearer token in `data/mcp-token`. Run `.venv\Scripts\python.exe mcp_server.py` for stdio MCP. Discovery works even when the server is stopped and never launches it.

Retired identities can remain in Hoard Hub as non-launchable compatibility entries pointing at the new module routes. This keeps family tokens, mail interests, references and existing cross-Hoard calls intact without running either original server.

## Development

Install `pytest pytest-asyncio`, then run `python -m pytest tests -q`. `legacy_tests/` retains the source regression suites. `scripts/qa_server.py` starts synthetic, offline data; `scripts/verify_mcp.py --data-dir <QA-data>` exercises the actual stdio transport. `scripts/build_catalog.py` regenerates the tool catalogue without opening histories or starting schedulers.

The two native UI projects live under `ui/`; use `npm ci` and `npm run build` in each. Built assets ship with this repository. Text-model requests use the family's configured global Sparks service. Models never load while modules are OFF. Source commits and licenses are retained under `provenance/`; bundled Cinzel and Source Sans 3 fonts carry their SIL Open Font Licenses.


## Owned data and compatibility

Native module data can be relocated into `data/native/<module>/data`, with per-module configuration beside it. Writer fiction uses the owning desktop profile `writers-hoard/fiction/data`. Move complete data trees, including SQLite WAL/SHM, media, downloaded models and browser sessions; update saved absolute paths before enabling a module. The compatibility manifests in `compatibility/<id>/faustus-plugin.json` preserve native IDs, tool schemas and tokens without a retired checkout. Add each merged application's `compatibility` directory to Hub roots before the general repository root. Discovery and compatibility bridges never start an application. All modules remain OFF during relocation.

Legacy in-place adoption scripts are optional import helpers; keeping the old repository is unnecessary once relocation and route updates have been verified.
