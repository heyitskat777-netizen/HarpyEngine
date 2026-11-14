# Private original-actor review control

Adds a current-facilitator-only "Check original Pilot identity (no freeze)" action
to the existing private shelving request view. Confirmation invokes the v30 review
preflight anew with the saved request revision and the current interaction's
principal. Revoked facilitator access, promoted/withdrawn requests and replaced
actors fail through the original preflight. No saved successful result grants
future authority. Player views retain only their own withdrawal control.

The result identifies the exact request and distinguishes a player request from a
GM proposal. It says the result applies to this read only, the request is pending,
and no player is frozen. It does not render actor incarnation, profile/snapshot
proof, configuration event or private sheet information. Responses stay ephemeral
with mentions disabled. Existing decline/withdrawal behavior remains unchanged.

No gameplay or journal mutation, persisted verification state, availability
phase/generation, freeze, parking, worker permit/drain, dispatcher or activation
was added. A future availability mutation still requires reauthorization in its
own source transaction plus all canonical, shared-resource and remote-effect gates.
Handler/NPC authority remains unsupported by the Pilot preflight.

## Integration and checks

Isolated candidate: harpyengine-p1-shelving-review-ui-20261110. The initial copy's
four preflight hashes match the packaged v30 manifest. The separate six-file
required Processor incremental patch was applied only after all its input hashes
matched, and all output hashes were checked. This reconciles those independent
layers locally; no unrelated full regression is claimed.

Changed Python: discord_adapter/p1_shelving.py and new test_shelving_review_ui.py.
Worker Ruff lint/format passes. Worker did not run pytest. Root minimum:

    PYTHONPATH=src /workspace/scratch/1003c11eb181/harpyengine-p1-adapter-20261109/.venv/bin/python -m pytest -q tests/rules/test_shelving_review_ui.py::test_native_actor_review_rechecks_current_request_and_facilitator_without_writes

The authored native journey verifies private no-write review of a GM proposal,
no proof leakage, explicit player promotion, stale controls, facilitator revocation
and new reviewer success, retained pending intake, and zero dice calls. The v30
service's real-replacement test remains the source-identity coverage; it is not
rerun or claimed passed on this later snapshot. Independent review, live Discord,
player acceptance and final exact-candidate global gates remain pending. Bot OFF.
