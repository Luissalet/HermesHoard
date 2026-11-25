"""What this install says is its own real hub and real data, for the mail helper's isolation rule (``fam_mail.isolation``).

The helper reads the person's real mailbox, so it only runs in the real install. Hermes keeps one data folder per module below
``<repo>/data``, or wherever ``data/modules.json`` says (adopted data stays where it was). On a Spark the hub is not at
``127.0.0.1:8810``: the install says which hub it is in ``HERMES_REAL_HUB_URL`` (one URL, or several separated by commas).
A test sets neither: its data lives in a folder of its own, with a ``modules.json`` of its own.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def real_hubs() -> list[str]:
    return [url.strip() for url in os.environ.get("HERMES_REAL_HUB_URL", "").split(",") if url.strip()]


def real_data() -> list[Path]:
    folders = [REPO_ROOT / "data"]
    try:
        saved = json.loads((REPO_ROOT / "data" / "modules.json").read_text(encoding="utf-8-sig")).get("data_paths") or {}
        folders += [Path(text) for text in map(str, saved.values()) if text and Path(text).is_absolute()]
    except (OSError, ValueError, AttributeError):
        pass
    return folders
