import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../context.js";
import { useContextProvider, useRebasedDraft } from "./hooks.js";
import { Busy, ErrorBox, Field, useBusy } from "./ui.jsx";

export default function PersonNameEditor({ person, tripId, tripTitle, onChanged }) {
  const { t, notify } = useApp();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState(null);
  const [busy, run] = useBusy();
  const form = useRebasedDraft({ name: person.name });
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useContextProvider(() => ({ form: "trip_person_name", mode: "edit", kind: "trip", object_id: tripId,
    title: tripTitle, person_id: person.id, fields: form.draft, changed: form.changed }), open);
  const save = (event) => {
    event.preventDefault();
    const sent = { name: form.draft.name };
    run("save", async () => {
      setError(null);
      try {
        const result = await api.call("trip_people", { trip: tripId, rename: { [person.id]: sent.name } });
        if (!mounted.current) return;
        const savedName = result.people.find((item) => item.id === person.id).name;
        // Accept native whitespace normalization only if no later edit replaced the submitted text.
        if (form.current().name === sent.name) form.set("name", savedName);
        await onChanged();
        if (!mounted.current) return;
        notify(t("exp_person_renamed"));
        if (form.saved({ name: savedName })) setOpen(false);
      } catch (failure) { if (mounted.current) setError(failure); }
    });
  };
  return <div className="min-w-0 max-w-full">
    <button type="button" className="btn btn-sm" aria-expanded={open}
      aria-label={`${t("exp_person_rename")}: ${person.name} (${person.id})`} onClick={() => setOpen(!open)}>{t("exp_person_rename")}</button>
    {open && <form className="mt-2 space-y-2" onSubmit={save} aria-label={t("exp_person_rename")}>
      <p className="help break-words">{tripTitle} · {tripId}<br />{person.name} · {person.id}</p>
      <p className="help">{t("exp_person_rename_help")}</p>
      <Field label={t("exp_person_new_name")}><input className="field" required maxLength={40} value={form.draft.name}
        onChange={(event) => form.set("name", event.target.value)} /></Field>
      <ErrorBox error={error} />
      <div className="flex flex-wrap gap-2">
        <Busy type="submit" className="btn btn-sm btn-primary" busy={busy.save} disabled={!form.draft.name.trim() || !("name" in form.changed)}>{t("save")}</Busy>
        <button type="button" className="btn btn-sm" onClick={() => setOpen(false)}>{t("cancel")}</button>
      </div>
    </form>}
  </div>;
}
