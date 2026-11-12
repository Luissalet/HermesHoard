const $ = (id) => document.getElementById(id);
const STATE_TEXT = { OUT_OF_STOCK: "agotado", UNKNOWN: "sin botón de compra", BLOCKED: "bloqueada" };
const STAGE_TEXT = { added: "En la cesta", pay: "Esperando tu pago", password: "Pide tu contraseña", delivery: "Elige la entrega", lost: "Se agotó antes del pago", blocked: "Bloqueada", signed_out: "Sin sesión" };

function ago(ms) {
  if (!ms) return "nunca";
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  return s < 90 ? `hace ${s} s` : `hace ${Math.round(s / 60)} min`;
}

async function fileConfig() {
  try { return await (await fetch(chrome.runtime.getURL("config.json"))).json(); } catch { return {}; }
}

async function render() {
  const { jobs = [], runs = {}, link = {}, config = {}, profile = {} } = await chrome.storage.local.get(["jobs", "runs", "link", "config", "profile"]);
  const cfg = { ...(await fileConfig()), ...config };
  $("pause").textContent = cfg.paused ? "Reanudar" : "Pausar";
  $("link").className = "link" + (link.ok ? "" : " bad");
  $("link").textContent = link.ok ? `Conectada con Hermes · ${ago(link.at)}` : `Sin conexión con Hermes${link.error ? ": " + link.error : ""}`;
  const box = $("jobs");
  box.replaceChildren();
  if (!jobs.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "Hermes no tiene productos en la cesta automática.";
    box.append(empty);
  }
  for (const job of jobs) {
    const run = runs[job.id] || {};
    const card = document.createElement("div");
    card.className = "job";
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = job.name || job.ref;
    const meta = document.createElement("div");
    meta.className = "meta";
    const waiting = run.phase === "checkout" || run.phase === "done" || run.phase === "adding";
    if (!job.enabled) meta.textContent = "En pausa desde Hermes";
    else if (waiting) { meta.textContent = STAGE_TEXT[run.stage] || "En la cesta"; meta.classList.add("hot"); }
    else meta.textContent = `Vigilando cada ${job.interval_s} s · ${STATE_TEXT[(run.last_state || "").split(" ")[0]] || "abriendo"} · ${run.checks || 0} lecturas · ${ago(run.seen)}`;
    card.append(name, meta);
    if (waiting) {
      const row = document.createElement("div");
      row.className = "row";
      const show = document.createElement("button");
      show.textContent = "Ir a la pestaña";
      show.onclick = async () => { if (run.tabId != null) { const tab = await chrome.tabs.update(run.tabId, { active: true }); chrome.windows.update(tab.windowId, { focused: true }); } };
      const again = document.createElement("button");
      again.textContent = "Volver a vigilar";
      again.onclick = async () => { await chrome.runtime.sendMessage({ type: "popup-rearm", job_id: job.id }); render(); };
      row.append(show, again);
      card.append(row);
    }
    box.append(card);
  }
  if (document.activeElement?.tagName !== "INPUT") {
    $("hermes").value = cfg.hermes || "";
    $("key").value = cfg.key || "";
    $("doc_type").value = profile.doc_type || "DNI";
    $("doc_number").value = profile.doc_number || "";
  }
}

$("pause").onclick = async () => {
  const { config = {} } = await chrome.storage.local.get("config");
  const cfg = { ...(await fileConfig()), ...config };
  await chrome.storage.local.set({ config: { ...config, paused: !cfg.paused } });
  render();
};
$("sync").onclick = async () => { await chrome.runtime.sendMessage({ type: "popup-sync" }); render(); };
$("test").onclick = () => chrome.runtime.sendMessage({ type: "popup-test" });
$("save").onclick = async () => {
  const { config = {} } = await chrome.storage.local.get("config");
  await chrome.storage.local.set({
    config: { ...config, hermes: $("hermes").value.trim(), key: $("key").value.trim() },
    profile: { doc_type: $("doc_type").value, doc_number: $("doc_number").value.trim() },
  });
  await chrome.runtime.sendMessage({ type: "popup-sync" });
  render();
};
chrome.storage.onChanged.addListener(render);
render();
