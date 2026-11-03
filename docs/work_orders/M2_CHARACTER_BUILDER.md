# M2 addition — complete, rules-validated character creation

This work order is specified, not implemented by the M1 draft workflow.

Before implementation, audit official rulebook/sheet creation steps and record
verified page anchors, required vs optional choices, dependencies and derived
resources. Resolve source/version gaps explicitly; no AI-invented options/stats.

Build a persistent, private, resumable multi-step Girl/Frame wizard with legal
options, back/edit support and stale revision checks. Keep private character facts
separate from public sheet fields. Validate choices before activation. Require
human review/confirmation, then commit a versioned playable sheet and creation
event atomically. Draft/invalid characters cannot enter gameplay as verified PCs.

Acceptance BUILDER-01 through BUILDER-04: every agreed creation branch has a
source/test map; illegal combinations and derived values rejected; resume/edit
does not reroll or reset choices; activated sheets are usable by the same engine
services and survive restart/rebuild. Independent rules review is required before
claiming complete official creation. Until then mark all these cases NOT_RUN.
