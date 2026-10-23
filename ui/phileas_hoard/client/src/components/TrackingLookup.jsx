import React, { useEffect, useReducer, useRef } from "react";
import { api } from "../api.js";
import { useApp } from "../context.js";
import { shortClock, windowLabel } from "../format.js";
import { useContextProvider } from "./hooks.js";
import { ErrorBox, ExtLink, Field, Section, StatusPill } from "./ui.jsx";
import { initialLookup, trackingLookup } from "./tracking-lookup.js";

export default function TrackingLookup({ open, onClose }) {
  const { t, lang, carriers, loadCarriers } = useApp();
  const [state, dispatch] = useReducer(trackingLookup, initialLookup);
  const sequence = useRef(0);
  const { fields, result, error, loading } = state;
  useEffect(() => { if (open) loadCarriers(); }, [open, loadCarriers]);
  useContextProvider(() => ({ form: "tracking_lookup", mode: "query", fields, pending: loading, result: result || null }), open);
  const submit = async (event) => {
    event.preventDefault();
    if (!fields.tracking_number.trim()) return;
    const id = ++sequence.current;
    const query = { tracking_number: fields.tracking_number.trim(), carrier: fields.carrier };
    dispatch({ type: "start", id });
    try { dispatch({ type: "resolved", id, query, data: await api.call("track_number", query) }); }
    catch (cause) { dispatch({ type: "failed", id, error: cause }); }
  };
  const change = (field) => (event) => dispatch({ type: "change", field, value: event.target.value });
  if (!open) return null;
  const data = result?.data;
  const native = data?.result;
  const effective = native?.carrier || data?.carrier;
  const carrierName = (carriers || []).find((c) => c.id === effective)?.name || effective || data?.carrier_name || "—";
  return <Section id="sec-tracking-lookup" title={t("tracking_lookup")} actions={<button type="button" className="btn btn-sm" onClick={onClose}>{t("tracking_lookup_close")}</button>}>
    <p className="help mb-3">{t("tracking_lookup_help")}</p>
    <form className="flex flex-wrap items-end gap-3 mb-4" onSubmit={submit}>
      <Field label={t("tracking_number")} className="min-w-0 flex-1"><input className="field mono" required minLength={6} maxLength={40} autoComplete="off" value={fields.tracking_number} onChange={change("tracking_number")} /></Field>
      <Field label={t("carrier")} className="min-w-0 flex-1"><select className="field" value={fields.carrier} onChange={change("carrier")}><option value="">{t("carrier_guess")}</option>{(carriers || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
      <button type="submit" className="btn btn-primary" disabled={loading || !fields.tracking_number.trim()}>{t(loading ? "tracking_lookup_loading" : "tracking_lookup_go")}</button>
    </form>
    <ErrorBox error={error} />
    {native && <div className="space-y-3" aria-live="polite" style={{ overflowWrap: "anywhere" }}>
      <div className="flex flex-wrap items-center gap-2" style={{ overflowWrap: "anywhere" }}><strong className="mono">{result.query.tracking_number}</strong><span>{carrierName}</span>{native.ok && native.found && <StatusPill status={native.status} />}</div>
      <p className="help">{t("tracking_lookup_sent_carrier")}: {result.query.carrier || t("carrier_guess")}</p>
      {!native.ok ? <div role="status" className="banner banner-info"><strong>{t(native.source === "none" ? "tracking_lookup_no_source" : "tracking_lookup_failed")}</strong>{native.error && <p style={{ overflowWrap: "anywhere" }}>{native.error}</p>}</div> : !native.found ? <p role="status">{t("tracking_lookup_not_found")}</p> : <>
        {native.status_text && <p>{native.status_text}</p>}
        <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[auto_1fr]">
          <dt className="help">{t("tracking_lookup_eta")}</dt><dd className="m-0">{native.eta_from ? windowLabel(native.eta_from, native.eta_to || native.eta_from, lang) : t("tracking_lookup_no_eta")}{native.eta_time ? ` · ${native.eta_time}` : ""}</dd>
          {native.service && <><dt className="help">{t("tracking_lookup_service")}</dt><dd className="m-0">{native.service}</dd></>}
        </dl>
      </>}
      <p className="help">{t("tracking_lookup_source")}: {native.source || "—"}</p>
      {data.url && <ExtLink href={data.url}>{t("open_tracking")}</ExtLink>}
      {native.ok && native.found && <div>
        <h3 className="mb-2">{t("timeline")}</h3>
        <p className="help mb-2">{t("tracking_lookup_events_help")}</p>
        {native.events?.length ? <ol className="m-0 space-y-3 pl-5">{native.events.map((event, index) => <li key={`${event.ts}-${index}`} style={{ overflowWrap: "anywhere" }}><div className="flex flex-wrap items-center gap-2"><StatusPill status={event.status} /><span className="help">{event.ts ? shortClock(event.ts, lang) : "—"}</span></div><p>{event.description}</p>{event.location && <p className="help">{event.location}</p>}</li>)}</ol> : <p className="help">{t("timeline_none")}</p>}
      </div>}
      {data.attempts?.length > 0 && <details><summary className="help">{t("tracking_lookup_attempts", { n: data.attempts.length })}</summary><ul className="help list-disc pl-5">{data.attempts.map((attempt, index) => <li key={index} style={{ overflowWrap: "anywhere" }}>{attempt.source} · {t(!attempt.ok ? "tracking_lookup_failed" : attempt.found ? "tracking_lookup_found" : "tracking_lookup_not_found")}{attempt.error ? ` · ${attempt.error}` : ""}</li>)}</ul></details>}
    </div>}
  </Section>;
}
