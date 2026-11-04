# M3E — resumable Off-Duty periods and source-owned recovery

Status: IN_PROGRESS / RULES_SUBSET. Source: book PDF 17, 27–28, 71, 118,
123 and 142–152; printed pages are two lower. Core sources and campaign rulings
must remain separate. Ancillary mechanics stay disabled.

## Implemented foundation

- An actual Off-Duty context, canonical roster and appointed Handler; no fake
  mission to hold recovery work. Private immutable period/work histories,
  projection rebuild and migration `0013` preserving existing mission records.
- Handler-only start preparation, current membership/review/pause checks, no
  overlapping period/unfinished mission/pending scene Play, and no new mission
  offer/dispatch while a period remains open. Development-only native commands
  `/mission off_duty` and `/mission strain` and the private Off-Duty inbox category
  expose preparation/owned declarations; no live M3 release has been deployed.
- Ordinary pure Play reducers retain actual 2d6 and current Status modifier,
  excluding Heat. No second roll after reopening. Required low/high scenes cannot
  be declined; mid routine scenes require other Girls when selected. Each actual
  participant confirms its own played scene. Recovery is once per period and
  blocked by pending mechanical effects.
- DoctorDoctor owner records a factual credit-sharing declaration or no trigger.
  A reward goes only to another current canonical Pilot, even when offline. The
  state/work/receipt transaction is idempotent and rolls back together. The
  factual account remains in private work history, not event metadata or command
  outcomes. No declaration is invented for an absent player.
- Sedation can bind to an actual period. Recovery and existing M2 optional unmarks
  respect it. Tag replacement/Paired rename retain a locked slot's mark. Explicit
  period end clears only that period's locks, preserving the marks themselves.
  Legacy/unscoped locks require explicit resolution; a new period cannot erase them.

## Work still required before an Off-Duty release

1. Strain scenario/trigger review, stable d6, Handler-owned column selections and
   parent-linked recursive/unused Endgame scheduling are implemented offline.
   Implement every selected table/Endgame's actual sheet/world effects, deadlines,
   deferred triggers and immediate ordering. The 72 selectable branches are not
   72 completed event resolvers. Current preparation has no generic acknowledge/
   waive method; root work stays pending. Custom-event substitutions also remain
   unsupported, without an automatic fallback that discards a printed result.
2. Void Observation provenance, pre-roll Status reduction, Void-count modifier,
   exact actor/Handler selections, all outcomes and scene/recovery dependencies.
   Ordinary Go Off-Duty is not a substitute for a pending observation trigger.
3. Wire ordinary rolls, scene participation and recovery to transactional services
   and private native Discord controls. Carry source-specific one-use modifiers,
   optional Tag embrace, asset/body-part exceptions, shortages and paid quotes.
4. Typed Handler scene selection/effects (including Handler playbook exceptions),
   Punishments on screen for harsh results, offscreen discipline/Requisitions,
   actual Status review and Gorgon/world movement at explicit period end. Do not
   accept client booleans as completed work or allow a human scene acknowledgement
   to stand in for a missing mechanical resolver.
5. Connect period-scoped Sedation in the discipline service and bind every followup
   to its real context. High Budget now marks DoctorDoctor once and uses the same
   context-bound compulsory replacement path as mission-failure scrapping. Add the
   remaining DoctorDoctor triggers and replacement paths. Preserve immediate-work
   ordering and source ownership.

## Acceptance

Executed tests belong in `reports/M3_ACCEPTANCE.md` and the additive acceptance
catalogue. Automated core/service tests do not represent independent review or
Discord play-testing. Required cases include all Status/tier branches, illegal
participant/Identity/Asset choices, observation substitution, shortages, pending
work, absent owners, revocation, cross-campaign isolation, stale state/revisions,
rollback, concurrent delivery/replay, restart/backup/rebuild and populated upgrade.
Every printed rule remains incomplete until its full interactions are reviewed.

## Ordinary cycle integration checkpoint

The ordinary Go Off-Duty roll now uses the shared transactional scene lock, OS dice
receipt, post-roll Tag choices, Bond modifiers and repeat-Tag/Paired follow-ups.
Status is committed before rolling; Heat is not spent. The final adjusted receipt
is saved to the real period before its scene/recovery choices become available.
An abort preserves known dice and answered humans. Its owner can resume only after
chat restoration; only an aborted unrolled reservation can be cancelled for a fresh
confirmation. A changed character, Handler or registry requires explicit recovery.

Activation proves three actual Strain rolls with saved columns, no remaining
preparation effects, and a matching canonical roster/character incarnation. It
cannot waive unimplemented Strain effects. Actual M2 Punishment debts are bound to
this period, including debts created during its scenes. An actual discipline
application fulfills the original debt; unrelated causes are not merged. Harsh
results and pre-roll discipline require an on-screen scene confirmed by the
participating humans. Moderate consultation, delegation and typed follow-ups retain
the real mission/Off-Duty context. Sedation receives the actual period ID.

Owned native controls and the requests inbox now cover roll/resume, scene choice,
individual participation, recovery and optional Tag embrace. The four-slot cap,
protected/Paired Identities and Sedation slot locks remain enforced. None of these
controls supply another participant's response. Every printed Handler scene has a
baseline workflow: routine, actual Permission award, actual Punishment, typed NPC
hiring/firing/chastising/request, current prisoner and a human-authored exploitation
scene. A human playing a real NPC/prisoner is separately invited; no PC is invented
for them. Hiring/firing records employment without inventing a price or changing
Bonds. Free external Pilots are unavailable as prisoners without actual custody.
Handler-playbook exceptions remain part of the uncompleted playbook runtime.

After real recovery/work and the Handler scene, the Handler explicitly reviews all
current Girls' performance and submits the complete Status order. Effective-Status
comparisons use active canon instead of creation-time ranks. Explicit end applies
Directed movement and Aggressive changes/destruction once. Destruction records an
unconsumed canonical Budget trigger with its actual source event; the next factual
Strain review cannot deny it. All-base loss remains required Handler outcome work,
not an automatically selected reassignment, punishment or ending. Sedation locks
clear only on successful completion of their own period.

Still required: Void Observation, all source-specific one-use modifiers, shortages
and paid repairs, complete playbook/body-part interactions, the rest of the Strain
and Endgame effects and world/Director outcomes, independent audit and human tests.
This ordinary-cycle checkpoint does not complete M3 or authorize a live M3 release.
