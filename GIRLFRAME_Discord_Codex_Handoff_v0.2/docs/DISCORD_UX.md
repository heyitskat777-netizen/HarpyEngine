# Discord Native UX and Interaction Contracts

## Scope and source

Build with `discord.py` application commands, `discord.ui.View`/`LayoutView`, select menus, modals and buttons. Do not assume the bot can modify Discord's sidebar, create a permanent right-hand panel, or render an arbitrary web app inside a normal message. The prior HTML mockup is illustrative, not literal Discord chrome. A future Discord Activity is a separate milestone.

## Command groups

| MVP command | Visible to | Description | Milestone |
|---|---|---|---|
| `/campaign create`, `/campaign join`, `/campaign status` | member / owner | Guild campaign and membership | M1 |
| `/girl create`, `/sheet [user]` | member / owner | Draft creation, own private sheet, others' public sheet | M1 |
| `/roll basic`, `/roll show`, `/ledger`, `/health` | member / owner | OS dice test primitive, receipts, audit | M1 |
| `/play` | active Girl owner | Select legal Girl/Frame Play and begin pending action | M2 |
| `/choice` | required player | Resume/reissue a pending player-facing decision | M2 |
| `/scene open`, `/scene join`, `/scene close`, `/scene status` | authorized scene participant | Play-by-post scenes | M4 |
| `/canon propose`, `/canon review` | player / facilitator | Evidenced proposals and rulings | M4 |
| `/mission list`, `/mission inspect`, `/mission respond` | eligible players | Offer/accept/decline and mission status | M3 |
| `/gm` and `/handler` | allowed participants | Distinct GM rulings and Handler speech | M5/M6 |
| `/safety pause` | any participant | Immediate OOC pause without fictional penalty | M1 basic, complete before AI |

Guild ID, authenticated Discord user ID and selected campaign are mandatory on every inbound call. Never accept character ownership from an untrusted slash option. Namespace groups according to Discord application command structure. Use ephemeral responses for setup and private replies, but require durable source-backed pending choices if actions can persist beyond an interaction token.

## `/play` wizard state machine

1. Player invokes `/play` → respond or defer **within Discord's initial interaction window**.
2. Server retrieves `legal_plays` from current ruleset, character sheet and scene state. **No AI needed**.
3. Select Play → service returns legal target types/IDs, whether target is required, legal Heat spending, legal Assets, required physical trigger and remaining resources.
4. Select target and Heat (and Asset if printed rule requires); stale input refreshes or errors, never consumes resources by accident.
5. **Confirm & Roll** with stable `action_id`, `interaction_id`, `expected_revision`; server validates and locks pre-roll spend before OS dice. Once rolled, no editing the Heat amount; send a receipt.
6. Present legal result-tier options, including ordered and conditional choices; required human/player/Handler GM responses become durable `choice_requests` with target principals and allowed branches.
7. `Finish Play` only when every printed mandatory effect, alternative selection and consent/rule-adjudication requirement has been fulfilled; commit effects atomically and update sheets/ledger.
8. Source linked to real scene or `fictional_context` description. A Play is not legal solely because it exists in a dropdown.

## Example native interface layout

```text
GIRL FRAME | PREPARE A PLAY  (private response)
Character: SYNTHETIC_GIRL_A   Status: Wing   Heat: 3
[ Choose Play: Keep Your Head                v ]
[ Target: Not applicable                     v ]
[ Heat spend: 2                              v ]
[ Confirm & Roll ] [ Cancel ]

After confirmation:
GIRL FRAME | ROLL RECEIPT #R-02
2d6: [4] + [3]  Heat: +2  Final: 9  Tier: 8–10
Select printed result options (requirements depend on Play).
[ Pick options ] [ Show ledger record ]
```

The example is synthetic. It does **not** claim that every possible heat/target combination is legal. The engine enforces eligibility and exact options.

## Discord constraints / development guidelines

- A slash/component interaction needs an acknowledgement or deferral quickly, before longer model/database work. Use a queued job for AI calls; do not rely on the transient interaction token for tomorrow's player choice.
- Ephemeral interactive views are not suitable as multi-day pending controls. The backend persists requests; use `/choice`, DM or a permissioned durable message to resume them, after verifying the requester and game revision.
- Native string selects are finite and require pagination/filtering for large legal lists. Revalidate values on submission, do not trust client selection IDs.
- `discord.py` persistent views require stable custom IDs and `timeout=None`, re-registered on bot startup. Durable pending choice state lives in DB independent of the View object.
- Multiple NPC/AI identities can be rendered with clear role labels/portraits; display is never proof of authority. Display e.g. `[GM]` vs `[HANDLER: VEY]` and log their distinct source principals.
- Discord changes or disappearance of a source message do not mutate canon. Preserve source message ID when allowed and a minimal verified event summary in the backend.
- Use `allowed_mentions=none` by default and selectively opt in specific user pings to avoid notification storms and abuse.
- Respect Discord permission and component limits; write fake-Discord tests for channel missing/permissions denied/invalid modal/stale button/unknown user.

## Publication and privacy

| Artifact | Delivery | Required authorization |
|---|---|---|
| Player's private `/play` setup | Ephemeral | owner user ID |
| Combat roll receipt | Scene/mechanics channel if visible | campaign + scene participants |
| Secret player choice | Private response or DM (opt-in) | required principal only |
| Active mission card | designated mission board | assigned roster/public info only |
| Canon summary | campaign ledger projection | per-event visibility; no private payload echo |
| Hidden knowledge reveal | named recipients only | independent knowledge and access checks |

## Persistent choice examples

- A Flirt prompts the **other real player** to answer the chosen printed question; store awaiting-user choice, never fabricate or substitute a generic answer.
- A Newgirl Mentor Play can require a mentor's choice; tag the target account, record replies in separate authorized events.
- A Handler direct order must record the literal in-fiction order and issuer; use Receive Orders then Disobey Orders if selected/triggers. The AI Handler may issue an order but does not select the human Girl's response.
- A mandatory world/Strain follow-up is an Engine/GMRuling requirement, not a “pending user” if printed rules assign the choice elsewhere.

## Accessibility and device test matrix

Test slash-command discovery, mobile narrow screens, dark/light themes, buttons under native 25-option limits, screen-reader button labels, long content pagination and accessible error messages. Feature must remain playable without elaborate images or a future Discord Activity.
