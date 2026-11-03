# Intended native Play interface

The owner chose an overview inbox with guided detail review for requests. `/play`
is planned to use a one-step-at-a-time private panel, as specified in the retained M2 Play work order
and DISCORD_UX.md. This document records the intended interface, not working Plays.

1. Choose category (Core/Girl/Frame) and an implemented legal Play from native
   selectors. The rule registry and current sheet/context determine eligibility.
2. Read the printed trigger and requirements. Supply fictional context if needed.
   Select legal targets, Heat and any rule-required Assets/options. The menu itself
   never proves that a fictional trigger happened.
3. Review actor, target, locked-in choices, resources and expected modifiers.
4. Confirm & Roll. Revalidate and create the durable pending action, acquire the
   configured scene-channel chat lock and acknowledge it, then perform the
   irreversible roll/spend transaction. Failed acquisition performs no roll/spend.
5. Display the immutable receipt and the exact result-tier choices for that Play.
   No late Heat changes or duplicate-click rerolls.
6. Required player/Handler/GM responses route to the guided request inbox with
   legal actions and actor-specific authority. `/choice resume` is a planned alias.
7. Commit required effects, publish the permitted outcome and release the channel
   lock. Close/timeout of a private panel does not cancel a saved action.

Plays are not implemented yet; current `/roll basic` remains an unlocked raw dice
test. Do not enable buttons to resolve unsupported Plays. No arbitrary blanket
Asset bonus, invented result options or generic consent overriding printed rules.

The owner additionally requested scene-channel chat freezing while a Play resolves.
Detailed requirements and acceptance cases are in
`docs/work_orders/M2H_PLAY_CHANNEL_LOCK.md`. That feature depends on actual pending
Play actions and is not activated for character-setup requests or ordinary dice.
