import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../context.js";
import { Busy, Check, Chip, Empty, ErrorBox, ExtLink, Field, Price, Rel, useBusy, useLoad } from "../components/ui.jsx";
import { num, shortClock } from "../format.js";

// The shops' own stock mail ("vuelve a estar disponible", reservations, price drops, sold out) matched to the watched products.
const STATUSES = ["all", "alerted", "matched", "unmatched", "ended", "old", "ignored"];
const KINDS = ["", "available", "preorder", "price_drop", "sold_out"];
const KIND_CLS = { available: "chip-ok", preorder: "chip-accent", price_drop: "chip-accent", sold_out: "chip-danger" };
const STATUS_CLS = { alerted: "chip-ok", matched: "", unmatched: "chip-amber", ended: "chip-danger", old: "", ignored: "" };

function AssignBox({ notice, targets, onDone }) {
  const { t, notify } = useApp();
  const [busy, run] = useBusy();
  const [target, setTarget] = useState("");
  const assign = () => run("assign", async () => {
    const r = await api.call("stock_notice_set", { notice_id: notice.id, action: "assign", target_id: target });
    notify(r.alert ? t("ntc_assigned_alert") : t("ntc_assigned"));
    await onDone();
  });
  const ignore = () => run("ignore", async () => {
    await api.call("stock_notice_set", { notice_id: notice.id, action: "ignore" });
    await onDone();
  });
  const mine = targets.filter((x) => !notice.shop || (x.url || "").includes(notice.shop));
  const options = mine.length ? mine : targets;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <select className="field" style={{ width: "auto", maxWidth: 260 }} value={target} onChange={(e) => setTarget(e.target.value)} aria-label={t("ntc_assign_to")}>
        <option value="">{t("ntc_assign_to")}</option>
        {options.map((x) => <option key={x.id} value={x.id}>{x.label || x.last_title || x.url}</option>)}
      </select>
      <Busy className="btn btn-sm" busy={busy.assign} disabled={!target} onClick={assign}>{t("ntc_assign")}</Busy>
      <Busy className="btn btn-sm" busy={busy.ignore} onClick={ignore}>{t("ntc_ignore")}</Busy>
    </div>
  );
}

function NoticeSettings({ status, onSaved }) {
  const { t, notify } = useApp();
  const [busy, run] = useBusy();
  const [form, setForm] = useState(null);
  useEffect(() => {
    if (status) setForm({ interval: String(status.interval_min), maxAge: String(status.max_age_hours), live: String(status.live_hours), domains: status.domains || "" });
  }, [status]);
  if (!status || !form) return null;
  const save = () => run("save", async () => {
    await api.call("settings_set", { values: { "mail.notices.interval_min": form.interval, "mail.notices.max_age_hours": form.maxAge, "mail.notices.live_hours": form.live, "mail.notices.domains": form.domains } });
    notify(t("saved"));
    await onSaved();
  });
  const toggle = (on) => run("toggle", async () => {
    await api.call("settings_set", { values: { "mail.notices.enabled": on ? "1" : "0" } });
    await onSaved();
  });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  return (
    <details className="panel">
      <summary className="font-semibold">{t("ntc_settings")}</summary>
      <div className="mt-3 space-y-3">
        <Check checked={status.enabled} onChange={toggle} disabled={busy.toggle}>{t("ntc_enabled")}</Check>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("ntc_interval")}><input className="field num" type="number" min="5" max="1440" value={form.interval} onChange={(e) => set("interval", e.target.value)} /></Field>
          <Field label={t("ntc_max_age")} hint={t("ntc_max_age_hint")}><input className="field num" type="number" min="1" max="168" value={form.maxAge} onChange={(e) => set("maxAge", e.target.value)} /></Field>
          <Field label={t("ntc_live")} hint={t("ntc_live_hint")}><input className="field num" type="number" min="1" max="168" value={form.live} onChange={(e) => set("live", e.target.value)} /></Field>
        </div>
        <Field label={t("ntc_pairs")} hint={t("ntc_pairs_hint")}>
          <textarea className="field mono" rows={3} value={form.domains} onChange={(e) => set("domains", e.target.value)} placeholder="news.tienda.com=tienda.es" />
        </Field>
        <Busy className="btn btn-primary btn-sm" busy={busy.save} onClick={save}>{t("save")}</Busy>
      </div>
    </details>
  );
}

function Rules({ rules, shops }) {
  const { t } = useApp();
  if (!rules) return null;
  return (
    <details className="panel">
      <summary className="font-semibold">{t("ntc_rules")}</summary>
      <div className="mt-3 space-y-3">
        <p className="help">{t("ntc_rules_intro", { min: rules.match_min })}</p>
        <div className="grid gap-3 md:grid-cols-2">
          {Object.entries(rules.kinds).map(([kind, phrases]) => (
            <div key={kind} className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <Chip className={KIND_CLS[kind]}>{t(`ntc_kind_${kind}`)}</Chip>
                <span className="help">{(rules.alert_for[kind] || []).length ? t("ntc_alert_as", { types: rules.alert_for[kind].map((x) => t(`ev_${x}`)).join(" / ") }) : t("ntc_ends_alerts")}</span>
              </div>
              <div className="help">{phrases.map((p) => `«${p}»`).join(" · ")}</div>
            </div>
          ))}
        </div>
        <div>
          <span className="label">{t("ntc_personal")}</span>
          <div className="help">{rules.personal.map((p) => `«${p}»`).join(" · ")}</div>
        </div>
        <div>
          <span className="label">{t("ntc_shops")}</span>
          {!shops?.length ? <p className="help">{t("ntc_no_shops")}</p> : (
            <div className="scroll-x">
              <table>
                <thead><tr><th>{t("mail_store")}</th><th>{t("ntc_senders")}</th><th className="r">{t("count_targets")}</th><th>{t("ntc_here")}</th></tr></thead>
                <tbody>
                  {shops.map((s) => (
                    <tr key={s.shop}>
                      <td className="font-semibold">{s.retailer || s.shop}<div className="help">{s.shop}</div></td>
                      <td className="mono">{s.senders.join(", ")}</td>
                      <td className="r num">{s.targets}</td>
                      <td>{s.paused_here ? <Chip className="chip-ok" title={t("ntc_paused_hint")}>{t("ntc_paused_n", { n: s.paused_here })}</Chip> : <span className="help">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </details>
  );
}

export default function MailNotices() {
  const { t, lang, notify, refreshDash } = useApp();
  const [busy, run] = useBusy();
  const [status, setStatus] = useState("all");
  const [kind, setKind] = useState("");
  const { data, error, loading, reload } = useLoad(() => api.call("stock_notices", { status, kind, limit: 150 }), [status, kind]);
  const targets = useLoad(() => api.call("target_list", {}), []);
  const st = data?.status;
  const rows = data?.notices || [];
  const scan = () => run("scan", async () => {
    const r = (await api.call("stock_notices_scan", {})).result || {};
    if (r.skipped) notify(r.skipped);
    else if (!r.ok) throw new Error((r.errors || []).join("; ") || t("mail_error"));
    else notify(t("ntc_scan_done", { scanned: r.scanned, notices: r.notices, matched: r.matched, alerts: r.alerts, ended: r.ended }));
    await reload();
    refreshDash();
  });
  return (
    <div className="space-y-3">
      <p className="help">{t("ntc_intro")}</p>
      {st && (
        <div className="panel space-y-3">
          <div className="kpis">
            <div className="kpi"><b className="num">{num(st.counts?.alerted ?? 0, 0, lang)}</b><span>{t("ntc_kpi_alerted")}</span></div>
            <div className="kpi"><b className="num">{num((st.counts?.matched ?? 0) + (st.counts?.ended ?? 0) + (st.counts?.old ?? 0), 0, lang)}</b><span>{t("ntc_kpi_matched")}</span></div>
            <div className="kpi"><b className="num">{num(st.counts?.unmatched ?? 0, 0, lang)}</b><span>{t("ntc_kpi_unmatched")}</span></div>
            <div className="kpi"><b className="num">{num(st.shops?.length ?? 0, 0, lang)}</b><span>{t("ntc_kpi_shops")}</span></div>
            <div className="kpi"><b><Rel ts={st.last_run_ts} /></b><span>{t("mail_last_scan")}</span></div>
            <div className="kpi"><b>{st.enabled ? <Rel ts={st.next_run_ts} /> : "—"}</b><span>{t("mail_next_scan")}</span></div>
          </div>
          {!st.enabled && <div className="banner banner-warn" role="status">{t("ntc_disabled")}</div>}
          {!st.windows_here && <div className="banner banner-info" role="status">{t("ntc_spark")}</div>}
          {st.last_error && <div className="banner banner-danger" role="alert">{t("mail_error")}: {st.last_error}</div>}
          <div className="flex flex-wrap items-center gap-2">
            <Busy className="btn btn-primary btn-sm" busy={busy.scan || st.running} onClick={scan}>{t("ntc_scan_now")}</Busy>
            <button type="button" className="btn btn-sm" onClick={reload}>{t("refresh")}</button>
          </div>
        </div>
      )}
      <Rules rules={data?.rules} shops={st?.shops} />
      <NoticeSettings status={st} onSaved={reload} />
      <div className="panel flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="label">{t("status")}</span>
          <select className="field" style={{ width: "auto" }} value={status} onChange={(e) => setStatus(e.target.value)}>{STATUSES.map((s) => <option key={s} value={s}>{t(`ntc_st_${s}`)}</option>)}</select>
        </label>
        <label className="block">
          <span className="label">{t("ntc_kind")}</span>
          <select className="field" style={{ width: "auto" }} value={kind} onChange={(e) => setKind(e.target.value)}>{KINDS.map((k) => <option key={k || "all"} value={k}>{k ? t(`ntc_kind_${k}`) : t("all")}</option>)}</select>
        </label>
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <p className="help">…</p> : !rows.length ? <Empty>{t("ntc_empty")}</Empty> : (
        <div className="panel scroll-x p-0">
          <table>
            <thead><tr><th>{t("mail_store")}</th><th>{t("ntc_col_mail")}</th><th>{t("ntc_kind")}</th><th className="r">{t("price")}</th><th>{t("ntc_col_target")}</th><th>{t("status")}</th></tr></thead>
            <tbody>
              {rows.map((n) => (
                <tr key={n.id} style={{ opacity: n.status === "ignored" || n.status === "old" ? 0.6 : 1 }}>
                  <td className="whitespace-nowrap font-semibold">{n.shop || n.sender_domain}<div className="help">{n.sender_domain}</div><div className="help">{shortClock(n.mail_ts, lang)}</div></td>
                  <td style={{ minWidth: 240, maxWidth: 440 }}>
                    <div className="font-semibold clamp2" title={n.subject}>{n.subject}</div>
                    {n.title && n.title !== n.subject && <div className="help clamp2">{n.title}</div>}
                    <div className="help">«{n.phrase}»{n.personal ? ` · ${t("ntc_personal_mail")}` : ""}</div>
                  </td>
                  <td><Chip className={KIND_CLS[n.kind]}>{t(`ntc_kind_${n.kind}`)}</Chip></td>
                  <td className="r"><Price value={n.price} currency={n.currency || "EUR"} old={n.old_price} /></td>
                  <td style={{ minWidth: 200 }}>
                    {n.target_id ? (
                      <div className="space-y-0.5">
                        <a href={`#/target/${encodeURIComponent(n.target_id)}`} className="font-semibold">{n.target_label || n.title}</a>
                        <div className="help">{t(`ntc_how_${n.match_how}`)}{n.match_score ? ` · ${n.match_score}` : ""}</div>
                        {n.url && <ExtLink href={n.url}>{t("open")}</ExtLink>}
                      </div>
                    ) : n.status === "ignored" ? <span className="help">—</span> : <AssignBox notice={n} targets={targets.data?.targets || []} onDone={reload} />}
                  </td>
                  <td>
                    <Chip className={STATUS_CLS[n.status]}>{t(`ntc_st_${n.status}`)}</Chip>
                    {n.alert_type && <div className="help">{t(`ev_${n.alert_type}`)}</div>}
                    {n.note && <div className="help">{t(`ntc_note_${n.note}`)}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
