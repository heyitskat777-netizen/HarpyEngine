# GIRL FRAME Discord UI Mockups | Noncanonical demonstration

Open `GIRLFRAME_Discord_UI_Mockups.html` in a web browser to inspect seven clickable, Discord-inspired flow sketches. This file is an offline mockup. **It is not a Discord bot, not an MCP app, not a functional game engine, and it does not connect to any service or save data.** All character values, example roll faces, results, timestamps and story events are invented for demonstration and are **not GIRL FRAME campaign canon**.

## How to evaluate the seven flows

| Tab | User experience | Plausible native Discord building blocks | Backend behavior needed |
|---|---|---|---|
| 01 `/play` selection | Player selects Play, target, Heat before rolling | Slash command, **ephemeral** components-v2 card, select menus, buttons | Check ownership and availability; calculate Heat legality; record roll exactly once |
| 02 Two-player Play | The other Girl's **human player** receives a pending question and replies | Bot message, targeted mention, component button and modal; optional private conversation | Durable pending action linked to user IDs, Play and rolled result; block unearned Bond changes |
| 03 Handler scene | GM narration and AI Handler dialogue clearly distinguished; direct order opens action controls | Bot messages and separate attributed messages/embeds, button group, `/pause` | Handler context excludes unknown secrets; GM checks trigger; player owns response; engine resolves 7− |
| 04 `/sheet` | Player reviews character resources, Assets, Bonds | Slash command, components-v2 layout, buttons and ephemeral private view | Read state projections from database, private visibility filters, automatic refresh |
| 05 Secret | CHIFFON learns an anomaly; may tell AYLA or keep it private | DM, ephemeral response, restricted channel/thread (subject to admin permissions) | Actor-centric knowledge graph; source/witness/recipient provenance; never copy into Handler context without disclosure |
| 06 Mission board | Vey offers mission; each player accepts/declines separately | Persistent channel post, buttons, mission forum thread, updated status message | Real mission state and roster acceptance; GM/Handler authorization; no forced deployment |
| 07 Canon and rolls | Players inspect the immutable recorded facts, outcomes, roll history | Slash query, pageable bot messages/cards, message references | Append-only event log, immutable roll record, linked projection updates and correction events |

## IMPORTANT limits of the visual concept

- The Discord-like **server/channel sidebar** and **right-hand Campaign Status panel** are illustrative background around the bot messages. A normal Discord bot cannot replace the Discord client's navigation or install a custom right-hand panel.
- The **seven navigation tabs across the top** exist only to switch between concepts inside the HTML mockup. They are not bot controls. Each concept would normally appear in a separate channel, command response, or thread in the native Discord client.
- Real Discord **message components** support selectable controls, buttons and structured layouts. Small dialogs can be opened using **modals**. Richer fullscreen/dockable bespoke screens would instead require a **Discord Activity** or an external web app.
- The mock's `<select>` controls look similar to dropdowns but aren't literal Discord components. The bot must enforce Discord component and option limits, and defer longer-running interactions promptly.
- The demo's roll faces and totals are fixed illustrations and are **not verifiable random rolls**. In production, use the deterministic rules engine with OS-backed dice and immutable roll IDs.
- The two-player response modal is not shown to another logged-in user because this is a one-browser mock. In production the backend must deliver the prompt **only** to the correct Discord account and keep the pending step durable across process restarts.
- The mock's promise, mission, and secret buttons demonstrate intended states but do not commit actual events. Production code must validate every effect and enforce access permissions.
- Examples describe player decisions and mechanical consequences, not AI authority over a human-controlled Girl. AI may never invent the other Girl's response.

## Codex handoff: recommended component contracts

1. **`PlayWizardView`**: receives `{campaign_id, scene_id, acting_character_id, acting_discord_user_id, ruleset_version}`, calls `GET legal-plays`, `GET legal-targets`, and `GET legal-heat`, submits a nonce-protected declaration, and renders a pending action id.
2. **`RollResultView`**: presents `{roll_id, faces, modifiers, tier, legal_choice_ids}`, ensures exactly-once dice generation, and does not allow post-roll Heat edits.
3. **`PendingPlayerChoiceView`**: receives `{action_id, required_discord_user_id, question, allowed_answers, expires?}`, does not decide on behalf of a human, and persists when the view becomes unavailable.
4. **`HandlerMessageView`**: distinguishes **in-fiction order** from **GM ruling**. Its direct-order button links to an authenticated order event, not a free-text assertion.
5. **`CharacterSheetView`**: reads authoritative state projections and filters fields by requester permissions; public and private views must be intentionally different.
6. **`MissionBoardView`**: accepts per-player decisions, preserves declined/pending assignments, and derives status from the engine.
7. **`LedgerView`**: paginates and filters canonical records, with linked source messages and roll/Play causal chain; correction is a new event.

## Suggested UI order

Build `PlayWizardView` and `RollResultView` in the first playable Discord slice. Add `PendingPlayerChoiceView` before implementing Flirt, Defeat or any Play requiring another participant's choice. Add `CharacterSheetView`, `MissionBoardView`, and `LedgerView` as stable read-oriented surfaces before AI automation.

This document accompanies the separate development blueprint v0.1; it does not amend the live GIRL FRAME Turn 194 state.
