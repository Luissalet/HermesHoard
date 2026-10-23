import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../context.js";
import { useContextProvider } from "./hooks.js";
import { Busy, ErrorBox, Field, Modal, useBusy } from "./ui.jsx";
import { localLabel, segCount, tripWhen } from "./travel.jsx";

export default function TripSplit({ trip, selected, open, onClose, onSeparated, onChanged }) {
  const { t, lang } = useApp();
  const [title, setTitle] = useState("");
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState(null);
  const [busy, run] = useBusy();
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  // Opening the action for a new selection starts another split; refreshing a completed request keeps its receipt.
  useEffect(() => {
    if (open && selected.length) { setReceipt(null); setError(null); }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  useContextProvider(() => ({ form: "trip_split", mode: "new", object_id: null, trip_id: trip.id,
    fields: { split_title: title, split_segments: selected.map((s) => s.id) } }), open && !receipt);
  const submit = (event) => {
    event.preventDefault();
    if (busy.split || receipt) return;
    const sent = { trip: trip.id, split_title: title, split_segments: selected.map((s) => s.id) };
    run("split", async () => {
      setError(null);
      try {
        const result = await api.call("trip_update", sent);
        if (!mounted.current) return;
        // Keep the native receipt even if refreshing the original later fails. Never resubmit a completed split.
        setReceipt({ ...result, sent_title: sent.split_title });
        onSeparated(sent.split_segments);
        await onChanged();
      } catch (failure) { if (mounted.current) setError(failure); }
    });
  };
  if (!open) return null;
  return <Modal title={receipt ? t("trip_split_done") : t("trip_split")} onClose={onClose} wide>
    {receipt ? <div className="space-y-3" role="status">
      <dl className="m-0 space-y-3">
        {[[t("trip_split_original"), receipt.original], [t("trip_split_new"), receipt.new]].map(([label, item]) => (
          <div key={item.id} className="min-w-0 space-y-1">
            <dt className="label">{label}</dt>
            <dd className="m-0 break-words font-semibold">{item.title}</dd>
            <dd className="help m-0 break-all">{item.id}</dd>
            <dd className="help m-0">{tripWhen(item, lang) || "—"} · {segCount(t, item.segments)} · {item.currency}</dd>
          </div>
        ))}
      </dl>
      <p className="help">{t("trip_split_expenses")}</p>
      {title !== receipt.sent_title && <p className="help break-words">{t("trip_split_later_title", { title })}</p>}
      <ErrorBox error={error} />
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className="btn" onClick={onClose}>{t("trip_split_close")}</button>
        <a className="btn btn-primary" href={`#/viaje/${encodeURIComponent(receipt.new.id)}`}>{t("trip_split_open")}</a>
      </div>
    </div> : <form className="space-y-3" onSubmit={submit}>
      <p className="help break-words">{t("trip_split_original")}: {trip.title}<br /><span className="break-all">{trip.id}</span></p>
      <ul className="m-0 list-none space-y-2 p-0" aria-label={t("trip_split_selected")}>
        {selected.map((s) => <li key={s.id} className="min-w-0">
          <div className="break-words">{s.label}</div>
          <div className="help break-all">{s.id}</div>
          <div className="help">{localLabel(s.dep_local, lang) || "—"}</div>
        </li>)}
      </ul>
      <Field label={t("trip_split_name")} hint={t("trip_split_name_hint")}>
        <input className="field" maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} />
      </Field>
      <p className="help">{t("trip_split_moves")}</p>
      <p className="help">{t("trip_split_expenses")}</p>
      <ErrorBox error={error} />
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className="btn" onClick={onClose}>{t("cancel")}</button>
        <Busy type="submit" className="btn btn-primary" busy={busy.split} disabled={!selected.length}>{t("trip_split_submit")}</Busy>
      </div>
    </form>}
  </Modal>;
}
