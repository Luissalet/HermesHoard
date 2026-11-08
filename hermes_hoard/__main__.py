import argparse
import json
import os
import sys
from pathlib import Path

import uvicorn
from .app import create_app

# Written by the Hoard Hub while Hermes runs on a Spark (so the PC can be switched off): a second Hermes here would watch
# the same products from a stale copy of the data and send every alert twice.
MARKER = Path(__file__).resolve().parent.parent / "data" / "placement-elsewhere.json"


def placed_elsewhere():
    try:
        where = json.loads(MARKER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return where if isinstance(where, dict) and where.get("location") not in (None, "", "pc") else None


def main():
    parser = argparse.ArgumentParser(description="Hermes's Hoard")
    parser.add_argument("--port", type=int, default=int(os.environ.get("HERMES_PORT", "5221")))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    where = placed_elsewhere()
    if where:
        print(f"Hermes is running on {where.get('node') or 'a Spark'}; bring it back from the Hoard Hub (Run on: PC) first.",
              file=sys.stderr)
        raise SystemExit(3)
    uvicorn.run(create_app(port=args.port), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
