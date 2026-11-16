# P2-D2/D3 source context and synthetic shadow checkpoint

Base: 6b52fac22a160ea5d94ea0e1995b1a0d2fc3313d. Clean existing development
checkout preserved. Owner authorizes continued engine-first work, defers Activity
integration, tentatively prefers GPT-6.1 Terra and explicitly prohibits spending.
No provider was installed/called and no tokens/costs are simulated as real usage.

Implemented: append-only source references and explicit local chronology/dependencies;
separate GM and current actor knowledge; source correction/disclosure reconciliation;
strict five-way shadow decisions; out-of-transaction deterministic provider;
bounded invalid-output retry; atomic outcome/frontier acknowledgement; failure and
stale recovery; private durable GM review/reopen with no application/publication.
Migration0023 adds two tables in the existing store. Existing D1 acknowledgement
was extracted into a shared transaction seam rather than copying its authority
checks. No live database was migrated.

Synthetic trial command: `.venv/bin/python tools/run_director_trial.py`.
Latest recorded run: 28 passed in 9.48s, zero failures/errors/skips; focused only.
This includes D1/database dependencies. Early test attempts had nine fixture-setup
errors because an imported fixture's dependency was not imported; corrected without
weakening assertions. Later runs verify source/privacy/role isolation, dependency
ordering, source reconciliation, all five review-only outcomes, bounded repair,
outage sanitization, saved-outcome replay, stale inference and atomic rollback.
Applicable Ruff/format/mypy, registry/planning and repository checks are run at
this handoff. Remote CI is separate evidence; no full regression or human trial.

[Engine trial and deferred UI contract](../docs/P2_ENGINE_TRIAL_HANDOFF.md) records
exact methods, current scope and remaining gates. This is a synthetic shadow
candidate, not autonomous-live readiness. NPC presence/knowledge consumers,
authorized NPC/world/Play effects, delivery, retention/redaction, broader source
coverage and human fairness/pacing still need work. Source sequence is not a
complete fictional clock or cross-scene causality engine. These engine gaps remain
visible; deferred UI integration is not used as their blocker.

No real capture, paid inference, deployment, worker startup, bot restart, live
migration, environment publication or private recovered-engine mutation occurred.
