# M3G — canonical world, adversaries and source-triggered consequences

Status: IN_PROGRESS / RULES_SUBSET. Owner target: complete M3 implementation and
automated checks, then hand off a concrete player-testing candidate. This is not
independent certification or recorded human play-testing.

World data belongs to the existing canonical GameState and immutable game history.
Additive optional fields preserve old saves; no separate campaign authority or
live database migration is introduced by these models.

Implemented in this checkpoint:

- Printed map setup with three Foundation bases, at least two cities and three
  important locations; distinct squares and a private Class 0 at an actual base.
- Typed NPCs, factions, external Pilots/custody, Gorgon Class/Type/Assets/Core plans,
  permanent territory and explicit period-end movement choices. All eight actual
  Gorgon Type headings are supported, including Growth and Parasite.
- Native private setup, public map pages, NPC introduction/control and owner-only
  starting NPC Bond links. Previously unnamed slots can be linked by their owner
  when that NPC is introduced; private feelings are not copied to world records.
- Pure Directed one-square movement, Aggressive destruction/Class changes,
  three-by-three Gorgon territory, guarded Assets, Core exposure/defeat and
  custody-required transport. These helpers still need complete combat/period
  integration before the associated subsystem is finished.
- Twelve Strain branches have actual typed initial effects and native controls:
  Void Low 1/1, 2/1, 4/1, 5/1; Void High 3/1; Rebellion Low 1/1, 6/1;
  Budget Low 5/2, 6/2 and High 2/2, 3/2, 5/1.
- Persistent next-NPC Rebel affiliation consumed by actual introduction; room
  assignments/Bond overflow; all-Cadre shortage Tags; NPC firing; political areas;
  city anarchy without false physical destruction; revived Gorgon resources and
  inherited Sprite Types. The two-Collateral city threat has persistent state and
  a pure consumer, including interruption and once-only completion.

These initial effects do not finish Gorgon/Harpy abilities, world combat, future
trigger/scene integration, all table branches, the Off-Duty cycle or M3 overall.

Remaining order:

1. Complete source-bound Gorgon/NPC/Harpy actions and Player-owned responses,
   Core/Asset interactions, legal targets, player location/travel and conditions.
   A future conditional effect must use its actual trigger; never replace it with
   a generic “done” response or decide a voluntary Player action for them.
2. Bind world end effects to the real explicit Off-Duty end after recovery and
   source work; handle followups and all-base loss as actual owned decisions.
3. Integrate remaining Strain effects, deadlines, future missions/activations,
   NPC/Gorgon transformations, Director prices, custody/transport/conversion,
   captured character ownership and all supported Endgames.
4. Complete remaining Girl/Frame/Handler runtime rules and all source interactions
   with this world state, then comprehensive native controls and golden traces.
5. Run source audit, automated release/migration/recovery checks and prepare the
   player-testing handoff. Independent/human results remain separate evidence.

Acceptance includes rule-positive/negative cases, real campaign identity and
ownership, secret nonleakage, stale/revoked controls, pause, concurrency/rollback,
stable replay, backup/rebuild and exact source triggers. See `M3_STRAIN.md`,
`M3_OFF_DUTY.md`, the central rulings register and `reports/M3_ACCEPTANCE.md`.
