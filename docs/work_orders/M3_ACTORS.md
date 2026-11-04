# M3B/G — actual actor identity and shared rules ports

Status: IN_PROGRESS / RULES_SUBSET. This is the actor/scene state required for M3 mechanics, not the
broader M4 Scene Coordinator or any AI implementation. Sources include the shared
Girl/Frame Plays (PDF 20–29), NPC principles/playbooks (188–191), Director (192),
Harpy/rebel and Gorgon chapters, and the current source registry.

A Discord human and a fictional character are separate identities. One human may
play a Girl and an NPC/Director. User-ID-only authority cannot distinguish those
roles. Keep actual entity references, current human controllers, character/Frame
incarnations and source events explicit. Source-gated pending requests must not
move to another character because a name/role/profile changes.

Implement typed actor references and canonical resource ports for real Pilots,
NPCs, external Pilots, Gorgons and the Handler's Director context. Preserve the
actual Pilot roster and its immutable activation/review provenance. Do not copy
non-Pilots into Pilot sheets or maintain a second mutable state authority. Public
views and Handler knowledge must omit unobserved private entity/card information.

Bind the minimum actual scene cast and role selection needed by rolls/targets.
Validate controller, actual location/custody, role, incarnation, legal Assets and
required Core exposure before commitment. Existing M2 human-Pilot behavior must
remain intact; preserve actual OS dice, post-roll ordering, exact human decision
owners, scene locks, interrupted choices and durable receipts. Actor/cast changes
need explicit safe recovery. Role acceptance, fictional movement, medical help,
transport, conversion and consent are distinct events.

A shared rules port must carry source-specific resources and conditions, rather
than inventing Girl/Frame playbook traits, Assets or Status for another actor type.
Introduce source-owned fiction choices where the book leaves them to humans.
Missing consumers fail closed. Add no generic force/waive/resolve command.

Acceptance: one human with two roles, Director versus its player's Girl, secret
NPC data, spoofed entity/generation IDs, current controller change, absent actor,
real legal targets/assets/Core scope, no borrowed abilities, nested owned choices,
resource/receipt rollback, pause, concurrent commands, restart/rebuild and native
selectors. Bind future career-end/new-character work to actual character IDs;
old actions/coordination/role sync must not apply to a replacement character.

## Implemented actor and casting checkpoint

Typed references distinguish current Pilot character incarnations, NPCs, external
Pilots, Gorgons and scoped Handler contexts. Descriptors read actual canonical
resources; unmodeled resources stay absent. One human's roles never borrow one
another's playbooks, Heat, Assets, Identities or permission to view hidden entities.
Immutable original profile snapshots prove legacy bindings. Existing Play choices
also bind every actual participating character; genuine legacy action history can
prove the original generations without guessing or rolling again.

`/mission actors` provides a private owned-role selector. `/mission cast` records
explicit role joins and withdrawals in the actual bound scene, with source events.
Existing human scene joins are imported only from their original immutable bind,
join, canonical state and profile evidence. The original Handler join records a
facilitator, not automatic fictional Handler presence. One human may cast an NPC
and a Girl separately. NPC control does not silently join that human's Girl.

Casting changes require finished actions and restored chat. Own withdrawal remains
OOC during a safety pause. Old controllers may withdraw their own stale casting
record; new controllers must make their own explicit join. A role change cannot
move answered choices or known dice. Closing a scene archives its cast; reusing a
channel creates a different actual scene identity. Unknown NPCs stay hidden in
views, including the Handler's view. A casting record never supplies fictional
movement, medical help, custody, piloting, exposure or consent.

Pilot-only casts retain existing M2 controls. Mixed-role casts fail closed in the
legacy Play/order/follow-through path until actual actor-aware consumers exist.
This is deliberate partial coverage, not an implementation of those Plays. Actor
aware target/location/resource ports, Director Girl Plays, NPC/Gorgon Plays,
career/lifecycle archives and full runtime interactions remain required.
