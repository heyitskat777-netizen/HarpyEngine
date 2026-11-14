# ANKOU Emotional Relay reconciliation — r270

Read-only audit, 2026-11-13, against recovered r269/v38 source. The five audited source/test files byte-match the verified r270 candidate recovery. Printed pp83–84 (PDF85–86) freshly read from the authorized retained rulebook, SHA-256 `0f8dbaae7f0a254cdbfb4856b9f50c44fd31a97b36234062db4ae7f4874b55f0`. No tests executed by this reviewer; this is not whole-type or release certification.

## Ordinary effects and immediate consequences

`src/girlframe/services/m3_ankou.py` implements original-owner activation with exactly two distinct benefits and original Handler consequence choice (699–821). The benefit consumers are real: first-against dominant emotion becomes a Tag (977–991, 2361–2380); speech is private recipient delivery (1205 onward); interruption erases a real acting-person Tag and requires an actual child Play, with decline preserved (2748–2805); touch damages a real owned Asset before actual Helplessness (1249–1320); sensing returns vague same-square locations, with concealed identities remaining unnamed (2952–2977).

Handler consequences are not mere acknowledgments. The NPC-death hook creates owned Identity-erasure work and four Heat while inside the Frame, or a durable Helplessness cause outside it (2259–2295; 996–1002). Intense partner nominations are individually owned and may pass; completed nominations produce a required actual selected Play, or complete when nobody nominates (782–815, 992–995, 1157–1188; `m3_ankou_feedback_sequences.py` 660–737). Feedback choice starts a real sequence (765–778). Scene expiry ends the Relay rather than indefinitely preserving its benefits (2451–2460).

## Evidence classification

Implemented with authored evidence is not newly focused-tested. `tests/rules/test_ankou.py::test_relay_actual_head_speech_touch_and_same_source_asset_cost` covers speech and real touch/Asset cost, but selecting the nominees consequence there does not establish actual Intense nomination-to-child completion. The nearby interrupt-decline test provides separate authored evidence. This audit found no tests for a real Intense nomination/required performance lifecycle or NPC-death Identity/Heat versus outside-Frame Helplessness consequence. These are targeted evidence gaps, not absent entire workflows.

## Uncertainty and finite support

Nomination eligibility currently uses actual Bond depth == 2 (service around 792). Obsessive grants directional effective Intense benefits even without an actual Bond; `engine/m3_ankou.py::effective_intense` represents that and is used by other ANKOU consumers. Whether the Relay's optional nomination consequence belongs to those effective benefits is a printed-rule interpretation question, not an established runtime mismatch. Resolve it explicitly and test the resulting owned nomination route before claiming coverage; do not silently change symmetric Bonds.

`m3_ankou_support.py::range_people` enumerates current sheet actors, Handler and living NPCs, not independent Clone AM actors. Treat that as a finite actor-support limitation requiring separate lifecycle/rules work, not proof that ordinary pilot Relay is absent.

No production changes, registry approvals, live Discord, AI Director, final privacy audit, full regression, process restart or backup/restore validation were performed in this audit. Existing integration/access and final-candidate gates remain.
