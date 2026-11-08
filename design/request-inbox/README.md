# `/character requests` — design preview

This is a reviewable mockup, not a deployed bot change. All people, counts and
requests are synthetic. The page is self-contained and uses no external services,
credentials or campaign records. Its buttons change browser memory only. Reset
restores the examples. The comparison page loads the same prototype in three frames.

Open [index.html](index.html) for the interactive demo, or [overview.png](overview.png)
for the side-by-side preview. Other images show each layout, request detail, changed
request, empty inbox and a 390-pixel mobile view. Discord controls its actual fonts,
spacing and colors; these screenshots approximate its native appearance. The
prototype comparison toolbar is outside the proposed Discord response.

## Selected direction

The owner selected **A — overview inbox, opening B — guided review**. See
`DECISION.md`. The original comparison remains design history. The runtime uses
five summaries per overview page and one version-bound request per review. It uses the
current classic `discord.ui.View`, embeds, selects and buttons. C is a feasible
alternative using Components V2; the installed discord.py 2.7.1 supports its
LayoutView/Container/Section/accessory-button shapes. It requires a different view
implementation. No external dashboard or browser page is required in Discord.

A slash command opens a private ephemeral bot panel. A native popup modal is useful
for entering a callsign/context, rather than as the inbox itself. Selecting a
request or pressing Review edits the panel to show its effects and allowed actions.

- A: five request summaries per page, pending/needs-you/waiting/history buttons,
  category dropdown, request dropdown, and Previous/Next/Refresh/Close.
- B: one full request, before/after or effect preview, shared details, role-specific
  action, Back, and Previous/Next. This is also A/C's detail screen.
- C: three native request containers per page, each with a Review accessory button,
  filters and paging. Fourteen/16/29 component-node payloads were constructed by
  the installed SDK for A/B/C. The classic payloads use four action rows; C stays
  below the V2 40-component limit. The proof is `native-components.json`, not a
  complete callback implementation.

The demo exercises local acceptance/decline/withdrawal, filters, page navigation,
role-specific outgoing actions, empty state and changed-request blocking. Pair
Asset actions show where the existing wizard would open; they do not simulate a
second Asset-selection implementation. Preview Bond/Play entries are intentionally
unresolvable until their mechanics exist.

## One inbox, multiple sources

“All pending” means all pending requests/tasks relevant to the authenticated player,
including incoming and outgoing. It never means every private request on the server.
Default to Pending; provide Needs you, Waiting and History without slash arguments.
Only role-appropriate actions appear: a sender cannot accept their own proposal,
a Handler assignment is not silently reassigned by its recipient, and a Pair's
choice does not expose another player's private descriptions.

| Item | Existing backend | Unified inbox behavior |
|---|---|---|
| Starting Bond | BondService; currently separate `/character bonds` | Incoming accept/decline, outgoing withdraw, private detail |
| Court and Mentor callsign | SharedSetupService; current `/character requests` | Same decisions through a shared review layout |
| Handler Mentor nomination | HandlerService plus starting-Bond flow | Derived coordination task: nominated Newgirl starts agreement; Mentor reviews the resulting Bond; Handler retains nomination authority |
| Pair Assets | PairService plus creation owner descriptions | Pair sees Choose Assets; owner later sees Describe Assets; each routes to its existing authorized wizard |
| Mentor callsign to choose | Accepted Mentor relationship plus callsign flow | A task for the Mentor until a request is sent; then recipient review |
| Bond elevation/change | Not implemented as an official mechanical resolver | Future task keyed to a validated rule/action; never free-form “approve a stat change” |
| Play responses/coordinated mechanics | Original M2 pending-action/choice work remains | Future legal-option selector tied to committed action and saved receipt; no reroll |

## Implementation after design review

The implementation adds a service-level inbox projection over the existing request sources and derived
coordination tasks, with source-specific adapters for allowed actions. The common
item needs stable source/type/ID, participants, state, freshness, effect preview,
required actor/action and expected revisions. Counts, filters and pagination must
operate over the combined eligible set, not concatenate separate limited pages.
Deduplicate tasks when a downstream request already represents the same work.

For example, once a nominated Newgirl sends the Mentor Bond request, show that
request to the Mentor rather than also generating a duplicate “start agreement”
task. After acceptance, create a “choose callsign” task for the Mentor; once sent,
show a waiting request to the Mentor and a decision to Newgirl. Pair Asset names
and the owner's descriptions likewise remain different tasks and authorities.

Reuse existing typed service commands for mutations and recheck authority,
current state, constraints and revisions at click time. A changed request can be
viewed/declined/withdrawn as allowed, but old acceptance remains disabled and a
fresh proposal is required. Refresh reloads records; it cannot authorize a stale
version. Avoid Accept all: request types have different rules and consequences.
Mechanical changes must originate in implemented rule services; the inbox only
routes player choices and displays outcomes. Some future rules may require a
specific response or acknowledgement rather than generic accept/decline buttons.

Saved decisions survive restart in the existing stores. Ephemeral panels expire;
reopening `/character requests` reconstructs the current inbox. A persistent entry
button in onboarding could open the same private inbox later. No DM or public
notifications are part of this mockup. Broader notification policy is a separate
choice, not an automatic side effect of unifying requests.

## Verification

`validate_layouts.py` constructed all three native component trees without logging
into Discord. `render_mockups.py` rendered the HTML offline with Chromium and
checked filters, simulated acceptance, sender-only withdrawal, planned/stale action
blocking, empty state, task routing, all three layouts and mobile overflow. It
reported no page errors. The managed browser blocks `file:` navigation, so the
renderer loads the already-local HTML into an isolated page in memory; screenshots
use the same content. No external network access is needed.

These original mockups did not change the live bot. Following the owner's selection,
the overview and guided review implementation is tracked in `docs/work_orders/M2G_GUIDED_INBOX.md`
and `reports/M2_ACCEPTANCE.md`; the browser remains a standalone synthetic demo.
