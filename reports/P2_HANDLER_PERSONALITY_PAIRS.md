# Handler personality in matched campaigns

Two newly created characters per playbook ran the same evacuation scene on
development base `31009ee`. The native clock reached 18:35 against an 18:40
cutoff. Each character received the same routine line, mixed handoff report,
updated report, request for a quiet channel, and direct time question. Each run
also included a private observation from the Pilot.

The comparison used synthetic proposals and replies written after inspecting
the actual role packets, then frozen for replay through the model contracts.
The engine checked response eligibility, review freshness, and delivery to the
original Pilot. The rehearsal measures what the contracts can support. The
writer's choices and dialogue do not measure an independent provider's
characterization or the long-term pacing of a player campaign.

## What the sheet has today

| Part | Saved fields and their use |
| --- | --- |
| Native identity | Name, appearance, outfit, background, and two gear choices. Starting Bonds, ranks and playbook-specific relationships are handled in the native setup. |
| Playbook guidance | Routine voice, initiative, eligible cues, when to hold back, behavior under pressure, recovery, strength and blind spot. It lists shared Plays, signature rules and advancement triggers. |
| Private roleplay notes | Personal voice, intervention instinct, current concern, obligation, and the Handler's view of a relationship or promise. The Handler can edit these after activation. The reviewed Handler receives them as portrayal guidance. |
| Optional Director dossier | A separately reviewed record can supply values, fears, contradictions, limits and reaction tendencies. Its changing state can hold evidence-backed relationships, goals, promises, obligations and experiences. |

The 14 baseline packets carried their playbook profile and role identity.
The native name, background and accepted starting Bond story stayed on the
sheet. The dossier requires separate authorship and confirmation. The notes
appeared after the owner saved them, and all 14 earlier need reviews became stale.

## Where the pairs diverged

| Playbook | First character | Second character |
| --- | --- | --- |
| Mistress | Mara gave immediate public credit for the extra checklist. | Sable waited for a peer to offer help, then made it easy for the Pilot to accept or decline. |
| Dogrunner | Brass assigned a repair as soon as the Pilot owned the error. | Vellum let the Pilot finish the correction, then asked which entry to defend. |
| Scientist | Hale preserved the two matching readings immediately. | Quill waited until a third reading was offered and asked whether it could change the decision. |
| Frantic | Rivet took a task off the Pilot at the first staffing bottleneck. | Morrow waited for a workable handoff and clarified what the Pilot wanted to delegate. |
| Insurgent | Mica routed the first demand for names through their desk. | Locke waited for the demand to repeat and offered a quieter follow-up. |
| Trainer | Slate gave the next check on the first procedural gap. | Bell intervened at the same point and asked the Pilot to identify the last confirmed check. |
| Advocate | Piper immediately returned the floor to the Pilot. | Rue waited for the Pilot to say they wanted to answer, then offered to stay or give room. |

Six pairs intervened on different beats. The Trainers used the same beat to
take different actions. Each character delivered one reviewed optional reply
and one requested clock readback. Across 84 inputs there were 28 deliveries.
The routine lines, requests for space and private observations stayed quiet.
The bystander received none of the replies. The common scene and fixed rules
keep the comparison focused on what the characters chose to attend to.

## What to improve next

1. Use the existing private notes to ask three concrete setup questions. What
   do you protect first when plans conflict? What makes you step in or wait?
   What do you do after you misread a Pilot? Those answers affect real choices
   in a shared setup. Keep cadence and vocabulary as a separate voice choice.
2. Seed the existing role-scoped dossier from the activated Handler's approved
   identity and a small number of agreed relationship anchors. Give the Handler
   their own name and selected details. Let the original participants review
   anything that would make a shared history available. Keep personality
   preferences distinct from facts the Handler actually perceived.
3. Carry forward a few accepted experiences that can change behavior. A refusal,
   successful handoff or kept promise should affect whether the Handler steps
   in again for that Pilot. Reuse approved review and closeout receipts, and
   preserve the playbook cue gate and player ownership.

The most informative next comparison would replay a second mission after an
agreed relationship change. Assess whether the new behavior follows from that
experience, whether the Handler still sounds like the same person, and whether
they leave enough room for the Pilots to act.

## Verification

**14 matched cases passed in 40.07 seconds.** The tests activated full native
sheets, saved private notes after activation, and used the reviewed response
and delivery paths with an inert transport. The business rules and runtime
prompts were held fixed for this comparison.
The Scientist and Trainer cases from the earlier timed rehearsal also passed
in 7.74 seconds. Ruff and Git whitespace checks passed.

```sh
PYTHONPATH=src .venv/bin/python -m pytest -q --tb=short \
  tests/rules/test_handler_personality_pairs.py
```

[Replay test](../tests/rules/test_handler_personality_pairs.py) · [Synthetic replies](../tools/fixtures/p2_handler_personality_pairs.json)
