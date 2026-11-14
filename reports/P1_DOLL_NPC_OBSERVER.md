# P1 ordinary NPC Unassuming Doll observer

Baseline: `harpyengine-p1-doll-advice-integrated-20261111`.
Sparse overlay: `harpyengine-p1-doll-npc-observer-20261111`.
Safe execution view: `harpyengine-p1-doll-npc-observer-exec-20261111`.

## Source and finite result

Unassuming Doll, rulebook PDF50/printed48, allows “someone” to answer a question
or offer a secret and “they” to give a Tag or Punish the low result. The concrete
missing adapter was an unconditional exclusion of all NPC observers. The native
source now accepts an actual ordinary, visible World NPC at the same established
location and in the original cast with its actual controller. Historical proof
checks the original ordinary visible NPC as well. The Vatgrown's own Heat,
receipt, body, scene and benefit lifetimes remain unchanged.

An NPC observer is not a new NPC performer or resource sheet. Observation does
not require invented physical contact, human anatomy or consent. Special-source
NPC aliases remain excluded by the existing ordinary-NPC validator. Answers,
Tags and source-supported social Punishment retain their original controller.
Existing Punishment instruction, severity-appropriate consultation, actual
attendance, effect and completion govern the consequence before the Doll gets
her low benefit. The currently supported NPC social effects are minor, so they
do not require Handler consultation. The existing mandatory consultation gate
applies to moderate Punishments; this adapter does not expand that gate.

## Authored normal tests

All four nodes are in `tests/rules/test_vatgrown_npc_observer.py`:
- `test_native_npc_mid_paid_source_owned_secret_and_private_reopen`: native source,
  actual cost/receipt, source actor/controller, independently authored private
  secret, wrong-human rejection, duplicate submission, readback/restart and
  public payload nonleakage. Recommended root minimum.
- `test_native_npc_high_real_object_and_quiet_benefits`: actual one-plus-object quota.
- `test_native_npc_low_actual_tag_before_owned_benefit`: original NPC Tag provenance,
  idempotency and required consequence before the one benefit.
- `test_native_npc_low_real_social_punishment_before_benefit`: actual NPC instruction,
  voluntary Handler approval, independently attested scene, real Bond/Tag social effect
  and source/chat closure before the benefit.

Worker pytest and collection: **NOT RUN**. Root reports the exact native mid
node above passed **1 in 6.28s** in the safe execution view. High, low Tag and
low Punishment normals remain authored **NOT RUN**. No source or test changed
after that run. Root owns further minimal execution.
No existing green workflow was rerun. Full regression, affected directed/other
observer-source combinations, global static/migration/privacy/restore checks,
independent review and human acceptance remain pending.

## Local static checks

Changed service and test: Ruff check and format check passed, with the original
project config and explicit `girlframe` first-party classification for the sparse
overlay. Python AST parse passed for both. The first lint invocation discovered
the workspace-global config rather than the project config and reported unrelated
rules; the corrected invocation found only one new long source line and one long
test assertion, both corrected before the final successful check. No broad static
or typecheck was run.

The safe execution view hardlinks 1,700 unchanged baseline files. Both modified
Python paths were copied directly into fresh nlink=1 inodes before any execution;
all source bytes match the overlay and the baseline service hash stayed unchanged.
Caches, virtualenvs, private `var`, `.git`, bytecode and archives were not copied.
Documentation/registry additions stay in the sparse overlay for root integration;
they do not modify the already-created execution view during root testing.

No bot start, live Discord, merge, deployment, model call, publication, real
campaign data, archive/full-byte snapshot or user-file deletion occurred.
