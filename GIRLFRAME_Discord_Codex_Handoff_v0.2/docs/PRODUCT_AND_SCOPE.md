# Product Contract and MVP Scope

## North-star experience

3–5 human players each control one Girl/Frame in an asynchronous private Discord campaign. The bot plays one Foundation Handler as a mechanically restricted in-world character and acts as GM for the surrounding world. Natural human roleplay proceeds without constant bot commentary. Players invoke explicit `/play`, `/sheet`, `/mission`, `/gm`, `/handler` and other interactions; event-driven scenes and consequences are reliably stored. Narrative initiative never steals ownership of a human PC.

## What success looks like

1. A new guild owner makes a campaign, assigns Players, creates a Girl/Frame by official rules once the character-builder milestone is complete.
2. A Girl opens `/play`, selects a legal Play, target, pre-roll Heat; the Engine commits a unique dice receipt, waits for legal options and other players, and updates all affected sheets on final commit.
3. Players converse freely between Plays. An authorized canon action records what was actually established, plus witnesses and in-fiction knowledge.
4. Vey (or a newly created Handler) can order, punish, bargain and pursue a defined agenda; her knowledge is limited to observed and reported information, not all GM secrets.
5. Missions and shared Off-Duty resolve exactly from recorded rolls, with mandatory Strain cascades and punishment obligations enforced. Harpies retain independent motivations; AI may not declare conversion consent without an established event.
6. Disconnects, retries, bot restarts and Discord message edits do not reroll dice, reassign a PC, fabricate canon, or erase history.

## Product phases

| Phase | Scope | Exclusions |
|---|---|---|
| M0–M1 | Private guild, campaigns, minimal synthetic GirlDraft, simple dice/ledger, read-only sheets | No AI or full mechanics |
| M2 | Native `/play` wizard and selected **fully verified** Plays, pending human decisions | No full game certification |
| M3 | Complete published-rule coverage inventory, verified module implementations, Strain, mission and Off-Duty | No autonomous AI consequences |
| M4 | Persistent scenes, private knowledge, asynchronous choices and chronology | No model calls |
| M5 | AI GM generating schema-bound proposals, verified NPC/world narration | No independent AI Handler yet |
| M6 | AI Handler character sheet, agenda, private-context limits, in-world orders | No public bot listing |
| M7 | Closed human multiplayer pilot, accessibility, backups and operational acceptance | No public commercial release |

## User roles

- `campaign_owner`: settings, roster assignment, authorized export, facilitators, pause; cannot forge another player's roleplay choices.
- `facilitator`: review disputed rulings, handle safety escalation, approve explicit canonical corrections and imports; logged and scoped.
- `player`: controls only their assigned Girl(s). MVP defaults to one Girl per account.
- `spectator`: read-only and explicitly approved; cannot read secret state.
- `ai_gm`: writes scene and NPC/Harpy/world **proposals** subject to Engine validation.
- `ai_handler`: writes Handler **proposals** and dialogue from the Handler-visible projection.
- `engine`: trusted pure logic and event service with authoritative commits.

## Explicitly excluded from initial release

- AI-controlled player Girls, auto-resolution of disconnected PCs, background advancement based solely on inactivity, live voice/recording, player impersonation by LLM, arbitrary past-canon import, web-wide public bot directory, Discord Activity fullscreen UI, monetization, graphic adult content.

## UX principles

- `/play` is an **ephemeral setup wizard**, then a durable pending action when other players must respond. Ephemeral selections are presentation, not persistence.
- A result shows dice faces, exact modifiers, tier, official choice count and needed next action. No automatic Bond changes from dialogue alone.
- A public action ledger and a permission-filtered private ledger are both projections of the **same** event stream.
- Disputes get a `Needs Facilitator` state, not AI fabricated results. GM ambiguity is reported clearly.
- Keep Discord API messages concise; show long rules by page name/reference or brief permitted extracts rather than copying large copyrighted passages.
