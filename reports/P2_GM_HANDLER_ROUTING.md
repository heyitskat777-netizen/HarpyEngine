# Discrete GM / scoped Handler synthetic routing

Owner requested implementation followed by another test, with GM access to all
game information and a separately scoped Handler. Implemented on top of source
`90d54e6f4aca15c5e7613626e84f96b5368af778`; source fingerprint follows below.

## Delivered behavior

Explicit own scene question → GM request with full canonical campaign state and
gameplay records → saved private GM reply → optional separate Handler request
with the original question and actual Handler-known references → saved private
Handler reply. Both routes use separate schemas/providers and independently
retryable keys. Handler input never includes the GM envelope or GM output.

The synthetic adapter answers known objective/scope/status questions from cited
sources, asks for clarification on unknowns, and returns a Play-workflow referral
for mechanics. Recognised Keep Your Head requests include `play_id=keep_your_head`.
The canonical engine remains responsible for executing any actual Play and choices.
The GM's broad input does not become public output. Direct handling invalidates an
old frozen observer batch and excludes only that exact source revision from
routine pending work. Edits re-enter review; other pending input is preserved.

The contract and UI requirements are consolidated in
[the engine handoff](../docs/P2_ENGINE_TRIAL_HANDOFF.md#discrete-gm-and-handler-conversation).

## Actual conversation test

Only 50 Pilot messages were scripted. Four background briefing references were
seeded first; no Handler or GM dialogue was prewritten. Five narrative settings
frame a single conversation: barracks, hallway, briefing, simulated cockpit and
barracks debrief. These labels do not change canonical locations or accept a
mission; this is not five separate 100-message scenes.

| Engine route | Replies | Sourced answers | Clarifications | Play referrals |
|---|---:|---:|---:|---:|
| GM | 50 | 32 | 11 | 7 |
| Handler | 40 | 27 | 11 | 2 |

Observed examples:

- Pilot asks the objective: Handler cites inspection of the relay site and
  reporting observed conditions.
- Pilot asks the authorised scope: Handler cites accessible areas only and
  that forced entry is not authorised.
- Pilot asks who funds the relay: Handler requests clarification; it invents no
  funding source.
- Pilot asks whether a mission is already accepted: Handler cites planning-only
  status; canonical mission state is unchanged.
- Pilot asks Handler to resolve a roll: Handler refers to GM/engine Play handling.
- Pilot asks GM for Keep Your Head and Heat expenditure: typed workflow referral,
  no dice roll or expenditure.

Every GM request contained a GM-only canonical canary. No Handler request contained
it or a Pilot-only reference; Handler requests have no canonical-state or gameplay-
record fields. Saved replies exposed no GM-only canary. Cross-owner reads reject.
Retries made no additional provider calls. Canonical state matched before/after,
dice calls were 0, external tokens were 0 and external cost was 0.

The repeatable command is `.venv/bin/python tools/run_director_trial.py`.
Readable output: `var/gm-handler-conversation.html`; structured output:
`var/gm-handler-conversation.json`. Both remain ignored synthetic artifacts.

## Validation and limits

- Final routing selection: `.venv/bin/pytest -q tests/test_director_conversation.py
  --junitxml=var/gm-handler-trial.xml`: **7 passed in 9.31s**. This includes the
  50-message conversation, privacy, stale source/context, pause/consent, request
  schema separation, route-key conflict, independent failure recovery and observer
  deduplication. Earlier integrated trial selection: **37 passed in 15.81s** before
  expanding the same conversation test from 7 to 50 messages.
- Ruff check/format passed on all 7 changed Python files; mypy passed on all 5
  changed source files. Runtime registry, original planning contracts, repository
  manifest/secret check and `git diff --check` passed; repository findings: 0.
- Remote focused CI includes this routing file alongside the existing selected
  dependencies. Its exact commit/outcome is reported in the delivery message.

These are deterministic source-lookup templates with bounded question categories,
not measured model intelligence, freeform Handler personality or complete GM
adjudication. A future model adapter cannot be dropped into this service: current
output validation deliberately accepts only the exact synthetic reply policy.
New reference topics are backward-compatible defaults; no migration, dependency,
runtime release or bot deployment is included. GM current-scene history/reference
contexts are limited to 100 entries and require reconciliation beyond that limit.
Live publication, automatic orders/mission acceptance, real-provider integration
and the Activity UI remain unfinished. No full regression or human acceptance is
claimed by these focused tests.

Source fingerprint (SHA-256 of sorted filename, NUL, file bytes, NUL for the
5 changed source files, routing test, trial runner and focused CI selection):
`791c18f0a8aaa9667463a1380eb4e245c95ffc954541e53296c359305a57877a`.
