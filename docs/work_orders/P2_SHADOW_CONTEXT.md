# P2-D2/D3 — source knowledge and durable shadow decisions

Owner directs continuation toward a live-trial candidate. This unit completes
source-aware synthetic knowledge and shadow evaluation before external integration.
Normal flow: freeze a supported observation as a chronological reference with
explicit actor knowledge → build separately authorized GM/Pilot/Handler context →
claim an eligible batch → invoke deterministic provider outside the writer lock →
validate five-way decision and sources → atomically save outcome and acknowledge
only its current frontier → reopen. No mechanical application or publication.

Files: ai/director.py, services/director_context.py, services/director_shadow.py,
database/director_context_schema.py, metadata, next additive migration and focused
tests. Reuse D1 actors, consent, source history, claims and transaction patterns.
Bounds: 100 context references, 1,000-character source inputs, one repair attempt;
failed or stale work consumes no input. Scene ordering is explicit sequence and
source dependency, not real-time advancement. Superseded inputs invalidate context.
Missing NPC presence/knowledge and mechanical consumers stay blocked.

Completion: synthetic source → explicit Handler knowledge → isolated contexts →
WAIT or review-only typed proposal → durable reopen/replay; privacy canary,
chronology/source/revocation, repair/failure and stale provider completion checks.
Runtime/live integration still needs the actual Activity backend/session handoff,
real-data consent/retention, provider/model/budget, authorized operational setup and
human review. No paid calls, real capture, restart or deployment in this unit.

Next bounded integration: actual cast NPC context. Reuse existing ActorService
controller/profile proof and CastRole validation. Grant only explicit source
knowledge to actual living cast NPCs; return no private NPC details automatically.
No NPC-only audience expansion, autonomous dialogue or world mutation. Demonstrate
actual NPC cast/known source/withdrawal and wrong-controller/uncast rejection using
existing world/cast fixtures before adding a speaking/publishing consumer.
