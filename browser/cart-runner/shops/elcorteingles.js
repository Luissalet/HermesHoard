// Hermes cart runner — El Corte Inglés. Runs in every tab of the shop but only acts in the tab the extension opened
// for a job. Watches the buy button, adds one unit, and walks cesta -> entrega -> resumen. It never presses the pay button.
(async () => {
  const send = (message) => chrome.runtime.sendMessage(message).catch(() => null);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const visible = (el) => !!el && el.offsetParent !== null;
  async function until(test, ms, step = 200) {
    const end = Date.now() + ms;
    for (;;) {
      const value = test();
      if (value) return value;
      if (Date.now() > end) return null;
      await sleep(step);
    }
  }

  const hello = await send({ type: "hello" });
  if (!hello || !hello.job) return;
  const { job, profile = {} } = hello;
  let phase = hello.phase || "watch";
  const setPhase = (next, attempts) => { phase = next; return send({ type: "phase", job_id: job.id, phase: next, attempts }); };
  const stage = (name, detail = "") => send({ type: "stage", job_id: job.id, stage: name, detail });
  const path = location.pathname;

  // ------------------------------------------------------------ sign-in wall on the way to the pay page
  if (location.hostname === "cuenta.elcorteingles.es") {
    if (phase === "checkout") await stage("password");
    return;
  }
  if (phase === "done") return;

  // ------------------------------------------------------------ the product page
  const onProduct = path.includes("/" + job.ref);
  if (onProduct && phase === "adding") { location.href = "/purchase/v2/cesta/"; return; }   // reloaded mid-click: look in the basket
  if (onProduct && phase === "checkout") return;                                             // the user came back by hand
  if (onProduct) {
    if (Date.now() < (hello.hold_until || 0)) { setTimeout(() => location.reload(), Math.max(5000, hello.hold_until - Date.now())); return; }
    const reloadIn = (seconds) => setTimeout(() => location.reload(), seconds * 1000 * (0.75 + Math.random() * 0.5));
    if (/access denied/i.test(document.title) || (document.body.innerText.length < 600 && /access denied|acceso denegado/i.test(document.body.innerText))) {
      await send({ type: "seen", job_id: job.id, state: "BLOCKED", hold_s: 300 });
      await stage("blocked");
      setTimeout(() => location.reload(), 300_000);
      return;
    }
    const button = await until(() => document.querySelector("#add_to_cart_main_button"), 10_000);
    let product = {};
    for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
      try { const data = JSON.parse(node.textContent); if (data && data["@type"] === "Product") product = data; } catch { /* not JSON */ }
    }
    const offer = Array.isArray(product.offers) ? product.offers[0] : product.offers || {};
    const label = (button?.innerText || "").trim();
    const dead = !button || button.getAttribute("aria-disabled") === "true" || button.disabled
      || button.classList.contains("pds-button--is-disabled") || /agotado|no disponible|pr[oó]ximamente/i.test(label);
    const signedIn = !!document.querySelector(".user-logged-name");
    if (dead) {
      await send({ type: "seen", job_id: job.id, name: product.name || "", price: typeof offer.price === "number" ? offer.price : null,
                   state: (button ? "OUT_OF_STOCK" : "UNKNOWN") + (signedIn ? "" : " · sin sesión") });
      reloadIn(job.interval_s || 15);
      return;
    }
    // it can be bought: one click, then make sure the shop took it
    const attempts = (hello.attempts || 0) + 1;
    await setPhase("adding", attempts);
    button.click();
    const added = await until(() => document.querySelector(".cross-sell-pds-list__view-cart-btn")
      || (/producto añadido/i.test(document.body.innerText) ? true : null), 8000, 150);
    if (!added && attempts < 3) { await setPhase("watch", attempts); location.reload(); return; }
    await setPhase("checkout", 0);
    if (added) await stage("added");
    location.href = "/purchase/v2/cesta/";
    return;
  }

  if (!path.startsWith("/purchase/") || (phase !== "checkout" && phase !== "adding")) return;

  // ------------------------------------------------------------ the basket
  if (/\/cesta\/?$/.test(path)) {
    const inBasket = () => [...document.querySelectorAll(".quantity__trash-icon")].some((icon) => {
      let node = icon;
      for (let up = 0; up < 7 && node; up += 1) {
        node = node.parentElement;
        if (node && node.querySelector(`a[href*="/${job.ref}"]`)) return true;
      }
      return false;
    });
    const found = await until(inBasket, 9000);
    if (!found) {
      await stage("lost");
      await setPhase("watch", 0);
      location.href = job.url;
      return;
    }
    if (phase === "adding") { await setPhase("checkout", 0); await stage("added"); }
    const go = await until(() => [...document.querySelectorAll("#continue-button")].find(visible), 6000);
    if (go) go.click();
    // still here after a while: the shop wants something from the user
    await sleep(12_000);
    if (/\/cesta\/?$/.test(location.pathname)) await stage("delivery", "la cesta no avanza al pago");
    return;
  }

  // ------------------------------------------------------------ delivery choice (only shown when the shop needs one)
  if (/\/purchase\/(v2\/)?entrega\/?$/.test(path)) {
    const next = await until(() => document.querySelector("#deliveries-go-to-order-summary"), 8000);
    const radios = [...document.querySelectorAll('input[type="radio"]')];
    const isPickup = (radio) => /pickup|click_and_car|collect|tienda|store/i.test(`${radio.name} ${radio.id} ${radio.value}`);
    const home = radios.find((radio) => !isPickup(radio));
    if (home && !home.checked) { (home.closest("label") || document.querySelector(`label[for="${home.id}"]`) || home).click(); await sleep(800); }
    if (!home && (job.delivery || "home") === "home") { await stage("delivery", "solo ofrece recogida en tienda"); return; }
    if (next) next.click();
    await sleep(7000);
    if (/entrega\/?$/.test(location.pathname)) await stage("delivery");
    return;
  }

  // ------------------------------------------------------------ the page with the pay button: stop here
  const pay = await until(() => document.querySelector("#checkout-go-to-payment-methods-btn-test")
    || [...document.querySelectorAll("button")].find((b) => /pagar/i.test(b.innerText || "")), 10_000);
  // the buyer's identity document, when the shop asks for it and the user saved it in this browser
  const docType = document.querySelector('select[name="id_document_type"]');
  const docNumber = document.querySelector('input[name="PD-number"]');
  const fill = (el, value) => {
    const proto = el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };
  if (docType && docNumber && profile.doc_number && !docNumber.value) {
    const wanted = (profile.doc_type || "DNI").toLowerCase();
    const option = [...docType.options].find((o) => o.value && (o.text || "").toLowerCase().includes(wanted.slice(0, 3)));
    if (option) fill(docType, option.value);
    await sleep(200);
    fill(docNumber, profile.doc_number);
  }
  if (pay) {
    pay.scrollIntoView({ block: "center" });
    pay.style.outline = "4px solid #e0245e";
    pay.style.outlineOffset = "4px";
  }
  await setPhase("done", 0);
  await stage("pay", docType && docNumber && !docNumber.value ? "falta tu documento de identidad" : "");
})();
