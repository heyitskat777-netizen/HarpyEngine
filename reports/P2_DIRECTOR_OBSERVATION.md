# P2-D1 — synthetic Activity observation and durable batches

Checkpoint base: `15565352217b2b0e916158412c13593a007005bc`, existing
`codex/r285-integration-20261114` checkout. Initial status was clean; target-branch
fetch found no newer commits. No worktree, reset, history rewrite or live action.

## Completed workflow and adopted recommendations

An authorized synthetic scene participant explicitly submits IC text → persisted
source revision → quiet/size/age eligibility → one token-bound frozen claim →
synthetic review acknowledgement → fresh-service status. A real supported native
Keep Your Head action supplies an independently verified completed-Play trigger.

- Existing campaign store and original immutable scene/bind identity are reused.
  Additive migration `0022` adds `director_scene_state`, `director_inputs` and
  `director_runs`; no transcript or gameplay backfill. Only disposable synthetic
  databases were migrated. Existing populated `0021` rows are preserved.
- Default service is Off. Explicit `synthetic=True` local harness setup supports
  off/shadow policy only. Configured administrator membership/scene participation
  does not grant anyone else's consent. Every participant grants or withdraws
  their own policy-bound consent; current consent/membership is rechecked.
- Explicit Pilot/Handler input uses actual character incarnation, controller and
  applicable casting. IC input respects scene chat locks. OOC text is ignored and
  not retained. There is no AI/system-output ingest path or passive Discord scan.
- Inputs are bounded to 1,000 characters. Claims contain up to 20 latest source
  revisions plus three recent references, retaining original audiences. Oversized
  unread input is split without advancing past unseen input. Changed-audience
  history is blocked for privacy review, not silently widened or discarded.
- Default pacing is 120-second quiet/minimum routine interval, 20-message size
  threshold and oldest age 10 minutes. Duplicate source deliveries do not move
  quiet time. Own IC edits append revisions and invalidate affected claims while
  still counting as one current message. Plain ticks on reviewed scenes do nothing.
- Short claim/acknowledgement transactions prepare a future external inference
  boundary. Leases last 120 seconds. Frozen server metadata carries scene, policy,
  consent and canonical revisions, original bind event, source frontier and a guard
  over input, membership, safety history, policy, actions, choices, locks and work.
  Failure/expiry leaves unread input recoverable; concurrent claims yield one run.
- Keep source verification requires an actual `m2.choice_resolved` event, canonical
  history and the matching original receipt/actor/audience. Pending choices, all
  child families and unresolved scene work block it. No reroll or private Handler
  response enters the batch. The trusted source adapter is explicitly invoked;
  no background source listener/worker is installed or started.

This is source/reference batching, not fictional knowledge or canonical truth.
Synthetic acknowledgement is not an AI `WAIT` decision. Every batch/completion
blocks publication. The delivered summary v1 contracts/service remain unchanged.
See the [updated Activity handoff](../integrations/ai_assistance/INTEGRATION_HANDOFF.md)
for exact methods, wire models, internal token boundaries and unsupported paths.

## Exact local verification

Final runtime/test/CI-selection snapshot SHA-256:
`1144c9c52fc56d07b9716afc5aaa48244784c0b3b4e4c5e827689ea68e84f6db`.
Ignored `var/p2-director-source-snapshot.json` contains individual hashes. Reproduce
by mapping SHA-256 for `.github/ci-tests.txt`, migration `0022`,
`ai/observation.py`, `services/director_observation.py`,
`database/{director_schema,tables}.py` and
`tests/{test_director_observation,test_database}.py`; hash their sorted-key JSON
with separators `(',', ':')`. Reports/docs are excluded. No runtime/test edits
followed this passing snapshot. The publishing commit identifies the whole change.

`bash tools/install.sh` passed with pinned dependencies and unchanged `uv.lock`.

```text
.venv/bin/pytest -q tests/test_director_observation.py tests/test_database.py tests/test_ai_assistance.py --junitxml=var/p2-director-observation.xml
24 passed in 7.00s; zero failures/errors/skips. Focused, not full regression.
```

The selection covers twelve D1 cases, two database cases and ten existing summary
workflow cases. Evidence includes quiet deadline/replay; size/age during active
conversation; contiguous splitting/tail bounds; consent/role/guild denials; owned
edits/injection-field rejection; failed/expired/stale claims; concurrent claims;
pause→resume invalidation; actual native Keep and pending human/required-work
rejection; chat lock enforcement; staging rollback; immutable observations;
membership/policy/close/rebind invalidation; restart/reopen; fresh/populated
migration preservation, metadata parity and refused destructive downgrade.
Observer operations leave existing canonical/gameplay/delivery records unchanged.

```text
.venv/bin/ruff check src/girlframe/ai/observation.py src/girlframe/services/director_observation.py src/girlframe/database/director_schema.py src/girlframe/database/tables.py migrations/versions/0022_director_observation.py tests/test_director_observation.py tests/test_database.py
All checks passed.
.venv/bin/ruff format --check <same paths>
7 files already formatted.
.venv/bin/mypy src/girlframe/ai/observation.py src/girlframe/services/director_observation.py src/girlframe/database/director_schema.py src/girlframe/database/tables.py
Success: no issues found in 4 source files.
```

`tools/check_rules_registry.py` passed with unchanged RULES_SUBSET/review counts.
Original `verification/verify_handoff.py` passed: 34 files, 86 planned cases,
four schemas/four synthetic fixtures; planning evidence only.
`tools/check_repository.py` passed before this report: 2,077 publishable files,
40 manifest entries, zero findings. A final repository/link/diff check includes
this report. The CI focused selection adds the D1 tests to existing coverage;
remote CI is separate evidence. No full suite or human acceptance was run.

## Remaining scope and next action

Actual Activity backend/session/frontend details remain unavailable. D1 registers
no HTTP route, message timeline, realtime connection or worker lifecycle. Real
transcript capture, retention/deletion/redaction rollout, audience reconciliation,
other Play/child families, fictional knowledge/disclosure/chronology, five-way
Director decisions, model transport, spending policy and autonomous delivery are
unsupported. The native adapter conservatively blocks any unresolved same-scene
required work; it does not claim a general source-completion algorithm.

No real player data, paid calls, live database migration, bot restart, deployment,
environment publication or recovered-engine mutation occurred. This is an
unreleased development checkpoint, not a runtime release; frozen live v0.1.4 and
its unknown current process status remain unchanged. P1 human acceptance and
broader rules/privacy/Director-pacing review remain open.

Next: freeze a bounded source-aware fictional knowledge/chronology and synthetic
shadow-context workflow before adding model decisions. The Activity task can
reconcile its real backend/authentication against the handoff independently.
