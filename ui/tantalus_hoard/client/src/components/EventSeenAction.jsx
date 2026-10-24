import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../context.js";
import { Busy, Chip } from "./ui.jsx";

// Reading one event never invokes the native no-ID action that marks a whole visit.
export function EventSeenAction({ event, onChanged }) {
  const { t, notify, toastError, refreshDash } = useApp();
  const [busy, setBusy] = useState(false);
  const current = useRef(event.id);
  current.current = event.id;
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    setBusy(false);
    return () => { mounted.current = false; };
  }, [event.id]);
  const mark = async () => {
    const id = event.id;
    setBusy(true);
    try {
      await api.call("events_mark_seen", { event_ids: [id] });
      // The shared counter follows stored data even if this row has left the view.
      refreshDash();
      if (!mounted.current || current.current !== id) return;
      notify(t("event_seen_saved"));
      onChanged?.();
    } catch (error) {
      if (mounted.current && current.current === id) toastError(error);
    } finally {
      if (mounted.current && current.current === id) setBusy(false);
    }
  };
  return event.seen ? <Chip>{t("event_seen")}</Chip> : (
    <Busy className="btn btn-sm" busy={busy} onClick={mark} aria-label={`${t("event_mark_seen")}: ${event.title}`} title={t("event_mark_seen_hint")}>
      {t("event_mark_seen")}
    </Busy>
  );
}
