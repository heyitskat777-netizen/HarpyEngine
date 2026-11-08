# Independent creation-rules review packet

Status: READY FOR REVIEW MATERIALS, NOT CERTIFIED. Complete-builder independent acceptance remains NOT_RUN. Activation and the M2 pilot
subset are implemented behind a trusted approval gate; see M2_REVIEW_HANDOFF.md. Review this sanitized code,
tests and the separately supplied official PDFs; no real campaign sheets are needed.
A saved player review snapshot is not an independent source/code review.

## Evidence and source map

| Requirement | Official anchor | Implementation and evidence |
|---|---|---|
| Creation, starting access and introductions | Book PDF 7 / printed 5 | `engine/creation.py`, `creation_review.py`; selected Assets/descriptions/appearance, starting-access facts |
| Identities and Heat | Book PDF 10 / printed 8 | Four source-backed Girl Identities; Prince additional demographic Identities remain distinct; no runtime marking/Heat initialized |
| Mutual Bonds and depth | Book PDF 13 / printed 11; Girl creation pages in catalogue | `services/bonds.py`, `creation.py`, `creation_review.py`; participant agreement, explicit incoming choice, exact role/depth; no weakening/elevation |
| Starting hierarchy | Book PDF 14 / printed 12; Princess PDF 31 / printed 29 | Handler appointment/rank and current-roster validation; unique Ace/Dog, Princess first |
| Newgirl declarations and Mentor | Book PDF 40/42 / printed 38/40 | Per-counterpart zero/one missions, owner discussion attestation, Handler nomination, mutual agreement and accepted name; no fabricated conversation |
| Pair authority | Book PDF 57 / printed 55 | Pair selects names; owner describes; current provenance required |
| Optional initial Requisition | Book PDF 60 / printed 58 | Regular mode excludes optional initial Requisition; short-game option explicitly unsupported |
| CONSUME and DoctorDoctor tracks | Book PDF 65/71 / printed 63/69; sheet PDF 19/21 | Track labels/capacity verified; 0 Heat / Quiet / 0 boxes are owner-approved campaign defaults, not claims of explicit printed defaults |
| Court and separate Core | Book PDF 68/88–89 / printed 66/86–87 | Separate unnamed Core and prescribed Tags; exact five-role/four-one Court allocation, recipient role visibility, no controller mechanics |
| Additional mandatory choices | Book PDF 32/46/49/82; sheets 6/11/12/24 | Princess own/bonded-Girl/Handler standards; Oldgen two maxims; Vatgrown NPC and Handler desires; CHANGELING draft Psych Strings |
| Other playbook-specific fields | `docs/RULE_COVERAGE_REPORT.md` and `engine/creation_catalog.py` | Source-linked asset/Identity catalogues, NPC role counts, Mockingbird Void choice, Wyvern extra Asset, Vatgrown DNA and Prince fanbase |

The owner approved the three starting-resource campaign defaults in this development
conversation. The owner also approved unmarked Identities/maxims, undamaged Assets/body parts,
Personal NPC Bonds, zero Permissions, no acquired Requisitions and no extra Tags,
with printed exceptions preserved. Trusted policy records owner approval without forging a Discord actor
or Handler confirmation. Appointed Handler overrides remain explicit, versioned
and separately labelled. No startup change writes fictional resources.

`tests/test_creation_review.py` covers every Girl branch, every Frame plus JANUS-B,
mutual incoming choice, role/depth rejection, missing dependencies, current source
provenance, stale profile/roster/relationship data, private projection, explicit
campaign rulings, immutable snapshots, replay, concurrency, rollback, actual backup
restoration and native fake-adapter controls. Full evidence: `reports/M2_ACCEPTANCE.md`.
No offline test certifies unpublished assumptions or human Discord behavior.

## Required independent decision before playable activation

- Check the exact official PDF versions/page anchors and reconcile all supported
  creation branches against the book/sheets, including any remaining terminology
  discrepancies (such as sheet “Intimate” versus book “Intense”).
- Review the owner-approved initial-state rulings and their printed exceptions.
  Confirm the extra Princess/Oldgen/Vatgrown choices and CHANGELING anchors against
  their full source clauses. Review sheets record these as draft inputs, without
  initializing canonical resources or executing any Play.
- Review conflicting starting Bond depth/role cases. An incoming Intense Pair Bond
  is not silently downgraded to satisfy a different playbook's Personal requirement.
  Small-roster conflicts remain unresolved rather than invented away.
- Decide the final public/private sheet projection and explicit publication of the
  creation introductions. Private builder descriptions are not automatically public.
- Review the final Newgirl name/profile update so applying the approved callsign
  cannot invalidate its own nomination, Status or relationship provenance.
- Record reviewer identity, date, source versions, findings and an explicit decision.
  Resolve findings in code/tests before changing any certification/activation gate.
- Implement and verify transactional playable-sheet activation, gameplay-service
  consumption, restart/rebuild and a two-player native-client creation walkthrough.
  These are acceptance gates, not approval granted by saving a player snapshot.

## Play prerequisites retained

The original M2 Play work order still requires a verified subset, durable pending
actions, pre-roll choices, immutable receipts, exact result-tier response ownership,
Heat/Identity/Tag/Status mechanics and resume/recovery. The scene-chat lock extension
has its own LOCK-01–12 cases. No `/play` or automatic lock is enabled by this work.
AI and recovered-engine writes remain deferred. A review cannot grant player consent
or substitute a guessed rule for an unsupported branch.

M2J source audit corrected gaps in the earlier creation checklist. Source-version-1
reviews do not constitute verification of the new mandatory choices. Their history
remains readable; current version-2 readiness must be checked afresh. New evidence
is in `tests/test_creation_coordination.py` and `docs/acceptance/m2_playbook_creation.json`.

## M2K review update

The implementation requested above now exists and has synthetic automated evidence.
`M2_REVIEW_HANDOFF.md` supersedes earlier implementation-pending descriptions in
this packet. Independent certification remains absent. Review the canonical source,
source registry, gameplay tests and official PDFs before approving the digest.
The owner ruled that Intense retains Personal's ±2 Tag adjustment. That is an
explicit campaign interpretation, not a claim that the printed text resolves it.
