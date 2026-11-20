# Session Zero worksheet

Session Zero is a group planning workflow for HarpyEngine. The administrator
selects the participating campaign members, including the prospective Handler.
Members discuss a written Handler proposal and approve that exact revision
individually. A configured administrator can apply the approved nomination
through the existing campaign appointment authority.

Every listed Pilot attaches their own current activated sheet or saved,
complete character review. Each player can then add a character goal, story
hook, and desired spotlight. The Handler can draft campaign goals from those
contributions. Every group member can generate the worksheet after all Pilot
sheets are attached. The worksheet identifies the submitted characters and
includes the information explicitly entered for Session Zero.

The first slice uses the existing guild app command, private interaction
responses, character-readiness checks, the command inbox and private
campaign events. Verify the full workflow with synthetic players, including
stale revisions, missing sheets, visibility and the Generate button.

## Running the workflow

1. Each participant joins with `/campaign join`. A configured administrator
   opens `/session-zero` and chooses the group, including the prospective Handler.
2. A member proposes the Handler player, name, archetype, appearance and
   personality. Each member approves that exact proposal. Revised proposals
   collect fresh approvals. A configured administrator applies an approved
   first appointment from the panel. Existing Handler replacements use
   `/campaign handler` and its existing confirmation rules.
3. Each Pilot attaches their own active sheet or a current, complete saved
   `/character review`. The saved review path supports pre-game planning
   before character activation. Each Pilot can add a goal, hook and desired
   spotlight. The approved Handler can draft campaign goals.
4. Once every listed Pilot has attached a current sheet, any group member
   can use **Generate Session Zero sheet**. Discord returns a private Markdown
   download with the approved Handler profile, character callsigns and
   playbooks, Session Zero contributions, and the campaign goal draft.

The worksheet carries only the character overview and content explicitly
shared for Session Zero. Complete sheets, private notes, character details
from the creation review, and private Bonds stay in their existing stores.
The service rechecks saved-sheet freshness when generating. A changed review
or active sheet prompts the owner to attach the current version. Changing the
group starts new approvals and intake so its new audience receives fresh
consent. Access is limited to listed members. An administrator outside the
group can manage membership and apply the nomination with limited status only.

Campaign goal text is a planning draft. Future campaign setup or narrative
tools can consume the worksheet when authorized. The Session Zero profile
records the group's archetype choice ahead of official Handler character
creation.

## Integration

The feature uses the existing SQLite schema and dependencies. The
`SessionZeroService` operates on the campaign's existing `OnboardingStore`.
The bot registers `/session-zero` for its configured guild. Use the stable
interaction delivery key for retries, a current worksheet revision when
editing, and the exact proposal identity for each approval.

Offline startup exposed two existing Mentor callbacks registering at
`/campaign mentor`, plus 30 direct commands against Discord's limit of 25 per
group. The setup nomination still uses `/campaign mentor`. The M3 callbacks
for `mentor`, `trainee`, `vatgrown`, `oldgen_sex`, `newgirl_sex` and `oldgen`
are now under `/campaign pilot`. Their existing handlers and permission rules
continue to apply.
