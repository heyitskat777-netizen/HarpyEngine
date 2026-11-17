# Typed GM outcome consumers

Implemented on top of review baseline `9c713d3` as a synthetic, engine-first
candidate. This supersedes the review's implementation status and its table-authority
recommendation. The 63-entry review remains design evidence, not rules certification.

## Behavior

`GMOutcomeService` accepts strict, provider-neutral proposals bound to an actual
pending native source. It stores a private request/proposal; confirmation calls the
original native service as the actual source owner. The engine retains dice,
resources, costs, choice ownership, source proofs, follow-ups and delivery.

| Source / operation | Consumer and limits |
|---|---|
| Keep / `keep` | Actual `handler_keep`, including genuine child and alternate-actor sources; explicit goal demands, real are/are-not traits and prerequisite evidence. Harpy `beautiful` is supported. Clarification cannot commit a verdict. |
| Sensors / `sensors` | Every actually selected ordinary question, including mandatory high/off-list consequence; diceless Harpy question block uses its honest-answer consumer. |
| Battle / `battle_facts` | Original proposed battle context and adjudicator; opening, reach, permission, defense and Core facts enter `BattleService.confirm`. No reroll or replacement of fixed tier outcomes. |
| Battle / `battle_consequences` | Original pending Handler consequence choice; personal Asset payment remains with its owner. |
| Gorgon / `gorgon_judgment` | Actual capability, pitted-Asset contest, attack-response and collateral-reach judgments; scoped verdicts and genuine losing Assets only. |
| World / `collateral`, `warp` | Original Gorgon-controller choices; finite native effects and real subjects. |
| World / `handler_effect` | Existing pending Handler grant, limited to escalation, support or actual Contaminant Zone warp. Cannot issue a grant or manufacture zone authority. |
| PANDORA / `pandora` | Actual child-proposal stage, tier-bound class and Asset count; original native child creation and birth constraints. |
| Wraith / `wraith` | Actual Handler rules/Tag stage; retains tier and Frame-bound NPC requirement. |
| Snoop / `source_fact` | Actual pending object-existence/access judgment. The target's findings and private answer remain target-owned. |
| Shared table / `table` | Owner-approved GM discretion for Assault advantage and final exploration answers. Retains contributions and supersedes only shared closure controls. |
| Completed Play / `narration` | Separately confirmed synthetic contribution referencing actual completed result fields; applies no canon effects. Native pending work cannot be narrated as completed. |

The user explicitly ruled: **“Table outcomes should be GM-discretion.”** Trusted
policy `owner_table_outcomes="gm_discretion"` selects real GM-owned controls for new
Assault/exploration actions. It also permits adjudicating an existing open shared
stage after a policy transition, retaining prior contributions. Default `None`
preserves frozen configurations; no live policy was changed. Personal decisions,
consent, target-owned answers, child Plays and required costs remain independent.

## Validation and privacy

Requests bind source, scene, actual owner, original receipt where one exists,
canonical revision, current source records, consent/safety/cast guard, references
and the latest 100 synthetic scene inputs (with an omitted count). The same frozen
snapshot is checked inside the native write transaction. Changed sources or
permissions require a new request. Native command caching provides exact retry
behavior; a new command cannot reuse a consumed source. No migration or generic
effect-execution endpoint is added.

Full GM packets and private reasoning require the configured administrative GM
lens. `owner_review` gives only intended consumer fields to the actual owner as
an explicit OOC review. Private reasoning is never automatically copied into an
answer or contribution. This is **not semantic leak detection**: a reviewer must
check any free prose deliberately selected for disclosure. Handler persona requests
continue to use their separate, narrower knowledge context.

No provider is installed by default. Supply a typed manual proposal or an injected
`OutcomeProvider`; missing providers fail closed. The tests use explicit
fixture-authored interpretations, not keyword inference or autonomous AI judgment.

## Offline evidence

See the focused candidate and CI evidence recorded below. Tests reuse actual native
scenarios through typed proposal confirmation, preserving their original assertions.
They cover original owners, exact retries, source substitution, missing answers,
transaction-time stale rejection, guard cleanup, private-reason exclusion, child
and Harpy Keep, ordinary/Harpy Sensors, combat and Gorgon judgments, collateral,
evolution, Handler escalation/support, Contaminant warp, PANDORA, Wraith, Snoop,
GM table discretion and completed-outcome narration. Frozen default table behavior
also receives focused compatibility checks.

This is not a full regression, independent printed-rule acceptance, connected
Activity trial or real-model evaluation. Remaining conditional consumers from the
review (such as later poor-advice evidence) retain their native/manual source work;
there is no universal GM override. Activity UI/backend authentication, model
selection/budgeting and live installation remain deferred. No spending, external
model calls, real campaign capture, deployment or bot restart occurred.

### Recorded local checks

- Focused CI selection: **194 passed in 201.40s**, JUnit retained locally at
  `var/gm-outcome-candidate.xml`. This run started before the final additional
  Engage/Gorgon narration scenario and table-service authorization correction.
- Final affected checks: **3 passed in 6.27s** for GM Assault discretion (including
  revoked native release approval) and Engage/Gorgon final judgment/narration;
  the table authorization selection separately passed **3 in 6.40s**.
- The final focused selection includes the additional scenario, for 195 cases.
  Remote CI on the committed candidate supplies exact integrated-source evidence.
- Changed-source lint/format passed for 12 Python files. Applicable typing passed
  for nine source files, with the final table-service correction rechecked.
- Runtime registry contract, original planning contract, offline CLI health and
  publishable-file/manifest checks passed (zero repository findings).

Earlier failed development runs exposed a Keep evidence-ID translation mismatch
and several fixture setup errors. Those were corrected and the affected native
flows rerun. No failed case is excluded from the final focused selection.
