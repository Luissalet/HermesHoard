import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../context.js";
import { Busy, Chip, Empty, ErrorBox, ExtLink, Field, Price, Section, Switch, useBusy, useLoad } from "../components/ui.jsx";

// Products the user's own browser puts in the basket the moment they can be bought (browser/cart-runner).
const STAGE_CLS = { added: "chip-ok", pay: "chip-ok", password: "chip-amber", delivery: "chip-amber", lost: "chip-danger", blocked: "chip-danger", signed_out: "chip-danger" };

function age(seconds, t) {
  if (seconds === null || seconds === undefined) return t("cart_never");
  if (seconds < 90) return t("cart_ago_s", { n: seconds });
  if (seconds < 5400) return t("cart_ago_min", { n: Math.round(seconds / 60) });
  return t("cart_ago_h", { n: Math.round(seconds / 3600) });
}

function JobRow({ job, onChanged }) {
  const { t, confirm, notify } = useApp();
  const [busy, run] = useBusy();
  const update = (key, args, message) => run(key, async () => {
    await api.call("cart_job_update", { id: job.id, ...args });
    if (message) notify(message);
    await onChanged();
  });
  const remove = () => run("remove", async () => {
    if (!(await confirm({ title: t("cart_remove_title"), message: job.name, confirmLabel: t("cart_remove") }))) return;
    await api.call("cart_job_remove", { id: job.id });
    await onChanged();
  });
  const state = (job.state || "").split(" ")[0];
  return (
    <div className="panel space-y-2">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="font-semibold" style={{ overflowWrap: "anywhere" }}>{job.name}</div>
          <div className="help">{job.shop_name}{job.price != null && <> · <Price value={job.price} currency="EUR" /></>}</div>
        </div>
        <Switch checked={job.enabled} disabled={busy.enabled} label={t("cart_enabled")} onChange={(on) => update("enabled", { enabled: on })} />
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {job.stage
          ? <Chip className={STAGE_CLS[job.stage] || ""}>{t(`cart_stage_${job.stage}`)}</Chip>
          : !job.enabled ? <Chip>{t("cart_paused")}</Chip>
          : job.watching ? <Chip className="chip-ok">{t("cart_watching")}</Chip>
          : <Chip className="chip-danger">{t("cart_not_watching")}</Chip>}
        {!job.stage && state && <Chip>{t(`cart_state_${state}`)}</Chip>}
        {(job.state || "").includes("sin sesión") && <Chip className="chip-amber">{t("cart_signed_out")}</Chip>}
        <span className="help">{t("cart_last", { when: age(job.beat_age_s, t), n: job.checks || 0 })}</span>
      </div>
      {job.kind === "list" && (
        <div className="help">{t("cart_takes")}: {(job.match || []).join(" · ")}{job.max_total != null && <> · {t("cart_up_to")} <Price value={job.max_total} currency="EUR" /></>}</div>
      )}
      {job.stage && job.detail && <div className="help">{job.detail}</div>}
      <div className="flex flex-wrap items-center gap-2">
        <label className="help inline-flex items-center gap-1.5">{t("cart_every")}
          <select className="field" style={{ width: "auto" }} value={job.interval_s} disabled={busy.interval}
            onChange={(e) => update("interval", { interval_s: Number(e.target.value) })}>
            {[...new Set([10, 15, 20, 30, 60, 90, 120, job.interval_s])].sort((a, b) => a - b).map((s) => <option key={s} value={s}>{s} s</option>)}
          </select>
        </label>
        <label className="help inline-flex items-center gap-1.5">{t("cart_delivery")}
          <select className="field" style={{ width: "auto" }} value={job.delivery || "home"} disabled={busy.delivery}
            onChange={(e) => update("delivery", { delivery: e.target.value })}>
            <option value="home">{t("cart_delivery_home")}</option>
            <option value="any">{t("cart_delivery_any")}</option>
          </select>
        </label>
        <div className="ml-auto flex flex-wrap gap-2">
          <ExtLink href={job.url}>{t("cart_open")}</ExtLink>
          {job.stage && <Busy className="btn btn-sm" busy={busy.rearm} onClick={() => update("rearm", { rearm: true }, t("cart_rearmed"))}>{t("cart_rearm")}</Busy>}
          <Busy className="btn btn-sm" busy={busy.remove} onClick={remove}>{t("cart_remove")}</Busy>
        </div>
      </div>
    </div>
  );
}

export default function Cart() {
  const { t, notify } = useApp();
  const { data, error, loading, reload } = useLoad(() => api.call("cart_jobs"), []);
  const [busy, run] = useBusy();
  const [url, setUrl] = useState("");
  const [match, setMatch] = useState("");
  const [maxTotal, setMaxTotal] = useState("");
  const [shown, setShown] = useState(false);
  const isList = /\/mis-listas/.test(url);
  useEffect(() => {
    const timer = setInterval(() => { if (!document.hidden) reload(); }, 15000);
    return () => clearInterval(timer);
  }, [reload]);
  const add = (e) => {
    e.preventDefault();
    run("add", async () => {
      const args = { url: url.trim() };
      if (isList) {
        args.match = match.split("\n").map((line) => line.trim()).filter(Boolean);
        if (maxTotal.trim()) args.max_total = Number(maxTotal.replace(",", "."));
      }
      await api.call("cart_job_add", args);
      setUrl("");
      setMatch("");
      setMaxTotal("");
      notify(t("cart_added"));
      await reload();
    });
  };
  const jobs = data?.jobs || [];
  const key = data?.extension?.key || "";
  const address = `${window.location.origin}/products`;
  const copy = (text) => navigator.clipboard.writeText(text).then(() => notify(t("cart_copied")));
  return (
    <div className="space-y-5">
      <div>
        <h1>{t("cart_title")}</h1>
        <p className="help mt-1" style={{ maxWidth: "70ch" }}>{t("cart_intro")}</p>
      </div>
      <form className="panel flex flex-wrap items-end gap-2" onSubmit={add}>
        <Field label={t("cart_url")} hint={t("cart_url_hint", { shops: (data?.shops || []).join(", ") })} className="min-w-0 flex-1">
          <input className="field" type="url" required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.elcorteingles.es/…" />
        </Field>
        <Busy type="submit" className="btn btn-primary" busy={busy.add} disabled={!url.trim() || (isList && !match.trim())}>{t("cart_add")}</Busy>
        {isList && (
          <div className="grid w-full gap-2 md:grid-cols-[minmax(0,1fr)_180px]">
            <Field label={t("cart_match")} hint={t("cart_match_hint")}>
              <textarea className="field" rows={3} value={match} onChange={(e) => setMatch(e.target.value)} placeholder={"premium ditto\nlata sylveon"} />
            </Field>
            <Field label={t("cart_max_total")} hint={t("cart_max_total_hint")}>
              <input className="field" inputMode="decimal" value={maxTotal} onChange={(e) => setMaxTotal(e.target.value)} placeholder="92,98" />
            </Field>
          </div>
        )}
      </form>
      <ErrorBox error={error} />
      <Section title={t("cart_jobs")} count={jobs.length} id="cart-jobs">
        {!loading && !jobs.length && <Empty>{t("cart_empty")}</Empty>}
        {jobs.map((job) => <JobRow key={job.id} job={job} onChanged={reload} />)}
      </Section>
      <details className="panel">
        <summary className="font-semibold">{t("cart_ext_title")}</summary>
        <ol className="help mt-2 list-decimal space-y-1 pl-5">
          <li>{t("cart_ext_1")}</li>
          <li>{t("cart_ext_2")} <code>browser/cart-runner</code></li>
          <li>{t("cart_ext_3")}</li>
        </ol>
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <Field label={t("cart_ext_address")}>
            <div className="flex gap-2"><input className="field" readOnly value={address} /><button type="button" className="btn btn-sm" onClick={() => copy(address)}>{t("cart_copy")}</button></div>
          </Field>
          <Field label={t("cart_ext_key")}>
            <div className="flex gap-2">
              <input className="field" readOnly type={shown ? "text" : "password"} value={key} />
              <button type="button" className="btn btn-sm" onClick={() => setShown((s) => !s)}>{shown ? t("cart_hide") : t("cart_show")}</button>
              <button type="button" className="btn btn-sm" onClick={() => copy(key)}>{t("cart_copy")}</button>
            </div>
          </Field>
        </div>
      </details>
    </div>
  );
}
