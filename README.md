# Hermes's Hoard

All outgoing notification mail, including Products, Shipments, Trips, shop alerts, nightly summaries and Hub/Faustus notices, carries the `[Hermes]` subject prefix, `X-Hermes: 1` and `X-Hermes-Kind`. Gmail accounts also receive the **Hermes** label via IMAP after SMTP delivery; the label is created when missing. Search Gmail with `label:hermes` or `subject:[Hermes]`. Labelling failures do not turn a successful send into a failure. Existing recipients, message bodies and notification rules are retained. This applies to new mail; older messages are not relabelled.

**Products → target → How to fetch → My open window (Brave/Chrome/Edge)** watches a page you already have open in a Chromium browser on this computer, for shops that answer automated browsers with a check. On each check Hermes finds the window whose active tab shows the target address, presses that window's own Reload button through Windows UI Automation, scrolls to the end and back so lazy lists load, and reads the page text; the window is not brought to the front and no keys or clicks are sent. Each product row of a list (name, price, button text such as "Añadir", "Agotado temporalmente" or "Próximamente") is followed on its own: its own restock, sale-open, pre-order and price alerts, and its own "sold out" follow-up, so two products returning one after the other give two alerts. These checks run in their own scheduler lane and keep their interval (5 minutes or more) while other targets work through a backlog. If the window is closed, shows another page or asks for a human check, Hermes sends one high-priority notice (e-mail included) and keeps trying at the same interval; it never answers the check. The fetch tier is `open_window` in `target_add` / `target_update` (API/MCP). Needs Windows and the `uiautomation` package (in `requirements.txt`).

**Products → Basket** puts a watched product in your basket the moment it can be bought. Paste the product page and load the extension in `browser/cart-runner` (Brave / Chrome / Edge → extensions → Load unpacked) in the browser where you are signed in to the shop: it keeps the page open in a pinned tab, reloads it every few seconds, adds one unit when the buy button comes alive and walks the checkout (basket, home delivery, summary) up to the page with the pay button, where it stops; it never pays. Each stage raises a high-priority alert on every channel, with a sound and a desktop notice in the browser: in the basket, pay now, the shop asks for the password, a delivery choice is needed, sold out on the way. If the browser stops reporting for five minutes Hermes says so. The extension only acts in the tab it opened and talks to Hermes with its own key (`config.json` beside the extension or its popup), so Hermes can run on another machine. The buyer's identity document, when a shop asks for it on the pay page, can be saved in the extension (kept in that browser only). A job can also be one of your own lists at the shop (Carrefour favourites): you name the products to take from it, one entry each (every word of the entry must be in the product's name), and a basket limit; one reload reads the whole list, one unit of each wanted product that can be bought goes into the basket within the limit, a second unit is taken out again, marketplace sellers are left out unless asked, and the alert is headed by what went in. Supported shops: El Corte Inglés (product pages), Carrefour (your lists; basket, delivery and payment page). `config.json` may name a local listener (`probe`) that receives an outline of the pages the runner tab visits, to map a new shop. Tools: `cart_jobs`, `cart_job_add`, `cart_job_update`, `cart_job_remove`.

Each open-window reading is checked twice more. **Model check:** the configured model (the Prometheus route by default) reads the same page text and returns every row with its status and the words that prove it; rows it agrees with are marked corroborated, a buyable row only the model saw is held as pending and re-read one minute later (an alert needs two readings in a row), and a disagreement keeps the rule-based reading. **Faustus look:** when Faustus is running, Hermes asks it (in the background, one look per target at a time) to read the same tab through its browser-session extension, scroll it, and open product pages in background tabs when a row is unclear; its verdict is stored and merged on the next check, and a verdict that differs from Hermes brings that next check forward. Faustus never clicks a buy button or answers a check page. Settings: `faustus_eye.enabled` (`1`/`0`) and `faustus_eye.url` (default `http://127.0.0.1:7000`).

Hermes can also run on a DGX Spark (Linux) while the PC is off: the Hoard Hub moves it there and back (**Run on**). Off Windows the open-window targets pause quietly: no reading, no failure and no "needs your help" notice, only the note "En pausa…" on the target, and they are read again within 15 minutes of coming back to the PC. Every other check, the radar, the mailbox deals and the e-mail alerts keep working there (mail goes through the Faustus folder the Hub points it at). While Hermes runs on the Spark, `python -m hermes_hoard` on the PC refuses to start (`data/placement-elsewhere.json`), so no alert is ever sent twice. Shops that only answer an ordinary browser window (Carrefour product pages, and shops behind a bot wall such as Hipergol, HeroFreaks, Collectorage and Alfriki) pause the same way on the Spark; their stock still arrives through the stocktcg radar when the shop is listed there. Toasts are skipped there (no Windows desktop), not counted as failures.

Known shops (`tantalus_hoard/extract/sites.py`) read at their own level: a restock read from a shop's own product page scores 85 (own page + structured state + coherent price) and alerts. A page the person adds on an unknown shop counts as that shop's own page too, unless discovery knows the host as a marketplace, community or aggregator. Fake shops seen in paid ads (`SCAM_HOSTS`: managermodf.shop, xeagdyat.shop) are never a discovery candidate and cannot be added as targets.

A check that fails because this computer's network is down (unresolvable host, connection errors, `net::ERR_*`) is retried at about the target's normal cadence; only a shop's own refusals (robots, check pages, blocks) earn the escalating backoff of up to six hours.

Cadence: the aggregator radar runs every 3 minutes (every 2 when a watched set is out today or tomorrow; `radar.interval_min` / `radar.release_interval_min` change it, 1 minute minimum), re-reading each followed product page every 10 minutes (5 for a fresh release); the mailbox is scanned for deals every 15 minutes (`mail.deals.interval_min`). Both run in their own scheduler lane, so a long discovery or news sweep never delays them.

Buying alerts end when the offer ends. A restock, reservation or price alert leaves **Products → News** as soon as the shop's own page or the aggregator radar sees it sold out, or when no page has confirmed it for hours. History keeps it, marked **Sold out** or **Unconfirmed** with the time. If the alert already went out, a short "sold out" follow-up goes out on the same channels, at most once per alert, within two days of the alert and only when the offer has just ended. Tidying up older alerts sends nothing. The watcher's **Also alert when something already announced sells out** option (`policies.notify_ended_alerts`, on by default) turns the follow-up off. An offer that only lapsed and is listed again the same day restores its alert without raising a new one. The same holds at every level of reading: a revalidation that reads the page sold out ends the alert with its follow-up (it no longer waits for the next ordinary check, which used to end it silently); an open-window row ends with its own follow-up, and a row missing from two readings in a row (taken off the list, or a shop that hides what it does not sell) ends quietly as **Unconfirmed**; a row only the model understood ends like any other. When the product comes back, a new alert goes out.

**Products → Mail → Stock notices** reads the shops' own stock mail from the Faustus mailbox (read-only): "vuelve a estar disponible" / "back in stock", "ya puedes reservar" / reservations open, "ha bajado de precio" / price drop, "se ha agotado" / sold out. A phrase in the subject is enough; a phrase only in the body counts in a personal mail (your wishlist, your alert). The sender must be the shop of a watched product (its own domain or a sending domain it is known to use, such as `mail-game.net` for GAME; more pairs in the tab's settings as `sender=shop`). The mail is matched to the watched product by its link, by the product number in the target's link, or by every significant word of its name, including one row of an open-window list (a Carrefour favourite, say). A fresh match raises the same alert a page check would: `RESTOCK` (`SALE_OPEN` when the product said "Próximamente"), `PREORDER_OPEN`, `PRICE_DROP`, marked as coming from the shop's mail; a sold-out mail ends the live alerts with the usual follow-up. The page of that product is checked at once to confirm or end it; a mail alert no page confirms ends quietly after 12 hours, and a mail older than 12 hours is recorded without an alert. It needs no browser, so it is how open-window and window-only shops keep alerting while Hermes runs on a Spark. The tab lists every notice with how it was matched and what it raised, shows the phrase rules and the watched shops with their senders, assigns an unmatched notice to a product (**Assign**) or ignores it, and reads the mail now. Tools: `stock_notices`, `stock_notices_scan`, `stock_notice_set`; settings `mail.notices.enabled|interval_min|history_days|max_age_hours|live_hours|domains`. Nothing is clicked, fetched, answered or bought; mail links are only read as text.

Amazon invitation blocks returning after stale or contradictory aggregator views no longer raise another reservation alert. The live panel shows one current Amazon reservation per product URL; History retains all events. Radar prefers retailer product photos, cached for a day with up to six refreshes per cycle. Native `radar_run(watcher_id, refresh_urls)` refreshes known product photos only; `retailer_details` applies explicitly verified HTTPS image/format corrections that survive aggregator refreshes. Neither targeted operation checks stock or sends alerts.

**Products → News / History / product events** offer **Mark as seen** for an individual event. Only that event's stored `seen` flag changes; its status, price, history, other unread events and the last global visit stay intact. Seen events remain available in History when **Only unseen** is off. Existing **Mark all seen**, Dismiss and Resend actions remain available. Uses native `events_mark_seen(event_ids:[ID])` API/MCP115 without checking sources or sending notifications; failures keep the current filters and allow retry.

**Trips → Merge with another trip** now identifies both trips by ID, dates,
destination, native booking/expense counts and recorded currencies, including
trips with equal titles. The same existing confirmation performs the native
merge: bookings and expenses move, people/payers/splits follow native name
matching, saved notes join and the other trip is removed. No currency conversion
or undo is added. The returned kept-trip receipt stays open until Close, even
if refreshing fails; trip-page notes drafts remain unsaved and separate. A
confirmed incorporated ID is removed from the page's choices. Existing
`trip_update(merge_from, confirm)` API/MCP115 and engine remain unchanged.

In **Trips → Edit segment**, flight Gate, train Coach and transport Class can be
recorded directly. Coach and Seat have separate inputs. Existing values load
into the editor; clearing a field clears its native stored value. Saves send only
edited fields through existing `segment_add/update` API/MCP operations and retain
the current editor's error/retry and later-draft behavior. These are local notes,
without checking live boarding information or changing the carrier's reservation.
Other booking fields, calendar export and existing trip actions stay available.

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

`GET /api/modules`, `PUT /api/modules/{id}` with `{"enabled":true|false}`, and `POST /api/modules/stop-all` control the modules. The combined API exposes **118 tools**: 116 native functions plus `hermes_modules` and `hermes_set_module`. Calls to OFF modules return `module_disabled` without starting them.

**Shipments → Action required** lists, above everything else, the parcels that will not move until you act: customs to pay (the carrier's text mentions duties, VAT or a pending payment), customs documents, an address to fix, a failed delivery to rearrange, and parcels waiting at a pickup point (urgent two days before the deadline). Each card carries the same chip, the parcel joins **Needs attention**, and a new customs payment, documents request or address problem is notified once even when the carrier only changed its text. `phileas_overview` returns `action_required` first. The arrival estimate knows customs too: a parcel held at customs is expected 2–5 working days after it entered, or 1–4 working days after you pay or send the documents, instead of a carrier date that has already passed. Nothing is paid or answered for you.

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

## Skills for the agents that connect

This app carries procedures from the skill library of the family's workspace for the agents that connect to it: `hoard-daily-digest`, `hoard-what-happened`, `web-to-clean-markdown`, `unattended-brief`. They are named in what an agent reads on connecting, read with `skills_list` and `skill_read`, searched and assigned with `skills_library` and `skills_assign`, and offered as prompts. The person chooses them on the skills page (`/api/agent/skills/page`) or in the hub's Skills tab; the `skills` block of `faustus-plugin.json` holds what the app asks for by default.
