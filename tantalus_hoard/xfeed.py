"""Posts on X (accounts and lists) as an information source, and the fast lane that reads them.

People who hunt stock post it on X minutes before any aggregator shows it ("han puesto stock de las latas en Carrefour",
"UPC disponible por invitación en Amazon"). An information watcher can list X sources: ``{"kind": "x", "value": "@cuenta"}``
or a list (``https://x.com/i/lists/<id>``). They are read here, every ``x.interval_s`` seconds (120 by default) on the
``alerts`` lane, never behind a news sweep.

* **Reading**: X shows nothing without a session, so the account page is opened in Hermes's own browser profile (headless)
  and the timeline JSON the page loads (``UserTweets`` / ``ListLatestTweetsTimeline``) is parsed. The person logs in once
  in a window of that profile (``x_login``): on a Spark the window opens on the Spark's remote desktop (Prometheus), so it
  is seen and used from any browser. The password is typed by the person and never stored by Hermes; only the presence of
  the session cookie is checked, never its value.
* **Tips**: with ``info.x_tipsters`` on, a post is a tip when it points at a shop (a link that is not X or a social site)
  and talks about stock, a price or a shop, or when it names a shop and stock words without a link. A tip skips the
  watcher's term filters (the people who post know what they post), is ``confirmed`` and, with a shop link, ``high``.
  Quoted posts count: "acaban de restockear todo esto otra vez" quoting a post with the links is a tip.
* The first read of a source is a baseline (recorded, quiet). Posts older than ``x.max_age_min`` (120) never alert, so a
  pinned post or a long gap does not wake anyone.

Post texts are third-party data: they only become alert text and, at most, model input inside ``<page>`` tags.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlsplit

from .discovery import fold

log = logging.getLogger("tantalus.xfeed")

X_HOSTS = ("x.com", "twitter.com", "t.co", "pic.x.com", "pic.twitter.com", "mobile.twitter.com")
SOCIAL_HOSTS = X_HOSTS + ("instagram.com", "youtube.com", "youtu.be", "tiktok.com", "facebook.com", "fb.watch", "discord.gg",
                          "discord.com", "t.me", "telegram.me", "twitch.tv", "reddit.com", "threads.net", "bsky.app", "linktr.ee")
MATCH = {"user": "/UserTweets", "list": "/ListLatestTweetsTimeline"}
DEFAULT_INTERVAL_S = 120
DEFAULT_MAX_AGE_MIN = 120
READ_TIMEOUT_S = 30.0

_HANDLE = re.compile(r"^@?([A-Za-z0-9_]{1,15})$")
_LIST = re.compile(r"(?:x|twitter)\.com/i/lists/(\d+)", re.I)
_PROFILE = re.compile(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})(?:[/?#]|$)", re.I)
_RESERVED = {"home", "i", "explore", "search", "notifications", "messages", "settings", "login", "intent", "share", "hashtag"}

STOCK_WORDS = ("stock", "restock", "reposic", "repuest", "reponen", "repone", "han puesto", "ha salido", "han sacado", "sacando",
               "disponible", "invitaci", "preventa", "pre-venta", "reserva", "ya se puede", "ya se pueden", "a la venta", "en venta",
               "corred", "comprad", "volando", "in stock", "available", "preorder", "pre-order", "unidades")
SHOP_NAMES = ("amazon", "carrefour", "eci", "corte ingles", "elcorteingles", "game", "fnac", "alcampo", "toys r us", "toysrus",
              "toy planet", "toyplanet", "drim", "hipercor", "costco", "lidl", "aldi", "mediamarkt", "media markt", "juguetilandia",
              "pokemon center", "xtralife", "worten", "eroski", "primark")
_SHOP_ALIASES = {"amzn": "amazon", "link": "amazon", "a": "amazon", "elcorteingles": "corte ingles"}
_PRICE = re.compile(r"\d+(?:[.,]\d{1,2})?\s?(?:€|eur\b|euros\b)|€\s?\d+", re.I)


# ----------------------------------------------------------------------------- sources
def parse_source(value: str) -> tuple[str, str]:
    """``("user", handle)``, ``("list", id)`` or ``("", "")`` for something that is not an X account or list."""
    v = (value or "").strip()
    m = _LIST.search(v)
    if m:
        return "list", m.group(1)
    m = _HANDLE.match(v)
    if m:
        return "user", m.group(1)
    m = _PROFILE.search(v)
    if m and m.group(1).lower() not in _RESERVED:
        return "user", m.group(1)
    return "", ""


def source_url(value: str) -> str:
    kind, ident = parse_source(value)
    if kind == "list":
        return f"https://x.com/i/lists/{ident}"
    return f"https://x.com/{ident}" if kind == "user" else ""


def label_of(value: str) -> str:
    kind, ident = parse_source(value)
    return f"@{ident}" if kind == "user" else (f"lista {ident}" if kind == "list" else value)


# ----------------------------------------------------------------------------- timeline JSON
def _host(url: str) -> str:
    h = (urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def _is_social(url: str) -> bool:
    h = _host(url)
    return not h or any(h == s or h.endswith("." + s) for s in SOCIAL_HOSTS)


def _ts(created_at: str) -> Optional[float]:
    try:
        return datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y").timestamp()
    except (TypeError, ValueError):
        return None


def _unwrap(result: Any) -> Optional[dict[str, Any]]:
    if not isinstance(result, dict):
        return None
    if result.get("__typename") == "TweetWithVisibilityResults" or ("tweet" in result and "legacy" not in result):
        result = result.get("tweet")
    return result if isinstance(result, dict) and isinstance(result.get("legacy"), dict) else None


def _screen_name(tweet: dict[str, Any]) -> str:
    user = (((tweet.get("core") or {}).get("user_results") or {}).get("result") or {})
    return str((user.get("core") or {}).get("screen_name") or (user.get("legacy") or {}).get("screen_name") or "")


def _text(tweet: dict[str, Any]) -> str:
    note = ((((tweet.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {}).get("text"))
    text = note or (tweet.get("legacy") or {}).get("full_text") or ""
    return re.sub(r"\s*https://t\.co/\w+\s*$", "", str(text)).strip()


def _urls(tweet: dict[str, Any]) -> list[str]:
    legacy = tweet.get("legacy") or {}
    found = [u.get("expanded_url") or u.get("url") for u in (legacy.get("entities") or {}).get("urls") or []]
    note = (((tweet.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {})
    found += [u.get("expanded_url") for u in ((note.get("entity_set") or {}).get("urls") or [])]
    card = ((tweet.get("card") or {}).get("legacy") or {})
    for b in card.get("binding_values") or []:
        if b.get("key") in ("card_url", "website_url") and isinstance(b.get("value"), dict):
            found.append(b["value"].get("string_value"))
    out: list[str] = []
    for u in found:
        if u and u not in out and not _host(u).endswith("t.co"):
            out.append(str(u))
    return out


def _post(tweet: dict[str, Any]) -> dict[str, Any]:
    legacy = tweet["legacy"]
    pid = str(tweet.get("rest_id") or legacy.get("id_str") or "")
    author = _screen_name(tweet)
    post = {"id": pid, "author": author, "text": _text(tweet), "urls": _urls(tweet), "created_ts": _ts(legacy.get("created_at", "")),
            "reply": bool(legacy.get("in_reply_to_status_id_str")), "url": f"https://x.com/{author or 'i'}/status/{pid}",
            "quoted": None, "retweet_by": ""}
    quoted = _unwrap(((tweet.get("quoted_status_result") or {}).get("result")))
    if quoted:
        q = _post(quoted)
        post["quoted"] = {"author": q["author"], "text": q["text"], "urls": q["urls"], "url": q["url"]}
    return post


def parse_timeline(data: Any) -> list[dict[str, Any]]:
    """Every post a timeline answer holds (newest first, pinned and conversation entries included), retweets unwrapped
    to the original post with ``retweet_by`` set. Unknown shapes give an empty list, never an exception."""
    posts: dict[str, dict[str, Any]] = {}

    def add(result: Any) -> None:
        tweet = _unwrap(result)
        if not tweet:
            return
        retweeted = _unwrap(((tweet.get("legacy") or {}).get("retweeted_status_result") or {}).get("result"))
        try:
            if retweeted:
                post = _post(retweeted)
                post["retweet_by"] = _screen_name(tweet)
                post["created_ts"] = _ts(tweet["legacy"].get("created_at", "")) or post["created_ts"]
            else:
                post = _post(tweet)
        except (KeyError, TypeError, AttributeError):
            return
        if post["id"] and post["id"] not in posts:
            posts[post["id"]] = post

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 40:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "tweet_results" and isinstance(value, dict):
                    add(value.get("result"))
                elif key not in ("quoted_status_result", "retweeted_status_result"):
                    walk(value, depth + 1)
        elif isinstance(node, list):
            for value in node:
                walk(value, depth + 1)

    walk(data)
    return sorted(posts.values(), key=lambda p: -(p["created_ts"] or 0))


# ----------------------------------------------------------------------------- tips
def _shop_of(url: str) -> str:
    parts = _host(url).split(".")
    if len(parts) < 2:
        return ""
    name = parts[-1] if parts[-1] == "amazon" else parts[-2]
    return _SHOP_ALIASES.get(name, name)


def shop_links(post: dict[str, Any]) -> list[str]:
    urls = list(post.get("urls") or [])
    if post.get("quoted"):
        urls += [u for u in post["quoted"].get("urls") or [] if u not in urls]
    return [u for u in urls if not _is_social(u)]


def full_text(post: dict[str, Any]) -> str:
    parts = [post.get("text") or ""]
    if post.get("quoted"):
        parts.append(post["quoted"].get("text") or "")
    return "\n".join(p for p in parts if p)


def tip_signal(post: dict[str, Any]) -> dict[str, Any]:
    """``{tip, score, reasons, links, shops, price}`` for one post read from a stock-hunting account."""
    text = full_text(post)
    folded = " " + fold(text) + " "
    links = shop_links(post)
    stock = sorted({w for w in STOCK_WORDS if re.search(r"(?<![a-z0-9])" + re.escape(w), folded)})
    shops = sorted({s for s in SHOP_NAMES if re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", folded)})
    shops += sorted({_shop_of(u) for u in links} - set(shops) - {""})
    price = _PRICE.search(text)
    reasons: list[str] = []
    if links:
        reasons.append("shop link: " + ", ".join(_host(u) for u in links[:2]))
    if stock:
        reasons.append("stock words: " + ", ".join(stock[:3]))
    if shops:
        reasons.append("shop: " + ", ".join(shops[:3]))
    if price:
        reasons.append("price")
    tip = bool(links and (stock or shops or price)) or bool(stock and shops and not post.get("reply"))
    score = 85.0 if tip and links else 70.0 if tip else 45.0 if stock or (links and not tip) else 10.0
    return {"tip": tip, "score": score, "reasons": reasons, "links": links, "shops": shops,
            "price": price.group(0) if price else ""}


def parse_price(text: str) -> Optional[float]:
    m = _PRICE.search(text or "")
    if not m:
        return None
    digits = re.sub(r"[^\d,.]", "", m.group(0)).replace(",", ".")
    try:
        return float(digits.rstrip("."))
    except ValueError:
        return None


# ----------------------------------------------------------------------------- display for a login window
def find_display(preferred: str = ":5") -> str:
    """The X display a window can open on: ``$DISPLAY``, else the remote desktop of the Spark (Prometheus uses ``:5``),
    else any running display. "" when there is none (or on Windows / macOS, where no display is needed: ``"native"``)."""
    if sys.platform.startswith(("win", "darwin")):
        return "native"
    if os.environ.get("DISPLAY"):
        return os.environ["DISPLAY"]
    sockets = Path("/tmp/.X11-unix")
    wanted = (preferred or ":5").lstrip(":")
    if (sockets / f"X{wanted}").exists():
        return f":{wanted}"
    try:
        found = sorted(p.name[1:] for p in sockets.glob("X*") if p.name[1:].isdigit())
    except OSError:
        found = []
    return f":{found[0]}" if found else ""


# ----------------------------------------------------------------------------- the fast lane
class XTips:
    """Extra scheduler job ``x_tips``: reads every X source of the enabled information watchers."""

    def __init__(self, store: Any, engine: Any, fetcher: Any, get: Callable[[str, Any], Any], set_: Callable[[str, str], None], *,
                 clock: Callable[[], float] = time.time):
        self.store, self.engine, self.fetcher = store, engine, fetcher
        self.get, self.set = get, set_
        self.clock = clock
        self._lock = threading.Lock()
        self.last_summary: dict[str, Any] = {}

    # -- settings
    def interval_s(self) -> float:
        try:
            return max(60.0, float(self.get("x.interval_s", str(DEFAULT_INTERVAL_S)) or DEFAULT_INTERVAL_S))
        except (TypeError, ValueError):
            return float(DEFAULT_INTERVAL_S)

    def watchers(self) -> list[dict[str, Any]]:
        """Enabled information watchers that list at least one X source."""
        return [w for w in self.store.watchers(enabled=True) if w.get("mode") == "information"
                and any(isinstance(s, dict) and s.get("kind") == "x" for s in ((w.get("config") or {}).get("sources") or []))]

    def sources(self, *, sync: bool = False) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        out = []
        for w in self.watchers():
            rows = (self.store.sync_info_sources(w["id"], (w.get("config") or {}).get("sources") or []) if sync
                    else self.store.info_sources(w["id"]))
            out += [(w, r) for r in rows if r.get("kind") == "x"]
        return out

    def due(self, now: float) -> bool:
        if self.get("x.paused", "0") == "1":
            return False
        if now < float(self.get("x.next_run_ts", "0") or 0):
            return False
        return bool(self.watchers())

    def run_job(self, _ref: str = "all") -> dict[str, Any]:
        return self.run()

    def run(self) -> dict[str, Any]:
        with self._lock:
            now = self.clock()
            stats: dict[str, Any] = {"sources": 0, "posts": 0, "new": 0, "tips": 0, "events": 0, "errors": []}
            sessions: set[str] = set()
            for watcher, row in self.sources(sync=True):
                stats["sources"] += 1
                try:
                    res = self.engine.process_info_source(watcher, row)
                except Exception as exc:  # noqa: BLE001 - one source never stops the others
                    log.warning("x source %s failed: %s", row.get("value"), exc)
                    stats["errors"].append(f"{row.get('value')}: {type(exc).__name__}: {exc}"[:200])
                    continue
                for k in ("posts", "new", "events"):
                    stats[k] += int(res.get(k) or 0)
                stats["tips"] += int(res.get("material") or 0)
                if res.get("x_session"):
                    sessions.add(str(res["x_session"]))
                if res.get("error"):
                    stats["errors"].append(f"{row.get('value')}: {res['error']}"[:200])
            end = self.clock()
            session = "ok" if "ok" in sessions else ("login" if "login" in sessions else "")
            if session:
                self.set("x.session", session)
                self.set("x.session_ts", str(end))
            stats["session"] = session or (self.get("x.session", "") or "unknown")
            self.set("x.last_run_ts", str(end))
            self.set("x.next_run_ts", str(now + self.interval_s()))
            self.last_summary = {**stats, "seconds": round(end - now, 1)}
            return self.last_summary

    def status(self) -> dict[str, Any]:
        srcs = [{"watcher_id": w["id"], "watcher": w["name"], "source": label_of(r["value"]), "value": r["value"],
                 "last_check_ts": r.get("last_check_ts"), "last_error": r.get("last_error") or ""} for w, r in self.sources()]
        return {"paused": self.get("x.paused", "0") == "1", "interval_s": self.interval_s(),
                "last_run_ts": float(self.get("x.last_run_ts", "0") or 0) or None,
                "next_run_ts": float(self.get("x.next_run_ts", "0") or 0) or None,
                "session": self.get("x.session", "") or "unknown",
                "session_checked_ts": float(self.get("x.session_ts", "0") or 0) or None,
                "sources": srcs, "last": self.last_summary}


def post_hash(post: dict[str, Any]) -> str:
    return hashlib.sha256(f"x:{post['id']}".encode()).hexdigest()[:32]


__all__ = ["XTips", "parse_source", "source_url", "label_of", "parse_timeline", "tip_signal", "shop_links", "full_text",
           "parse_price", "find_display", "post_hash", "MATCH", "DEFAULT_MAX_AGE_MIN"]
