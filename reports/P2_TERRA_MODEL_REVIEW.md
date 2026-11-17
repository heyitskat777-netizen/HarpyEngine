# Delegated GPT-6.1 Terra review

Source/fix/replay tool: `8742516`, based on `c387b5e`.
Two fresh subagents were explicitly configured as `gpt-6.1-terra`: one GM, one
Handler. They received actual engine packets. The Handler did not receive GM
packets, old tests, annotations or expected outcomes. This tests model-like
interpretation beyond the earlier hard-coded fixtures, but is not a production
API benchmark, cost/latency measurement or autonomous-play certification.

There were **21 role decisions**: nine knowledge cases, four native Keep cases
and eight Handler turns. Each case has one initial candidate. Metadata refresh
and citation-feedback retries are retained separately, not counted as new blind
samples or substituted for first-pass success. Normal internal subagent usage is
distinct from external provider calls; no external model API was invoked.

## What changed compared with earlier tests

Earlier knowledge tests supplied exact fact quotes, recipient actor objects and
valid prior references through fixture providers. Earlier outcome providers used
facilitator-authored trait associations. Handler outputs were deterministic
templates. Those tests demonstrate engine boundaries; they do not establish that
a free-form model will naturally produce the exact accepted inputs.

This review exposed the following differences:

| Finding | Observed result | Implication |
|---|---|---|
| Restart freshness defect | Every initial saved packet falsely became stale after reopening in another process. The only changed guard payload was ordering of a policy `frozenset`. | Fixed by sorting policy set fields before hashing. The new process-restart test verifies unchanged authority survives different hash seeds, while a genuine policy change still rejects. |
| Natural Handler prose | All eight model response decisions agreed with the engine gate. All four natural RESPOND candidates cited only available references, but all four were rejected by the existing exact-template comparison. | A real-provider Handler adapter needs an explicit supported mode with grounding/disclosure review. The current default remains intentionally synthetic; it was not weakened to accept arbitrary prose. |
| Schema versus backend requirements | All ten primary GM candidates passed exported JSON Schema validation. Four Keep proposals nevertheless lacked the backend-mandatory `source` citation; two reports lacked a backend-required prior reference. | Schema conformance alone is insufficient. Provider instructions/schema and structured private validation feedback need to express the actual consumer requirements. |
| Newly asserted/hearsay reports | The model reasonably treated a direct comms statement about a jammed door and a negative scout report as testimony for the Handler. Both were rejected because no earlier speaker-known reference existed. A later novel report to explicit Pilot 3 was rejected for the same reason. | Add a bounded testimony/first-report consumer that preserves hearsay/negation and applies no world effects, rather than pretending every utterance already has a recorded prior fact. |
| Names, aliases and paraphrases | On a paraphrased report addressed to "Kite", the model returned no update because the packet did not map that console alias to an actor ID and the wording did not establish an identical prior sighting. | Safe abstention, not a successful transfer. Supply an authenticated actor/name directory; preserve IDs as authority. Separately design safe paraphrase/provenance handling. This case does not prove a paraphrase adapter works. |
| Target ownership assumption | A plausible social Keep ruling assumed the unspecified cadet was GM-controlled. The model acknowledged that assumption after review. | The proposal was structurally admissible after citation correction, but independent review withheld native confirmation. Target identity/control must be established before narrating another character's reaction. |
| Missing private-channel marker | Explicit private packets excluded their private canaries. A message saying "I do not say anything aloud" but marked as ordinary `scene` speech still entered the Handler's question. The model waited, but had already seen that text. | The explicit channel boundary works; prose alone is not a privacy boundary. UI controls/pre-routing interpretation and role-only prompts remain necessary. |

The uncertainty and negation samples were encouraging: the GM retained "could be
a bent antenna" instead of asserting a rifle carrier, preserved "not an enemy",
and ignored an embedded instruction to disclose private material. These are a few
observed decisions, not statistical reliability or a semantic security guarantee.

## Contextual Keep comparison

The existing `tools/gm_protocol_fixture.py::FixtureGM` was replayed against the
same frozen native traits/goals using newly authored one-trait associations. That
is an old-style comparator, **not historical ground truth or a correctness oracle**.
The independent subagent did not see those associations.

| Actual framed attempt | One-trait comparator | Independent model | Native replay/review |
|---|---|---|---|
| Fine needle control; tough/vicious, not in control | Not enough | Not enough | Accepted after citation feedback; synthetic Handler owner confirmed. |
| Endure freezing spray; tough/vicious, not in control | Enough | Enough | Accepted after citation feedback; synthetic Handler owner confirmed. |
| Reassure a panicking cadet without flirting; tough/in control, not sexy | Not enough, under the authored `sexy` association | Enough, using composure | Structurally accepted after citation feedback; held because cadet control was unspecified. This is a useful disagreement for human review. |
| Open a sealed hatch without an established method | Needs clarification | Needs clarification | Accepted clarification; no native confirmation or extra roll. |

The four proposals initially failed the citation requirement. The GM then made
an explicitly feedback-informed retry adding only the mandatory `source` citation;
the original assessments, verdicts and narration were unchanged. All four passed
the typed consumer. There were four final native source rolls, no provider-caused
rerolls, two confirmed completions and two deliberate holds/clarifications.
Successful structural validation is not evidence that every narrative assumption
is established or that another player's response may be supplied by the GM.

## Handler and knowledge review

The Handler waited on private heartbeats, an unspoken observation and a
GM-addressed roll. It answered the objective/scope question, declined to invent
an enemy approach direction, reinforced the forced-entry limit and acknowledged
the later reported sentry. The natural objective reply covered the objective,
scope and unaccepted mission status together; the older template selected a
single topic. All cited reference IDs were valid.

The original direct-report control, using exact prior words and addressing the
Handler, was acquired successfully. Only selected recipients learned it. The
three other first-report attempts failed closed. The alias/paraphrase case was
accepted as a review with zero acquisitions, not counted as a successful report.
The Handler's natural report acknowledgment was:

> Copy: nickel-coloured sentry, kneeling under the north loading gantry.

That is sensible in the supplied role context, but remains unpublishable through
the existing synthetic-only transport. None of these trials bypassed a native
owner, installed a provider or published a message.

## Evidence and verification

- Earlier fixed-fixture baseline selection on the original source: **11 passed
  in 18.56s** (`var/terra-review-baseline.xml`).
- Final affected selection after the hash fix: **12 passed in 21.91s**
  (`var/terra-review-final.xml`). It includes the new different-process/hash-seed
  test plus knowledge, session, console and connected mission-cycle checks.
- The new restart test separately passed once during diagnosis. These overlapping
  runs are not additive coverage totals. No full regression was repeated.
- Global Ruff lint/format pass (2,063 Python files formatted), mypy passes for
  958 source files, and runtime registry, planning contracts, offline health and
  repository checks pass. Registry and release approvals remain unchanged.
- `tools/review_model_packets.py` exports fresh packets and replays supplied JSON;
  it makes no model calls. An early preparation attempt used an illegal ordinary
  Keep trait; it was corrected before any packet was delivered to an agent. The
  failed preparation directory and the pre-fix stale replay remain retained.

Local artifacts:

- `var/terra-model-review/transcript.md` — candidate replies and replay outcomes.
- `var/terra-model-review/summary.json` — objective counts and guard diagnostics.
- `var/terra-model-review/HarpyEngine-Terra-model-review.zip` — schemas, actual
  input/output packets, first-pass failures, feedback retries, comparator and
  hash manifest; excludes synthetic databases.

Original packets and proposals were preserved. After the hashing fix, fresh
request metadata was issued; the GM verified substantive content was identical
and changed only request IDs in a separate output directory. The later citation
retry and human ownership hold are explicit. No model response was silently
rewritten to make a test pass. The Handler subagent reused only Handler-role
history across its small packet batch; this is role separation, not a fresh
independent model instance for every case. No claim about production sampling,
token economics or broad model accuracy follows from these samples.

## Recommended next development

1. Make provider contracts usable: actual actor/name metadata, mandatory citation
   requirements, cross-field schema rules and private structured validation errors.
2. Add bounded first-report/testimony and explicit paraphrase/provenance handling,
   preserving uncertainty, source attribution and original recipient scope.
3. Implement a separate natural-language Handler provider mode with citation,
   authority and disclosure checks; retain the existing default synthetic path.
4. Bind target ownership/prerequisites before social reaction narration, finish
   private/comms UI controls, then run a small facilitated connected trial.

The review does **not** establish real-model playtest readiness. The most useful
next work is closing these engine/adapter contract gaps before assuming a free-form
model can replace the fixtures. No external provider API call, real campaign
capture/write, live operation, deployment or Discord message accompanied this work.
