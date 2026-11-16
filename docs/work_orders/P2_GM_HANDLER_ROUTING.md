# P2 — discrete GM and Handler conversation routes

Owner clarification: messages route separately to the GM (campaign-wide canonical
information, adjudication and Play requests) and Handler (only actual role-known
information). No paid calls. Implement a deterministic local conversation adapter
and test with only Pilot turns scripted; no prewritten Handler dialogue.

Flow: accepted own scene message → explicit gm/handler target → separately built
provider request → bounded sourced answer/clarification or engine-workflow referral
→ atomic private saved reply → reopen/retry. Direct requests do not wait for routine
quiet batching. Existing autonomous observer stays separate. No rolls, spending,
orders, acceptance, consent or other mechanics follow from conversation text.

Files: ai/conversation.py; services/director_conversation.py; narrow internal
Handler projection seam in director_context; optional reference topic metadata;
focused routing/knowledge/stale/retry tests; reproducible Pilot-only transcript.
Reuse the authoritative store, actual sender/Handler identity, source revisions,
consent, pause and append-only outcome tables. Do not forge a Handler viewer or
forward GM provider output/context as Handler input. GM's broader reading authority
is not permission to publish undisclosed information or access credentials.

Synthetic providers use bounded question categories and exact sourced templates.
Missing facts produce clarification. GM receives all canonical campaign state
plus current scene references; output to a Pilot is restricted to permitted facts
or neutral mechanics referrals. No real model intelligence is claimed. Framework,
UI and paid providers remain deferred. Completion requires a substantive engine-
generated Handler answer, correct unknown response, discrete GM referral, private
canary separation, saved replay and stale/paused/unauthorized rejection.

Owner-requested follow-up and correction: run two scenes of 100 scripted Pilot
inputs each; no scripted Handler lines, address flags, expected response markers
or reply quota. The engine independently saves RESPOND/WAIT before invoking the
Handler generator. Bounded synthetic need detection supports direct questions and
a proposed forced-entry action contradicting actual known scope. Ordinary talk,
third-person mentions, negated action and explicit GM requests do not trigger it.
Record numbered interventions, actual reply/citations, silence decisions and
separate GM diagnostics. Prove privacy, retries, stale-decision rejection and
unchanged mechanics. GM raw history uses the latest 100 entries with an explicit
omitted-entry count, while canonical state and known references remain separate.
Keep generated HTML/JSON under ignored var/. Real unsolicited publication and
general narrative intelligence remain unsupported.

Next owner-requested demonstration: incorporate actual native Keep Your Head
Plays into both long scenes, exercising low/mid/high tiers. Show engine-selected
GM intervention versus private routine review, actual receipt/choice/lock stages,
required original Handler adjudication and optional scoped Handler dialogue.
Keep all player and required Handler choices explicitly scripted fixture inputs;
AI prose cannot supply those choices or declare success from a tier. Reuse native
Play services and completed-source proof; add only a private, replay-safe GM
readback of whitelisted receipt/total/tier. No general automatic Play consumer,
new rules, paid calls or live publication. Record actual changed synthetic state
and RNG counts instead of retaining the previous zero-roll/unchanged-state claim.
