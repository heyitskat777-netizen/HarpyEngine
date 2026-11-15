# Live setup correction — current names and shared-account roles

The owner requested current Discord nicknames instead of visible member IDs,
Handler and Pilot on the same account, and a restart. The frozen5412ee8 bot stays
running while this patch is prepared; deployment outcome is recorded separately.

## Behavior

- Native setup/Status, review, Bond, Pair, shared-request, Cadre, mission and
  discipline queues display current guild member names. Native member selectors
  resolve their opaque member values to current names. Explicit member tokens
  avoid rewriting ordinary prose, dice/receipt IDs or saved history. Member
  lookup is guild-local, acknowledged before network work, shared per interaction
  and refreshed on new interactions. Failed lookups show a safe label rather than
  a numeric member ID. Mentions remain disabled and nickname Markdown is escaped.
- Status cards preserve all25supported participants, using an embed when escaped
  names exceed2,000content characters. Review resolves labels before pagination.
  Internal IDs, custom IDs, selected values and authorization remain unchanged.
- The appointed Handler's actual Pilot profile participates in Status, starting
  Bonds, review and activation. Pilot ranking uses Pilot rank; Handler authority,
  persona and resources remain separate. Self Pilot Bonds/Mentors are disallowed.
  Same-account printed Handler choices still require explicit proposal/acceptance.
- Activation records real typed Pilot↔Pilot starting Bonds for the dual-role
  endpoint using actual profile incarnations and the activation event. Ambiguous
  prior numeric authority stays blocked. Ordinary scene joining retains that
  Pilot and the OOC facilitator, not a fabricated fictional Handler body.
- Enabled scoped review guidance now says to finish/save creation then use
  `/character activate`; it no longer presents generic pending-review text as
  another missing creation requirement. Broader certification remains separate.

## Focused evidence and limits

Nineteen distinct relevant cases pass across retained initial/failed-only retries
and the additional affected checks: native nickname refresh/ownership/mentions,
shared-account complete review/activation/actual low Flirt, own Handler-choice
acceptance, existing Status/review/Bond/cast normals, long25-name Status,
reciprocal mid/high Flirt and all four memory-pagination cases. Initial new-test
fixture mistakes (wrong issue code, unassigned pure state result, omitted required
Heat0) were corrected; production gates were retained. Changed-source typing
passes26files; Ruff/format cover all30changed Python files. The exact published
patch still needs its focused CI result. No new complete regression is claimed;
5412ee8's3,328-test full result remains baseline evidence.

Separate source reviewers inspected the nickname/ownership boundary and fresh
shared-account setup/typed-Bond/scene-role flow. Their concrete long-card and
legacy numeric-Intense findings were repaired. This is bounded technical review,
not whole-P1/M3 certification. Broader lifecycle/role combinations were not swept.
The live campaign had no canonical activated-state rows at the relevant metadata
check. Existing activated-roster changes retain their explicit migration guard.

After deployment, reopen `/campaign status_setup`, include the Handler's Pilot
and confirm the full order. Each Pilot must still have an accepted eligible
starting Bond, save a fresh review snapshot, and use a fresh activation command.
The bot does not choose ranks, fabricate Bond acceptance or activate anyone for
this fix. Real player outcomes remain pending. AI, Ancillary, environment
publication, private-engine writes and broader campaign scope remain unchanged.
