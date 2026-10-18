"""Explicit synthetic QA server; never opens a browser or loads real histories."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PRODUCT = "talos" if (ROOT / "talos_hoard").exists() else "hermes"
data_dir = Path(tempfile.mkdtemp(prefix=PRODUCT + "-browser-qa-"))
values = {"ECHO_BACKEND": "fake", "ARGUS_CAPTURE": "fake", "ARGUS_WINDOW": "fake", "ARGUS_VISUAL": "none",
          "SCRIBE_AUDIO": "fake", "SCRIBE_TRANSCRIBER": "fake", "CASSANDRA_AUTOSTART": "0", "CASSANDRA_GPU": "0",
          "CASSANDRA_ROOTS": str(data_dir), "TANTALUS_OFFLINE": "1", "PHILEAS_OFFLINE": "1",
          "TANTALUS_BROWSER": "0", "PHILEAS_BROWSER": "0", "HOARD_HUB_URL": "http://127.0.0.1:1",
          "HOARD_FAUSTUS_URL": "http://127.0.0.1:1"}
values["HOARD_HUB_AUTOSTART"] = "0"
os.environ.update(values)
if PRODUCT == "talos":
    import time
    from funes_hoard import api
    from funes_hoard.collectors.fake import ClockFakeProbe
    api._pick_probe = lambda demo: ClockFakeProbe(time.time(), 1, lambda ts: ("Fixture", "fixture.exe", "Synthetic browser QA", 1, 0, False))
    api.windows_recent_dir = lambda: None
from importlib import import_module
import uvicorn
port = 5220 if PRODUCT == "talos" else 5221
app = import_module(PRODUCT + "_hoard.app").create_app(data_dir, port=port)
print(f"Synthetic data only: {data_dir}", flush=True)
uvicorn.run(app, host="127.0.0.1", port=port)
