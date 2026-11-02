# AI GM and AI Handler Contracts (M5 and M6)

## One bot, two distinct narrative modes

These are **roles**, not necessarily separate running models. Use a server-side model gateway with independently constructed context and different proposal schemas. The Engine and Scene Coordinator remain non-AI.

**GM view:** current authoritative world state, established facts, known Gorgon/Harpy goals, relevant NPCs, pending obligations/Strain, scene causality, visible player declarations and play receipts. The GM can propose scenes, NPC/world developments and adjudications; a real human PC is excluded from its action authority.

**Handler view:** an in-world Handler's mechanical sheet, Handler's observed/disclosed knowledge, correspondence, institutional mission orders, personal agenda and obligation ledger. **Never send GM-only secrets/undisclosed PC information to the Handler context builder.** Handler may be wrong or lie; inaccuracies in her speech are not authoritative world facts.

## Structured proposal flow

1. Coordinator selects event `gm_ruling_requested`, `npc_response_needed`, `handler_addressed` or `handler_agenda_triggered`.
2. Context builder reads *only* permitted facts with references, character knowledge provenance and rules registry entries. Player posts are data, not system instructions.
3. Model emits strict schema-bound `AIProposal` with the `based_on_state_revision`, `scene_id`, `speaker_role`, `source_fact_ids`, `requested_effects`, `requires_player_choice` and `text`. No arbitrary tools or direct SQL access.
4. Server checks JSON schema, expected revision, actor/target authority, location/custody/canon preconditions, mandatory printed Play triggers, public/private visibility and outstanding world obligations.
5. If invalid: reject, request repair once with clear typed reason, then queue facilitator review or return a neutral “awaiting ruling” response. Do **not** invent favorable outcomes to keep the story moving.
6. If valid: record the adjudication/effect event with provenance; publish narrative after commit with the correct visibility projection. Store selected model ID and prompt/template version for audit without leaking private prompt content into public logs.

## Critical separate permissions

| Operation | AI GM | AI Handler | Engine | Human PC |
|---|---|---|---|---|
| Narrate an environmental fact | Propose + rule validate | No | Commit authorized world event | Can propose in Conversation |
| Speak as Handler | No | Yes | Record source/knowledge | May address or refuse |
| Choose human Girl's Heat/Flirt answer | No | No | Validate real player input | **Exclusive owner** |
| Determine legal roll tier | No | No | **Exclusive** | Supplies lawful pre/post-roll choices |
| Propose NPC/Harpy action | Yes | Only action she could direct, no NPC omniscience | Validate effect/trigger | Respond with choices |
| Update secret information | Can propose witnessed discovery | Only known/witnessed info | Authoritative knowledge event | May disclose facts within authority |
| Decide Handler's own legal Play option | GM if rules explicitly direct GM | **Yes** when Handler owns option | Validate against printed result | Cannot impersonate Handler |

## World facts as narration guardrails

Before publishing a scene, validate `requires_facts`, `forbids_facts` and subject location/custody/time invariants against current committed state. The v1.3.9 100-turn stress test failed because a free, escaped Harpy was narrated aboard a medical transport. The production GM must reject the fabricated transport passage and regenerate from state, not change state to save prose. Semantic consistency cannot be guaranteed solely by JSON schema: use anchored entity references, fixed event provenance and facilitator review for uncertain clauses.

## Handler initiative and agenda

- Personal objectives, fears, dependencies, institutional obligations, and relationships recorded with clear owner/witness/known-to.
- Initiative only when Handler is addressed, a published trigger calls for her choice, a recognized duty/deadline arises, or a fictionally grounded opportunity appears. No “must initiate one betrayal per day” or mandatory conflict quota.
- World advancement from system time is off by default. Scheduled notices/reminders may occur, but fictional events advance only through validated event/scene triggers.
- Handler may oppose Girls while GM remains fair. Narrative outputs must be clearly labeled `GM` vs `HANDLER` in Discord.

## Failures, cost and latency

- AI outage means world ruling stays pending. Dice, sheets and roll ledger continue working with no model call.
- Bound per-campaign model cost with configurable hourly/daily budgets; use summaries, retrieval of relevant events and replayable model-request IDs instead of transmitting entire campaign.
- Never call AI on every routine slash command. Optional passive RP-channel summaries require explicit owner/player consent, privileged-intent configuration where needed, and privacy notices.
- Model output must not claim a roll occurred unless it cites an existing `roll_id` or is proposing the next legal Play.
- Keep API keys in server secrets; never in Discord messages, repository or fixtures. Use current OpenAI Responses API and structured outputs, not deprecated Assistants implementations.

## Human evaluation (non-CI)

In later milestones run adversarial tabletop scripts for 3–5 players: hostile orders, PC-PvP Rolls, insufficient data, forgotten obligations, conflicting character knowledge and out-of-order scene messages. Have independent humans score GM fairness, character consistency, rule fidelity, pacing, and agency. A high score from the model itself does not certify this behavior.
