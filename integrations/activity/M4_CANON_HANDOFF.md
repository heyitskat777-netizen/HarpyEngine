# M4 Activity canon

The engine port starts at `44dd10c` and incorporates the new code from
`HarpyEngine-M4-activity-canon.zip`, including the Activity-only intake at
`c36b9ee`. The five earlier time, Session Zero, and difficulty patches are
already in the development history. The package's earlier test results apply
to its own revisions.

## Activity wiring

Use the existing authenticated `P2Scene.read` and `P2Scene.write` dispatch
with the campaign-bound `GuildViewer` resolved by the server. Copy the updated
`p2_scene.py`, `p2-desk.js`, and `mission_desk.py` as part of the Activity overlay.
Apply [the mission UI patch](m4_canon_mission_ui.patch) to the Activity source
after the campaign difficulty overlay. The deployed Activity must mount the
scene desk and its authenticated scene routes to expose the controls.

Set `BotPolicy.canon_facilitator_id` in the trusted campaign configuration to
an active member whose account is distinct from the campaign Handler. This
enables the manual canon desk. Use a fresh scene window and a stable submission
UUID for each explicit `canon-submit` action. Exact command retries reuse the
receipt. The facilitator works from the saved proposal and chooses private
approval, publication, or decline. Published references remain separate from
what characters have witnessed or learned.

Witness and report controls use the actual scene cast, character incarnation,
and appointment. The Handler can save a draft from their current known canon
and attach it to a native mission offer. The private mission view shows only
briefing text the viewer's actual character learned. Corrected sources flag an
undispatched offer for cancellation and reissue. The calendar exposes a
scheduled location and reviewed requirements, and safety pauses follow the
native scene binding. The draft, delivery, and Play paths check that pause.

## Handler consent and delivery

An Activity shadow packet can include canon after the actual Pilot witnesses
the established fact and explicitly reports it to the actual Handler. The
source, witness, report, and dependent facts must retain their approved
Activity observation consent generation. Withdrawing consent or correcting a
source can remove it from future packets and invalidate reviewed deliveries.
The manual ledger preserves the authorized history.

A report from another scene becomes private Handler background after approved
native closeout. It cannot be cited as evidence for speech in the new scene.
Local canon citations are eligible for reviewed delivery to Pilots with a
current witness record in that scene. The existing engine response decision,
review, exact recipient checks, and rule authority still apply.

## Offline check

```bash
python -m pytest -q --tb=short \
  tests/rules/test_activity_canon_handler.py tests/rules/test_canon.py \
  tests/rules/test_m4_completion.py tests/rules/test_campaign_time.py \
  tests/test_activity_shadow_readiness.py tests/rules/test_mission_service.py
```

The focused Handler test captures the actual request sent through the model
adapter to a local synthetic transport. It checks concurrent scenes, reviewed
closeout, correction, consent withdrawal, citation scope, and stale delivery.
The authenticated Discord Activity and a hosted model require separate verification.
