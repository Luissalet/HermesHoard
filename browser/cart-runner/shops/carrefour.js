// Hermes cart runner — Carrefour. Works from one of the user's own lists (Favoritos): one reload reads every product.
// Takes one unit of each wanted product that can be bought, within the job's basket limit, and walks to the pay page.
// It never presses the pay button.
(async () => {
  const send = (message) => chrome.runtime.sendMessage(message).catch(() => null);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const visible = (el) => !!el && el.offsetParent !== null;
  const fold = (text) => String(text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
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
  const { job } = hello;
  let phase = hello.phase || "watch";
  const setPhase = (next, extra = {}) => { phase = next; return send({ type: "phase", job_id: job.id, phase: next, ...extra }); };
  const stage = (name, detail = "", items = "") => send({ type: "stage", job_id: job.id, stage: name, detail, items });
  const probe = async (label) => {
    if (!hello.probe) return;
    const describe = (el) => ({
      tag: el.tagName, text: (el.innerText || el.value || "").trim().slice(0, 80), id: el.id, cls: String(el.className).slice(0, 140),
      aria: el.getAttribute("aria-label") || "", href: el.getAttribute("href") || "", name: el.getAttribute("name") || "", type: el.type || "",
      disabled: !!el.disabled || el.getAttribute("aria-disabled"), checked: !!el.checked, visible: visible(el),
    });
    await send({ type: "probe", payload: {
      label, at: new Date().toISOString(), url: location.href, title: document.title, visibility: document.visibilityState,
      text: document.body.innerText.slice(0, 8000),
      controls: [...document.querySelectorAll("button, a[href], input, select, [role=button]")].slice(0, 700).map(describe),
      html: document.documentElement.outerHTML.replace(/<script[\s\S]*?<\/script>/g, "").replace(/<style[\s\S]*?<\/style>/g, "").slice(0, 500000),
    } });
  };
  const path = location.pathname;
  const listId = (job.ref || "").replace(/^list-/, "");
  const onList = path.includes("/mis-listas/" + listId);
  // the basket of this kind of product (the shop keeps food and the rest apart); the header link knows which
  const basketUrl = () => document.querySelector("a.cart-header__item, a.mini-cart")?.getAttribute("href") || "/nf/MiCarrito";
  const blocked = () => /just a moment|attention required|access denied/i.test(document.title)
    || (document.body.innerText.length < 900 && /you have been blocked|verifica que eres humano|verify you are human/i.test(document.body.innerText));

  if (phase === "done") return;

  // ------------------------------------------------------------ the list
  if (phase === "watch") {
    if (Date.now() < (hello.hold_until || 0)) { setTimeout(() => location.reload(), Math.max(5000, hello.hold_until - Date.now())); return; }
    const reloadIn = (seconds) => setTimeout(() => { location.href = job.url; }, seconds * 1000 * (0.8 + Math.random() * 0.4));
    if (blocked()) {
      await send({ type: "seen", job_id: job.id, state: "BLOCKED", hold_s: 600 });
      await stage("blocked");
      setTimeout(() => { location.href = job.url; }, 600_000);
      return;
    }
    if (!onList) {
      // the shop sent the tab somewhere else: almost always the sign-in page
      await sleep(4000);
      if (/login|acceso|identif|signin|auth/i.test(location.href)) {
        await send({ type: "seen", job_id: job.id, state: "UNKNOWN · sin sesión", hold_s: 600 });
        await stage("signed_out");
        return;
      }
      reloadIn(20);
      return;
    }
    await until(() => document.querySelector(".nf-product-list-item"), 12_000);
    await sleep(2500);                                                         // prices and buttons settle after the rows appear
    const tiles = [...document.querySelectorAll(".nf-product-list-item")].map((el) => {
      const button = el.querySelector(".add-to-cart-button__button");
      const priceText = el.getAttribute("app_price") || el.querySelector(".nf-product-list-item__price")?.innerText || "";
      const price = parseFloat(priceText.replace(/[^\d,.]/g, "").replace(/\./g, "").replace(",", "."));
      return {
        el, button, price: Number.isFinite(price) ? price : null,
        name: (el.querySelector(".nf-product-list-item__title-link")?.innerText || "").trim(),
        seller: (el.querySelector(".nf-product-list-item__feature-seller")?.innerText || "").trim(),
        buyable: !!button && !button.disabled && !button.classList.contains("add-to-cart-button__button--sold-out")
          && /a[nñ]adir|reservar|comprar/i.test(button.innerText || ""),
        inBasket: !!el.querySelector(".add-to-cart-button__less-unit-button, .add-to-cart-button__more-unit-button"),
      };
    });
    const entries = (job.match || []).map(fold).filter(Boolean);
    const wantedBy = (tile) => entries.find((entry) => entry.split(" ").every((word) => fold(tile.name).includes(word)));
    const wanted = tiles.filter((tile) => wantedBy(tile) && (job.third_party || !tile.seller));
    const taken = new Set(hello.taken || []);
    const picks = [];
    const entriesTaken = new Set();
    let total = 0;
    for (const tile of wanted) {
      if (!tile.buyable || taken.has(tile.name)) continue;
      if (job.max_total != null && (tile.price == null || total + tile.price > job.max_total + 0.005)) continue;
      picks.push(tile);
      entriesTaken.add(wantedBy(tile));
      total += tile.price || 0;
    }
    if (!picks.length && wanted.some((tile) => tile.inBasket)) {               // already in the basket: straight to the pay page
      await setPhase("checkout", { attempts: 0 });
      location.href = basketUrl();
      return;
    }
    if (!picks.length) {
      const state = !tiles.length ? "UNKNOWN" : !wanted.length ? "UNKNOWN · no están en la lista" : "OUT_OF_STOCK";
      await send({ type: "seen", job_id: job.id, state });
      reloadIn(job.interval_s || 90);
      return;
    }
    await setPhase("adding", { attempts: (hello.attempts || 0) + 1 });
    const got = [];
    for (const tile of picks) {
      tile.el.scrollIntoView({ block: "center" });
      await sleep(250);
      tile.button.click();
      // the shop answers with a dialog ("Ir a la cesta") or turns the button into a quantity stepper
      const ok = await until(() => [...document.querySelectorAll(".added-dialog__link-button")].find(visible)
        || (!tile.el.querySelector(".add-to-cart-button__full-button") && tile.el.querySelector(".add-to-cart-button__button:not(.add-to-cart-button__button--sold-out)"))
        || tile.el.querySelector("[class*=stepper], [class*=quantity], [class*=units]"), 8000, 150);
      if (ok) got.push(tile.name);
      const close = [...document.querySelectorAll(".added-dialog [class*=close], .added-dialog button, [class*=dialog__close], [class*=modal__close]")].find(visible);
      if (close && !/cesta/i.test(close.innerText || "")) close.click();
      await sleep(700);
    }
    await probe("after-add");
    await setPhase("checkout", { attempts: 0, taken: [...taken, ...got] });
    if (got.length) await stage("added", "", got.join("\n"));
    location.href = basketUrl();
    return;
  }

  // ------------------------------------------------------------ basket and checkout: mapped with the probe first
  if (phase === "adding" && onList) { await setPhase("checkout", { attempts: 0 }); location.href = basketUrl(); return; }
  if (phase !== "checkout") return;
  const entries = (job.match || []).map(fold).filter(Boolean);
  const mine = (name) => entries.some((entry) => entry.split(" ").every((word) => fold(name).includes(word)));
  const button = (pattern) => [...document.querySelectorAll("button, a.c-button")].find((el) => visible(el) && !el.disabled && pattern.test((el.innerText || "").trim()));

  const stopAtPay = async (detail = "") => {
    await sleep(2500);
    const pay = button(/^finalizar compra/i);
    if (pay) { pay.scrollIntoView({ block: "center" }); pay.style.outline = "4px solid #e0245e"; pay.style.outlineOffset = "4px"; }
    const total = (document.body.innerText.match(/TOTAL A PAGAR\s*([\d.,]+\s*€)/i) || [])[1];
    detail = detail || (total ? `total ${total}` : "");
    await probe("pay " + location.pathname);
    await setPhase("done", { attempts: 0 });
    await stage("pay", detail);
  };
  const toPay = async () => {
    // "Entrega y horario": the address and the delivery the shop proposes are left as they are
    const go = await until(() => button(/^continuar al pago/i), 12_000);
    if (!go) { await setPhase("done"); await stage("delivery"); return; }
    const from = location.pathname;
    go.click();
    const moved = await until(() => location.pathname !== from, 15_000);
    if (!moved) { await probe("stuck " + location.pathname); await setPhase("done"); await stage("delivery"); return; }
    await stopAtPay();
  };

  if (/MiCarrito\/?$/i.test(path)) {
    await until(() => document.querySelector(".nfItem-productName, .cartEmpty__btn, [class*=cartEmpty]"), 12_000);
    await sleep(1500);
    const lines = [...document.querySelectorAll(".nfItem-productName")].filter((el) => mine(el.innerText));
    if (!lines.length) {
      await stage("lost");
      await setPhase("watch", { attempts: 0, taken: [] });
      location.href = job.url;
      return;
    }
    // one unit of each: a second click on a slow page must not become a second box
    let extra = false;
    for (const line of lines) {
      let box = line;
      for (let up = 0; up < 8 && box && !box.querySelector(".unit-picker__input"); up += 1) box = box.parentElement;
      const input = () => [...(box?.querySelectorAll(".unit-picker__input") || [])].find(visible) || box?.querySelector(".unit-picker__input");
      const units = () => parseInt(input()?.value || "1", 10) || 1;
      for (let guard = 0; guard < 4 && units() > 1; guard += 1) {
        const before = units();
        const minus = [...box.querySelectorAll(".unit-picker__minus")].find(visible);
        minus?.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
        minus?.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
        minus?.click();
        await until(() => units() < before, 8000, 150);
        await sleep(800);
      }
      if (units() > 1) {                                                       // the stepper did not answer: write the number
        const el = input();
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, "1");
        for (const type of ["input", "change", "blur"]) el.dispatchEvent(new Event(type, { bubbles: true }));
        el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
        await sleep(4000);
      }
      extra = extra || units() > 1;
    }
    await probe("basket-ready");
    if (extra) { await setPhase("done"); await stage("delivery", "hay más de una unidad en la cesta: déjala en una antes de pagar"); return; }
    const go = await until(() => button(/^continuar a entrega/i) || button(/^continuar/i), 6000);
    if (!go) { await setPhase("done"); await stage("delivery", "la cesta no ofrece continuar"); return; }
    go.click();
    await until(() => /delivery-and-schedule/.test(location.pathname), 15_000);
    await toPay();
    return;
  }
  if (/delivery-and-schedule/.test(path)) { await toPay(); return; }
  await sleep(3500);
  await stopAtPay();
})();
