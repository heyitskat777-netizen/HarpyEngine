# Guarded private shelving request source

Extends v39 guarded intake on the explicitly combined v40 managed-savepoint layer.
Actual self-request, configured-GM proposal, and subsequent explicit player request
now authorize and plan inside the guarded immediate transaction. Current membership,
facilitator configuration and original actor proof are resolved again before replay.
GM proposal is never player consent. Original proposal provenance is retained.

The exact planned event, campaign revision and receipt must match captured writes.
An existing pending request under a new key writes only its exact receipt; same-key
replay writes nothing. Hidden member/actor/choice/outbox effects reject atomically.
Committed-cleanup and uncertain-commit classifications retain the existing non-retry
instructions. No new error messages contain private actor or proof metadata.

Canonical storage and authenticated adapters remain trusted. This does not certify
historic event authenticity, create an availability generation, park shared work,
authorize gameplay dispatch or activate shelving. Activation remains fail closed.
No migration changes. Full regression, privacy/restore gates and end-to-end gameplay
freeze remain pending. Worker authored tests but did not run pytest; root owns checks.
