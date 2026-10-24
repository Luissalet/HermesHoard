# Individual event reading

Mode: Operate. Narrow refinement of the inherited Products interface.

Add one native action to the existing event card and history row: mark this ID seen, keeping other events unread. Preserve card/table composition, existing buttons, local fonts and family styling. Read state uses the incumbent Chip; pending state uses Busy. No new confirmation, modal or visual world.

ES/EN action names and event-specific accessible name. Seen is a stored flag, not a reading timestamp or dismissal. On failure the same action can be retried; a late completion never replaces another event's local UI. Shared counters reload native data. Mobile buttons wrap/stack in existing containers, history retains its table scroller.

Verification: bounded desktop/mobile screenshots and real offline interaction, native API/stdio115, a material React pending-identity/error test, area tests once and normal build. No model/scheduler/source activity. DESIGN sidecar drift is inherited and outside this task.
