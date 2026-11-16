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
