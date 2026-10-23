import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../context.js";
import { useContextProvider } from "./hooks.js";
import { Busy, ErrorBox, Field, Section } from "./ui.jsx";

const FIELDS = ["tracking_number", "carrier", "tracking_url", "order_ref", "sub_ref", "item", "merchant_url"];
const title = (s) => s.label || s.item || s.tracking_number || s.id;

export default function ShipmentMerge({ shipment, onChanged, current }) {
  const { t, confirm, refreshDash } = useApp();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [selected, setSelected] = useState("");
  const [drop, setDrop] = useState(null);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState(null);
  const [merging, setMerging] = useState(false);
  const [mergeError, setMergeError] = useState(null);
  const [message, setMessage] = useState("");
  const searchSeq = useRef(0), detailSeq = useRef(0), mounted = useRef(true);
  const latest = useRef({ selected, query });
  latest.current = { selected, query };
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; searchSeq.current++; detailSeq.current++; }; }, []);
  useContextProvider(() => ({ form: "shipment_merge", mode: "edit", kind: "shipment", object_id: shipment.id,
    title: title(shipment), fields: { keep: shipment.id, drop: selected, query }, changed: {} }), open && current);

  const search = async () => {
    const seq = ++searchSeq.current;
    setSearching(true); setSearchError(null);
    try {
      const result = await api.call("shipments_list", { filter: "all", text: query.trim(), limit: 50 });
      if (seq === searchSeq.current) setRows(result.shipments.filter((row) => row.id !== shipment.id));
    } catch (error) { if (seq === searchSeq.current) setSearchError(error); }
    finally { if (seq === searchSeq.current) setSearching(false); }
  };
  const choose = async (id) => {
    const seq = ++detailSeq.current;
    setSelected(id); setDrop(null); setReadError(null); setMergeError(null); setMessage(""); setReading(true);
    try {
      const result = await api.shipment(id);
      if (seq === detailSeq.current) setDrop(result.shipment);
    } catch (error) { if (seq === detailSeq.current) setReadError(error); }
    finally { if (seq === detailSeq.current) setReading(false); }
  };
  const merge = async () => {
    const picked = drop;
    const ok = await confirm({ title: t("shipment_merge"),
      message: t("shipment_merge_confirm", { keep: `${title(shipment)} (${shipment.id})`, drop: `${title(picked)} (${picked.id})` }),
      confirmLabel: t("shipment_merge_go") });
    if (!ok || !mounted.current || !current) return;
    setMerging(true); setMergeError(null);
    try {
      await api.call("shipment_merge", { keep: shipment.id, drop: picked.id, confirm: true });
      if (!mounted.current) return;
      setMessage(t("shipment_merge_done", { name: title(picked), id: picked.id }));
      setRows((items) => items?.filter((row) => row.id !== picked.id) ?? null);
      if (latest.current.selected === picked.id) { detailSeq.current++; setSelected(""); setDrop(null); setReading(false); }
      await refreshDash(); await onChanged();
    } catch (error) { if (mounted.current) setMergeError({ message: `${t("shipment_merge_failed", { id: picked.id })} ${error.message}`, hint: error.hint }); }
    finally { if (mounted.current) setMerging(false); }
  };
  if (!current) return null;
  return (
    <div>
      <button type="button" className="btn btn-sm" aria-expanded={open} aria-controls="shipment-merge-panel"
        onClick={() => { setOpen(!open); if (!open && rows === null) void search(); }}>
        {t(open ? "shipment_merge_close" : "shipment_merge")}
      </button>
      {open && <div id="shipment-merge-panel" className="mt-4">
        <Section title={t("shipment_merge")}>
          <div className="panel space-y-4">
            <p className="help m-0">{t("shipment_merge_help")}</p>
            <div style={{ overflowWrap: "anywhere" }}>
              <h3>{t("shipment_merge_keep")}</h3>
              <p className="m-0">{title(shipment)}</p>
              <p className="help m-0">{shipment.id} · {shipment.tracking_number || "—"} · {shipment.carrier || "—"}</p>
            </div>
            <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); void search(); }}>
              <Field label={t("shipment_merge_search")} className="min-w-0 flex-1">
                <input className="field" value={query} maxLength={80} onChange={(event) => {
                  setQuery(event.target.value); searchSeq.current++; setRows(null); setSearching(false); setSearchError(null);
                }} />
              </Field>
              <Busy type="submit" className="btn" busy={searching}>{t("search")}</Busy>
            </form>
            <ErrorBox error={searchError} />
            {searchError && <button type="button" className="btn btn-sm" onClick={search}>{t("shipment_merge_retry_search")}</button>}
            {searching && <p className="help" role="status">{t("shipment_merge_searching")}</p>}
            {rows !== null && <fieldset className="m-0 min-w-0 border-0 p-0 space-y-2">
              <legend className="font-semibold mb-2">{t("shipment_merge_pick")}</legend>
              <p className="help m-0">{t("shipment_merge_results", { n: rows.length })}</p>
              {rows.length === 0 && <p className="help">{t("shipment_merge_empty")}</p>}
              {rows.map((row) => <label key={row.id} className="flex items-start gap-2 cursor-pointer" style={{ overflowWrap: "anywhere" }}>
                <input type="radio" name="merge-shipment" checked={selected === row.id} onChange={() => { void choose(row.id); }} />
                <span className="min-w-0"><span className="block">{title(row)}</span><span className="help">{row.id} · {row.tracking_number || "—"} · {row.carrier || "—"}</span></span>
              </label>)}
            </fieldset>}
            {selected && <div className="space-y-3">
              <h3>{t("shipment_merge_drop")}</h3>
              <p className="help" style={{ overflowWrap: "anywhere" }}>{selected}</p>
              {reading && <p className="help" role="status">{t("shipment_merge_reading")}</p>}
              <ErrorBox error={readError} />
              {readError && <button type="button" className="btn btn-sm" onClick={() => choose(selected)}>{t("shipment_merge_retry_read")}</button>}
              {drop && <>
                <p style={{ overflowWrap: "anywhere" }}>{title(drop)}</p>
                <p className="help">{t("shipment_merge_fields")}</p>
                <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={t("shipment_merge_fields")}>
                  <table style={{ minWidth: 540 }}>
                    <thead><tr><th>{t("shipment_merge_field")}</th><th>{t("shipment_merge_keep_value")}</th><th>{t("shipment_merge_drop_value")}</th><th>{t("shipment_merge_result")}</th></tr></thead>
                    <tbody>{FIELDS.map((key) => <tr key={key}>
                      <th scope="row">{t(`shipment_merge_${key}`)}</th>
                      <td style={{ overflowWrap: "anywhere", maxWidth: 200 }}>{shipment[key] || "—"}</td>
                      <td style={{ overflowWrap: "anywhere", maxWidth: 200 }}>{drop[key] || "—"}</td>
                      <td className="help">{t(!shipment[key] && drop[key] ? "shipment_merge_fill" : "shipment_merge_preserve")}</td>
                    </tr>)}</tbody>
                  </table>
                </div>
                <p className="help">{t("shipment_merge_effects")}</p>
                <Busy className="btn btn-danger" busy={merging} onClick={merge}>{t("shipment_merge_go")}</Busy>
              </>}
            </div>}
            <ErrorBox error={mergeError} />
            {message && <p role="status" style={{ overflowWrap: "anywhere" }}>{message}</p>}
          </div>
        </Section>
      </div>}
    </div>
  );
}
