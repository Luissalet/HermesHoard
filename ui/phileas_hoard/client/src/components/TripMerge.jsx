import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../context.js";
import { useContextProvider } from "./hooks.js";
import { Busy, ErrorBox, Field, Modal } from "./ui.jsx";
import { segCount } from "./travel.jsx";

function TripFacts({ item, label, t }) {
  return <div className="min-w-0 space-y-1">
    <dt className="label">{label}</dt>
    <dd className="m-0 break-words font-semibold">{item.title || "—"}</dd>
    <dd className="help m-0 break-all">{item.id}</dd>
    <dd className="help m-0 break-words">{item.destination_label || item.destination || "—"}</dd>
    <dd className="help m-0">{item.start_date || "—"} – {item.end_date || "—"}</dd>
    <dd className="help m-0">{item.segments == null ? "—" : segCount(t, item.segments)} · {item.expenses == null ? "—" : t(item.expenses === 1 ? "trip_merge_expense_1" : "trip_merge_expense_n", { n: item.expenses })} · {item.currency || "—"}</dd>
  </div>;
}

export default function TripMerge({ trip, others, onClose, onSaved }) {
  const { t, confirm } = useApp();
  const [other, setOther] = useState(others[0]?.id || "");
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  const pending = useRef(false);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const close = useCallback(() => closeRef.current(), []);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const selected = others.find((item) => item.id === other);
  useContextProvider(() => ({ form: "trip_merge", mode: receipt ? "receipt" : "edit", kind: "trip",
    object_id: trip.id, title: trip.title, fields: { merge_from: receipt?.from.id || other },
    ...(receipt ? { result: { trip: receipt.trip, incorporated_trip_id_from_request: receipt.from.id } } : {}),
  }));

  const submit = async (event) => {
    event.preventDefault();
    if (pending.current || receipt || !selected) return;
    const sent = { trip: trip.id, merge_from: selected.id, confirm: true };
    const from = { id: selected.id, title: selected.title };
    pending.current = true;
    setBusy(true); setError(null);
    try {
      const ok = await confirm({ title: t("trip_merge"), message: t("trip_merge_review_confirm", { name: from.title, id: from.id, keep: trip.id }), confirmLabel: t("trip_merge_go"), danger: false });
      if (!ok || !mounted.current) return;
      const result = await api.call("trip_update", sent);
      if (!mounted.current) return;
      // The native receipt survives a failed reload; a completed merge is never submitted again here.
      const { id, title, destination, destination_label, start_date, end_date, segments, expenses, currency } = result.trip;
      setReceipt({ trip: { id, title, destination, destination_label, start_date, end_date, segments, expenses, currency }, from });
      await onSaved(from.id);
    } catch (failure) { if (mounted.current) setError(failure); }
    finally { if (mounted.current) { pending.current = false; setBusy(false); } }
  };

  return <Modal title={receipt ? t("trip_merge_receipt") : t("trip_merge")} onClose={close} wide>
    {receipt ? <div className="space-y-3">
      <div role="status"><dl className="m-0"><TripFacts item={receipt.trip} label={t("trip_merge_kept_result")} t={t} /></dl></div>
      <p className="help break-words">{t("trip_merge_incorporated_request")}: {receipt.from.title}<br /><span className="break-all">{receipt.from.id}</span></p>
      <p className="help">{t("trip_merge_notes_pending")}</p>
      <ErrorBox error={error} />
      <div className="flex justify-end"><button type="button" className="btn" onClick={close}>{t("trip_merge_close")}</button></div>
    </div> : <form className="space-y-3" onSubmit={submit}>
      <Field label={t("trip_merge_pick")}>
        <select className="field" value={other} disabled={busy} onChange={(event) => setOther(event.target.value)}>
          {others.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.start_date || "—"} – {item.end_date || "—"} · {item.id}</option>)}
        </select>
      </Field>
      <dl className="m-0 grid gap-4 md:grid-cols-2">
        <TripFacts item={trip} label={t("trip_merge_keep_role")} t={t} />
        {selected && <TripFacts item={selected} label={t("trip_merge_drop_role")} t={t} />}
      </dl>
      <p className="help">{t("trip_merge_native_effect")}</p>
      <p className="help">{t("trip_merge_currency_scope")}</p>
      <ErrorBox error={error} />
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className="btn" onClick={close}>{t("cancel")}</button>
        <Busy type="submit" className="btn btn-primary" busy={busy} disabled={!selected}>{t("trip_merge_go")}</Busy>
      </div>
    </form>}
  </Modal>;
}
