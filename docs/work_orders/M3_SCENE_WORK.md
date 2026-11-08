# M3B/G/H — actual scene and campaign work contexts

Status: IMPLEMENTED_SUBSET / automated checks passed; human/independent review pending. Required consequences can arise in a standalone bound scene,
not only a mission or Off-Duty period. Examples include combat, surgery, physical
control and career changes. Preserve a real source context without inventing a
mission, recovery period, actor response or fictional movement to hold the work.

Add an immutable index of actual scene identities and their original bind events.
The operational channel row can be rebound to a different scene; historical work
must retain its original identity. Backfill only actual event/outcome evidence,
without manufacturing unknown historical scenes. Bind new context records in the
same transaction as actual scene creation. This records OOC scene identity, not
physical character presence or travel.

Generalize required work to exactly one real mission, Off-Duty, scene or explicit
campaign context, with campaign-scoped event/parent verification. Preserve all
existing histories and append-only protections in a versioned migration. Reject
wrong campaign/source, nonexistent contexts, multiple parents and accidental
unscoped work. A scene rebind must not move a pending decision to the new scene.
Keep known rolled decisions recoverable and prevent closing their actual scene.

This creates no generic work resolver or waiver. Every future consequence still
needs its actual typed reducer, real human owners and source-specific resolver.
Initial physical facts, travel, custody, medical help, Frame control, an AM's
physical vessel and a replacement character are distinct events. A character ID
does not change merely because an AM changes vessels or a Girl changes Frame.

Acceptance: fresh and populated upgrades, exact old-row preservation, historical
scene indices after close/rebind, same-campaign source proof, invalid/no/multiple
contexts, immutable history, refusal to discard unrepresentable scoped work on
downgrade, paused OOC administration, known-roll recovery and unchanged live bot.
No migration/deployment/publication of the live environment is part of this work.
