# P2 Director design — Activity-first reconciliation

Checkpoint base: `28937b43fea63ac4df36260a330b55ebc6f39fb8` on
`codex/r285-integration-20261114`. The existing checkout was clean; an explicit
target-branch fetch found no newer work. No worktree, reset or history rewrite.

Input: owner's **GIRLFRAME / HarpyEngine: AI Director Architecture and Development
Handoff**, SHA-256
`650bc486b1d978ce3f02554471eae7a4fc50baab1b95968f8d1ae59d5d256cc4`.
The current instruction changes its transport to the Discord Activity. The
approved product decisions are retained without reopening them.

## Incorporated decisions and adaptations

- [Canonical architecture](../docs/AI_DIRECTOR_ARCHITECTURE.md): Option C, balanced
  initiative, 120-second quiet window, all adjustable pilot defaults, enabled NPC
  dialogue/world-proposal capabilities, off/shadow/live, five decisions, actual
  completed-Play integration and the twelve acceptance criteria.
- Explicit Activity scene submissions and committed engine events replace passive
  channel/thread observation. IC/OOC intent, server-owned source identity, consent,
  source revisions and durable scene IDs preserve the observation boundary.
- Quiet eligibility, active-conversation size/age reviews and optional publication
  are distinct. `WAIT` consumes only successful reviewed input; failures consume
  none. The new-input episode definition excludes Director/mirror/tick loops.
- Scene projection/refresh and stable contribution IDs replace an assumed general
  Discord-send path. Required outcomes remain independent of optional narration;
  any future Discord mirror retains separate at-least-once delivery semantics.
- UI scope covers scene timeline, owned choices, attention/ready controls,
  observation notice/consent and private facilitator controls. Current framework,
  authentication and deployment are still unknown, so no connected API is claimed.
- Source inspection confirmed existing scene/actions/choices/locks/source-work
  services and receipt/action delivery. Reserved `scenes`, `gm` and `handler`
  packages do not implement the Director. The existing summary service remains
  unchanged and record-review-only; real inference needs an external-work boundary
  outside database writer transactions.
- [One next work order](../docs/work_orders/P2_DIRECTOR_OBSERVATION.md) freezes
  P2-D1: synthetic Activity input → scoped durable eligible batch, one supported
  actual completed-Play source, claim/ack/restart and narrow integrity evidence.
  Later knowledge/chronology, shadow decisions, live capabilities and Handler
  initiative remain separately scoped work. Historical M4–M7 labels do not
  renumber the current P1/P2/P3 plan or certify earlier milestones.

Updated active instructions, workflow, roadmap/queue, Activity work order and
existing assistance handoff to point to the canonical design. The original
hash-verified planning package remains unchanged. No duplicate runtime Director
framework, inferred AI actor authority or fake publication adapter was added.

## Actual validation and limits

`git diff --check` passed. A local relative-link check passed for changed Markdown
documents. `verification/verify_handoff.py` passed: 34 required files, 86 planned
cases, four schemas/four synthetic fixtures; planning verification only.
`tools/check_repository.py` passed before this report: 2,071 publishable files,
40 manifest entries, zero findings. A final check includes this report as well.

`git diff --name-only -- src migrations tests rules config .github pyproject.toml uv.lock`
returned no changes. No runtime code, migrations, tests, rules, dependencies or
workflow configuration changed. Local pytest, Ruff and mypy were not rerun for
this documentation-only checkpoint. The existing CI may select focused gameplay
because the updated integration Markdown is outside its ordinary-doc directories;
that would be existing-source regression evidence, not Director acceptance.

No real conversation capture, model/provider call, bot/worker startup, live
migration, deployment, environment publication or private engine mutation occurred.
Enabled capabilities remain a design decision, not live activation. P1 human
acceptance, broader rules coverage and human Director pacing/fairness remain open.

Remaining dependencies: the Activity task's actual backend/authentication/client
handoff for direct integration; consent/retention/provider/data scope and spending
settings before real capture/inference; actual typed source/action/publication
consumers before autonomy. These do not block the synthetic D1 work order.

Next: implement P2-D1 against its frozen normal workflow and record focused source,
migration, privacy, retry and recovery evidence before opening another unit.
