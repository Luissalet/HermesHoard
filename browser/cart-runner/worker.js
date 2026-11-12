// Hermes cart runner — background. Keeps one pinned tab per job, relays what the page script sees to Hermes and makes
// noise when a product reaches the basket. The page script (shops/*.js) does the clicking; nothing here pays.

const SYNC_ALARM = "hermes-cart-sync";
const WATCHDOG_S = 75;          // a runner tab silent for this long is reloaded
const BEAT_EVERY_MS = 45_000;   // heartbeats to Hermes are thinned to this
const LOUD = new Set(["added", "pay", "password", "delivery", "signed_out"]);
const STAGE_TEXT = {
  added: "En la cesta. Pasando al pago…",
  pay: "PAGA YA: el pago está abierto en esta ventana.",
  password: "La tienda pide tu contraseña antes del pago.",
  delivery: "Elige la entrega y paga.",
  lost: "Se agotó antes de llegar al pago. Sigo vigilando.",
  blocked: "La tienda ha bloqueado la pestaña. Espero y reintento.",
  signed_out: "Sesión cerrada en la tienda: inicia sesión.",
};

const store = {
  async get(keys) { return chrome.storage.local.get(keys); },
  async set(values) { return chrome.storage.local.set(values); },
};

async function config() {
  const { config: saved = {} } = await store.get("config");
  let file = {};
  try { file = await (await fetch(chrome.runtime.getURL("config.json"))).json(); } catch { /* optional file */ }
  const merged = { hermes: "", key: "", paused: false, ...file, ...saved };
  merged.hermes = String(merged.hermes || "").replace(/\/+$/, "");
  return merged;
}

async function hermes(path, body) {
  const cfg = await config();
  if (!cfg.hermes || !cfg.key) throw new Error("Falta la dirección de Hermes o la clave");
  const response = await fetch(`${cfg.hermes}/api/cart/x/${path}`, {
    method: body ? "POST" : "GET",
    headers: { "X-Hermes-Cart-Key": cfg.key, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Hermes respondió ${response.status}`);
  return response.json();
}

// ---------------------------------------------------------------- jobs and their tabs
async function state() {
  const { jobs = [], runs = {}, link = {} } = await store.get(["jobs", "runs", "link"]);
  return { jobs, runs, link };
}

// Loaded unpacked, the files on disk can be newer than the running copy: a higher version there restarts the extension.
async function selfUpdate() {
  try {
    const disk = await (await fetch(chrome.runtime.getURL("manifest.json"), { cache: "no-store" })).json();
    if (disk.version && disk.version !== chrome.runtime.getManifest().version) chrome.runtime.reload();
  } catch { /* packed builds have nothing newer on disk */ }
}

async function sync() {
  await selfUpdate();
  const cfg = await config();
  let link;
  try {
    const data = await hermes("jobs");
    await store.set({ jobs: data.jobs || [] });
    link = { ok: true, at: Date.now(), error: "" };
  } catch (error) {
    link = { ok: false, at: Date.now(), error: String(error.message || error) };
  }
  await store.set({ link });
  if (!cfg.paused) await tend();
  await badge();
}

function runOf(runs, job) {
  const run = runs[job.id];
  // Hermes re-armed the job (or it is new): start watching again
  // (in the tab it already has, sent back to the job's page)
  if (!run || (job.armed_at || 0) > (run.armed_at || 0)) {
    return { phase: "watch", armed_at: job.armed_at || 0, tabId: run?.tabId ?? null, seen: 0, checks: 0, back: run?.tabId != null };
  }
  return run;
}

async function tabAlive(tabId) {
  if (tabId == null) return null;
  try { return await chrome.tabs.get(tabId); } catch { return null; }
}

async function tend() {
  const { jobs, runs } = await state();
  const next = {};
  for (const job of jobs) {
    const run = runOf(runs, job);
    next[job.id] = run;
    const tab = await tabAlive(run.tabId);
    if (!job.enabled || run.phase === "done") continue;
    if (!tab) {
      const created = await chrome.tabs.create({ url: job.url, active: false, pinned: true });
      run.tabId = created.id;
      run.seen = Date.now();
      try { await chrome.tabs.update(created.id, { autoDiscardable: false }); } catch { /* older browsers */ }
    } else if (run.back || (run.phase === "watch" && Date.now() - (run.seen || 0) > WATCHDOG_S * 1000 && Date.now() >= (run.hold_until || 0))) {
      delete run.back;
      run.seen = Date.now();
      try { await chrome.tabs.update(tab.id, { url: job.url }); } catch { run.tabId = null; }
    }
  }
  // tabs of jobs removed in Hermes, or paused while still watching, are closed (only tabs this extension opened)
  for (const [id, run] of Object.entries(runs)) {
    const job = jobs.find((j) => j.id === id);
    if ((!job || (!job.enabled && run.phase === "watch")) && run.tabId != null) {
      try { await chrome.tabs.remove(run.tabId); } catch { /* already closed */ }
      if (next[id]) next[id].tabId = null;
    }
  }
  await store.set({ runs: next });
}

async function badge() {
  const { jobs, runs, link } = await state();
  const cfg = await config();
  const watching = jobs.filter((j) => j.enabled && (runs[j.id]?.phase || "watch") === "watch").length;
  const hot = jobs.some((j) => ["checkout", "done"].includes(runs[j.id]?.phase) && j.enabled);
  const text = cfg.paused ? "II" : hot ? "!" : !link.ok ? "?" : watching ? String(watching) : "";
  await chrome.action.setBadgeText({ text });
  await chrome.action.setBadgeBackgroundColor({ color: hot ? "#c0392b" : !link.ok || cfg.paused ? "#8a8a8a" : "#1f7a4d" });
}

// ---------------------------------------------------------------- noise
async function siren(seconds) {
  try {
    if (!(await chrome.offscreen.hasDocument())) {
      await chrome.offscreen.createDocument({ url: "siren.html", reasons: ["AUDIO_PLAYBACK"], justification: "Aviso sonoro: producto en la cesta" });
    }
    await chrome.runtime.sendMessage({ to: "siren", seconds });
  } catch { /* no sound is not a reason to stop */ }
}

async function announce(job, stage, tabId) {
  const loud = LOUD.has(stage);
  chrome.notifications.create(`hermes-cart-${job.id}-${stage}-${Date.now()}`, {
    type: "basic", iconUrl: "icon-128.png", title: job.name || "Hermes", message: STAGE_TEXT[stage] || stage,
    priority: loud ? 2 : 0, requireInteraction: loud,
  });
  if (!loud) return;
  siren(stage === "added" ? 6 : 25);
  if (stage !== "added" && tabId != null) {
    try {
      const tab = await chrome.tabs.update(tabId, { active: true });
      await chrome.windows.update(tab.windowId, { focused: true, drawAttention: true });
    } catch { /* tab gone */ }
  }
}

// ---------------------------------------------------------------- the page script speaks
const lastBeat = {};

async function onMessage(message, sender) {
  const tabId = sender.tab?.id;
  if (message.type === "hello") {
    // which job, if any, does this tab run?
    const cfg = await config();
    const { jobs, runs } = await state();
    if (cfg.paused) return { job: null };
    const job = jobs.find((j) => j.enabled && runs[j.id]?.tabId === tabId);
    if (!job) return { job: null };
    const run = runs[job.id];
    const { profile = {} } = await store.get("profile");
    return { job, phase: run.phase, hold_until: run.hold_until || 0, attempts: run.attempts || 0, profile, probe: !!cfg.probe,
             taken: run.taken || [] };
  }
  if (message.type === "seen" || message.type === "phase" || message.type === "stage") {
    const { jobs, runs } = await state();
    const job = jobs.find((j) => j.id === message.job_id);
    const run = job && runs[job.id];
    if (!run) return { ok: false };
    run.seen = Date.now();
    if (message.type === "seen") {
      run.checks = (run.checks || 0) + 1;
      run.last_state = message.state;
      if (message.hold_s) run.hold_until = Date.now() + message.hold_s * 1000;
      await store.set({ runs });
      if (Date.now() - (lastBeat[job.id] || 0) > BEAT_EVERY_MS) {
        lastBeat[job.id] = Date.now();
        hermes("beat", { job_id: job.id, state: message.state, name: message.name || "", price: message.price ?? null }).catch(() => {});
      }
      return { ok: true };
    }
    if (message.type === "phase") {
      run.phase = message.phase;
      if (message.attempts != null) run.attempts = message.attempts;
      if (message.taken) run.taken = message.taken;
      await store.set({ runs });
      await badge();
      return { ok: true };
    }
    // a stage worth telling the user
    run.stage = message.stage;
    run.stage_at = Date.now();
    if (message.items) run.items = message.items;
    await store.set({ runs });
    announce({ ...job, name: (run.items || "").split("\n").join(" + ") || job.name }, message.stage, tabId);
    hermes("report", { job_id: job.id, stage: message.stage, detail: message.detail || "", items: message.items || "" }).catch(() => {});
    await badge();
    return { ok: true };
  }
  if (message.type === "probe") {
    // development aid: a page outline goes to a local listener named in config.json ("probe"), nowhere else
    const cfg = await config();
    if (cfg.probe) fetch(cfg.probe, { method: "POST", body: JSON.stringify(message.payload) }).catch(() => {});
    return { ok: !!cfg.probe };
  }
  if (message.type === "popup-sync") { await sync(); return { ok: true }; }
  if (message.type === "popup-rearm") {
    const { runs } = await state();
    if (runs[message.job_id]) { runs[message.job_id] = { ...runs[message.job_id], phase: "watch", attempts: 0, stage: "", hold_until: 0 }; }
    await store.set({ runs });
    await sync();
    return { ok: true };
  }
  if (message.type === "popup-test") { siren(4); return { ok: true }; }
  return undefined;
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message?.to === "siren") return false;
  onMessage(message, sender).then(respond, (error) => respond({ error: String(error) }));
  return true;
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const { runs } = await state();
  let changed = false;
  for (const run of Object.values(runs)) if (run.tabId === tabId) { run.tabId = null; changed = true; }
  if (changed) await store.set({ runs });
});

chrome.alarms.onAlarm.addListener((alarm) => { if (alarm.name === SYNC_ALARM) sync(); });
chrome.runtime.onInstalled.addListener(() => { chrome.alarms.create(SYNC_ALARM, { periodInMinutes: 0.5 }); sync(); });
chrome.runtime.onStartup.addListener(() => { chrome.alarms.create(SYNC_ALARM, { periodInMinutes: 0.5 }); sync(); });
chrome.storage.onChanged.addListener((changes) => { if (changes.config) sync(); });
