import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../context.js";
import { ErrorBox, Field, Section } from "./ui.jsx";
import { dayLabel } from "../format.js";

export default function ShipmentCalendar({ onClose }) {
  const { t, lang } = useApp();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  useEffect(() => {
    let live = true;
    api.call("shipments_ics").then((out) => {
      if (live) { setResult(out); setFrom(out.date_from); setTo(out.date_to); }
    }).catch((cause) => { if (live) setError(cause); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, []);
  const refresh = async (event) => {
    event.preventDefault(); setLoading(true); setError(null);
    try { setResult(await api.call("shipments_ics", { date_from: from || undefined, date_to: to || undefined })); }
    catch (cause) { setError(cause); }
    finally { setLoading(false); }
  };
  const change = (setter) => (event) => { setter(event.target.value); setResult(null); };
  return <Section title={t("shipment_calendar")} actions={<button type="button" className="btn btn-sm" onClick={onClose}>{t("shipment_calendar_close")}</button>}>
    <p className="help mb-3">{t("shipment_calendar_help")}</p>
    <form onSubmit={refresh} className="flex flex-wrap items-end gap-3 mb-4">
      <Field label={t("shipment_calendar_from")}><input type="date" className="field" required value={from} onChange={change(setFrom)} /></Field>
      <Field label={t("shipment_calendar_to")}><input type="date" className="field" required value={to} min={from || undefined} onChange={change(setTo)} /></Field>
      <button type="submit" className="btn" disabled={loading}>{loading ? t("shipment_calendar_loading") : t("shipment_calendar_show")}</button>
      {result && !loading && <a className="btn btn-primary" href={result.download_url} download="hermes-deliveries.ics">{t("shipment_calendar_download")}</a>}
    </form>
    {error && <ErrorBox error={error} />}
    {result && <>
      <p className="help mb-3">{t("shipment_calendar_count", {n:result.count,undated:result.undated,outside:result.outside_range})}</p>
      {result.at_selection_limit && <p className="help mb-3">{t("shipment_calendar_limit")}</p>}
      {result.events.length ? <div className="overflow-x-auto"><table className="table"><thead><tr><th>{t("shipment_calendar_date")}</th><th>{t("shipment_calendar_event")}</th><th>{t("shipment_calendar_kind")}</th></tr></thead><tbody>
        {result.events.map((event) => <tr key={event.uid}><td className="whitespace-nowrap">{dayLabel(event.start, lang)}</td><td><a href={event.url}>{event.title}</a>{event.location && <p className="help">{event.location}</p>}</td><td>{t(event.kind === "pickup_deadline" ? "shipment_calendar_deadline" : "shipment_calendar_estimated")}</td></tr>)}
      </tbody></table></div> : <p className="help">{t("shipment_calendar_empty")}</p>}
      <p className="help mt-3">{t("shipment_calendar_snapshot")}</p>
    </>}
  </Section>;
}
