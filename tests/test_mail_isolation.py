"""Hermes's mail: the Faustus helper only runs in the real install, and the real install is never left without it.

Both mail modules (Phileas and Tantalus) build their helper in two places, the mail source and the notifier. Every scenario counts the
calls of a stand-in for ``subprocess.run``: a test hub or test data must keep it at zero, the real install (the PC's, and the Spark's
with the hub it declares) must reach one. Nothing here starts a process, a hub or an app, and no mailbox is read."""

from __future__ import annotations

import importlib
import json
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
REAL_HUB = "http://127.0.0.1:8810"
SPARK_HUB = "http://10.0.0.2:8810"
OK_ANSWER = '{"ok": true, "error": "", "messages": [{"subject": "Pedido", "message_id": "<a@x>", "ts": 1}], "accounts": []}\n'
# package -> (the Hermes module that runs it, the setting that says where Faustus lives)
PACKAGES = {"phileas_hoard": ("shipments", "mail.faustus_dir"), "tantalus_hoard": ("products", "notify.email.faustus_dir")}


class CountingRunner:
    """A ``subprocess.run`` stand-in that only counts."""

    def __init__(self):
        self.calls = 0

    def __call__(self, cmd, **kw):
        self.calls += 1
        return subprocess.CompletedProcess(cmd, 0, OK_ANSWER, "")


class NoGateway:
    def available(self, *a, **k):
        return False


class Gateway:
    """The hub's mail gateway, serving one message."""

    def available(self, *a, **k):
        return True

    def register_interest(self, spec, sphere=None):
        return {"ok": True}

    def messages(self, since_id=0, limit=100, full=True, fields=None):
        row = {"id": 1, "message_id": "<g@x>", "subject": "Pedido", "text": "", "ts": time.time(), "from_address": "a@b.es"}
        return {"ok": True, "messages": [row] if since_id < 1 else [], "last_id": 1}


@pytest.fixture(params=sorted(PACKAGES))
def pkg(request):
    return request.param


@pytest.fixture
def faustus(tmp_path):
    root = tmp_path / "faustus"
    (root / "mcp_servers").mkdir(parents=True)
    (root / "mcp_servers" / "email_server.py").write_text("", encoding="utf-8")
    (root / "venv" / "bin").mkdir(parents=True)
    (root / "venv" / "bin" / "python").write_text("", encoding="utf-8")
    return root


@pytest.fixture
def install(pkg, monkeypatch):
    """Point this package's family client at a hub and a token file, and put the state back afterwards."""
    family = importlib.import_module(f"{pkg}.hoard_link.family")
    fam_mail = importlib.import_module(f"{pkg}.hoard_link.fam_mail")
    saved = dict(family._state)
    for key in ("HOARD_HUB_URL", "HOARD_TOKEN_FILE", "HOARD_HUB_DATA_DIR", "HERMES_REAL_HUB_URL"):
        monkeypatch.delenv(key, raising=False)
    fam_mail.forget_availability()

    def apply(hub, token_file, declared=None):
        if declared:
            monkeypatch.setenv("HERMES_REAL_HUB_URL", declared)
        family.configure(pkg.split("_")[0], None, token_file=token_file, hub=hub)

    yield apply
    family._state.clear()
    family._state.update(saved)
    fam_mail.forget_availability()


def module_token(pkg: str) -> str:
    """Where the real install keeps the module's token: one folder per module below ``<repo>/data`` (``data/modules.json``)."""
    return str(REPO / "data" / "native" / PACKAGES[pkg][0] / "data" / "mcp-token")


def helpers(pkg, faustus, runner, tmp_path, gateway=None):
    """The two helpers this package builds: the one of the mail source and the one of the notifier, made by the real constructors."""
    source = importlib.import_module(f"{pkg}.mail.source")
    notify = importlib.import_module(f"{pkg}.notify")
    setting = PACKAGES[pkg][1]
    get = lambda key, default=None: str(faustus) if key == setting else default  # noqa: E731
    mail = source.MailSource(None, get, process_runner=runner, hub_mail=gateway or NoGateway()) if pkg == "tantalus_hoard" else \
        source.MailSource(None, get, lambda k, v: None, process_runner=runner, hub_mail=gateway or NoGateway())
    config = importlib.import_module(f"{pkg}.config").Config(data_dir=tmp_path / "data")
    notifier = notify.Notifier(config, get, faustus_runner=runner)
    return mail, notifier


# ---------------------------------------------------------------------------------------------------------------------
# the real install keeps its mail
# ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("hub", [REAL_HUB, "http://localhost:8810/", None], ids=["pc", "localhost", "no-hub-configured"])
def test_the_real_install_still_reaches_the_helper(pkg, install, faustus, tmp_path, hub):
    """On the PC, and on a Spark whose unit sets no hub (the default, ``127.0.0.1:8810``), with the module's data folder below ``<repo>/data``."""
    install(hub, module_token(pkg))
    runner = CountingRunner()
    mail, notifier = helpers(pkg, faustus, runner, tmp_path)
    for helper in (mail.helper, notifier.helper):
        assert helper.isolation() == "" and helper.available()
        assert helper.run("status")["ok"] is True
    assert runner.calls == 2


def test_the_data_folder_of_the_product_itself_is_real_too(pkg, install, faustus, tmp_path):
    install(REAL_HUB, str(REPO / "data" / "mcp-token"))
    mail, _ = helpers(pkg, faustus, CountingRunner(), tmp_path)
    assert mail.helper.isolation() == ""


def test_a_spark_install_that_declares_its_hub_keeps_the_helper(pkg, install, faustus, tmp_path):
    install(SPARK_HUB, module_token(pkg), declared=SPARK_HUB + "/")
    runner = CountingRunner()
    mail, notifier = helpers(pkg, faustus, runner, tmp_path)
    assert mail.helper.available() and notifier.helper.available()
    assert mail.router.scan(since_days=30, limit=10)[0]["subject"] == "Pedido"
    assert runner.calls == 1


def test_several_declared_hubs_are_read_one_by_one(pkg, install, faustus, tmp_path):
    install(SPARK_HUB, module_token(pkg), declared="http://other.example.test:9000, " + SPARK_HUB)
    mail, _ = helpers(pkg, faustus, CountingRunner(), tmp_path)
    assert mail.helper.isolation() == ""


# ---------------------------------------------------------------------------------------------------------------------
# a test install does not reach the mailbox
# ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("hub", ["http://127.0.0.1:58778", "http://127.0.0.1:80", SPARK_HUB, "http://hub.example.test:8810"])
def test_a_hub_that_is_not_the_real_one_isolates(pkg, install, faustus, tmp_path, hub):
    install(hub, module_token(pkg))
    runner = CountingRunner()
    mail, notifier = helpers(pkg, faustus, runner, tmp_path)
    for helper in (mail.helper, notifier.helper):
        assert helper.isolation() == "hub" and not helper.available()
        answer = helper.run("status")
        assert answer["ok"] is False and answer["isolated"] == "hub" and "sin pasarela" in answer["error"] and "mail is off" in answer["error"]
    assert runner.calls == 0


def test_declaring_a_hub_does_not_make_the_others_real(pkg, install, faustus, tmp_path):
    for hub in ("http://10.0.0.3:8810", "http://10.0.0.2:58778", "https://10.0.0.2:8810", "http://127.0.0.1:58778"):
        install(hub, module_token(pkg), declared=SPARK_HUB)
        mail, _ = helpers(pkg, faustus, CountingRunner(), tmp_path)
        assert mail.helper.isolation() == "hub", hub


@pytest.mark.parametrize("where", ["tmp", "next-to-data", "elsewhere-in-repo", "no-token"])
def test_data_that_is_not_the_installs_isolates(pkg, install, faustus, tmp_path, where):
    token = {"tmp": str(tmp_path / "data" / "native" / "shipments" / "data" / "mcp-token"),
             "next-to-data": str(REPO / "data-copy" / "native" / "shipments" / "data" / "mcp-token"),   # a sibling whose name starts like it
             "elsewhere-in-repo": str(REPO / "docs" / "mcp-token"),
             "no-token": ""}[where]
    install(REAL_HUB, token)
    runner = CountingRunner()
    mail, notifier = helpers(pkg, faustus, runner, tmp_path)
    for helper in (mail.helper, notifier.helper):
        assert helper.isolation() == "data" and helper.run("scan")["isolated"] == "data"
    assert runner.calls == 0


def test_the_router_reads_nothing_in_a_test_install_and_says_so(pkg, install, faustus, tmp_path):
    install("http://127.0.0.1:58778", str(tmp_path / "data" / "mcp-token"), declared=SPARK_HUB)
    runner = CountingRunner()
    mail, _ = helpers(pkg, faustus, runner, tmp_path)
    for mode in ("auto", "faustus"):
        mail.router.source_getter = lambda mode=mode: mode
        assert mail.router.scan(since_days=30, limit=10) == []
        assert "sin pasarela" in mail.router.last_error and "mail is off" in mail.router.last_error
    assert mail.helper.status()["isolated"] == "hub"
    assert runner.calls == 0


def test_a_gateway_still_serves_a_test_install(pkg, install, faustus, tmp_path):
    install("http://127.0.0.1:58778", str(tmp_path / "data" / "mcp-token"))
    runner = CountingRunner()
    mail, _ = helpers(pkg, faustus, runner, tmp_path, gateway=Gateway())
    assert [m["subject"] for m in mail.router.scan(since_days=30, limit=10)] == ["Pedido"] and mail.router.last_source == "hub"
    assert runner.calls == 0


# ---------------------------------------------------------------------------------------------------------------------
# data adopted from the original apps stays where it was: modules.json of the install says so
# ---------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def adopted(pkg, monkeypatch, tmp_path):
    """An install whose ``data/modules.json`` points a module at a folder outside ``data`` (``scripts/adopt_data.py``)."""
    install = importlib.import_module(f"{pkg}.mail.install")
    repo = tmp_path / "install"
    (repo / "data").mkdir(parents=True)
    monkeypatch.setattr(install, "REPO_ROOT", repo)
    folder = tmp_path / "original-app" / "data"

    def write(text):
        (repo / "data" / "modules.json").write_text(text, encoding="utf-8")
    return folder, write


def test_adopted_module_data_is_the_installs_own(pkg, install, faustus, tmp_path, adopted):
    folder, write = adopted
    write('{"enabled": [], "data_paths": {"%s": %s}}' % (PACKAGES[pkg][0], json.dumps(str(folder))))
    install(REAL_HUB, str(folder / "mcp-token"))
    mail, _ = helpers(pkg, faustus, CountingRunner(), tmp_path)
    assert mail.helper.isolation() == ""
    install(REAL_HUB, str(folder.parent / "elsewhere" / "mcp-token"))
    assert mail.helper.isolation() == "data"


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"data_paths": []}', '{"data_paths": {"shipments": 5, "products": ""}}',
                                  '{"data_paths": {"shipments": "/not/a/path/here"}}', '{"data_paths": {"shipments": "relative/dir"}}'])
def test_a_missing_or_odd_modules_file_adds_nothing(pkg, install, faustus, tmp_path, adopted, text):
    folder, write = adopted
    write(text)
    install(REAL_HUB, str(folder / "mcp-token"))
    runner = CountingRunner()
    mail, _ = helpers(pkg, faustus, runner, tmp_path)
    assert mail.helper.isolation() == "data" and mail.helper.run("scan")["isolated"] == "data"
    assert runner.calls == 0
