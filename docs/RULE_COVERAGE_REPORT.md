# Creation source audit — first M2 step

Reviewed against the two owner-supplied official PDFs on 2026-11-03 UTC.
This is the implementing agent's bounded source comparison, not the independent
review required for complete creation. Sources remain outside Git; only short
choice labels, factual constraints and page references enter the bot repository.

| Source | SHA-256 |
|---|---|
| GIRL_FRAME_rulebook.pdf, 205 PDF pages | `0f8dbaae7f0a254cdbfb4856b9f50c44fd31a97b36234062db4ae7f4874b55f0` |
| GIRL_FRAME_official_sheets.pdf, 56 PDF pages | `ac501a049163826d2cfd804cd6f5ed68602c689c7e87fb153f183a661b1c48d3` |

PDF pages below are one-based. Printed book pages are two less at these verified
anchors; do not apply historical approximate offsets without checking the source.

| Playbook | Book PDF / printed | Sheet PDF |
|---|---|---|
| Princess | 31 / 29 | 6 |
| Mockingbird | 34 / 32 | 7 |
| Stim-Blissed | 37 / 35 | 8 |
| Newgirl | 40 / 38 | 9 |
| Casualty | 43 / 41 | 10 |
| Oldgen | 45 / 43 | 11 |
| Vatgrown | 48 / 46 | 12 |
| Alpha | 51 / 49 | 13 |
| AM | 54 / 52 | 14 |
| Bonded | 57 / 55 | 15 |
| The Prince | 61 / 59 | 18 |
| CONSUME | 65 / 63 | 19 |
| JANUS (also JANUS-B label) | 68 / 66 | 20 |
| DoctorDoctor Mk. II | 71 / 69 | 21 |
| Wyvern 0.4 | 74 / 72 | 22 |
| The Enforcer | 78 / 76 | 23 |
| Changeling | 81 / 79 | 24 |
| Project Ankou | 84 / 82 | 25 |
| The Red Queen | 88 / 86 | 26 |

`engine/creation_catalog.py` records these anchors and 171 short starting-choice
labels: 50 Girl Asset options, 40 Identities and 81 Frame Asset options. Comparing
normalized source text found one abbreviation: Prince's book says Onboard AM
(Artificial Mind), sheet 18 says Onboard AM. The catalogue retains the book label.
Other labels matched corresponding sheets after whitespace/typographic normalization.
This comparison checks names, not every rule attached to an Asset or playbook.
The owner explicitly approved official JANUS rules with the JANUS-B server label.

## Implemented starting choices

Book PDF 7 / printed 5 establishes Girl/Frame selection, two Assets from each,
four starting Identities, callsign and appearances. The builder derives the four
Identities, allows up to two distinct legal choices per family in a partial draft,
and reports missing choices/descriptions/appearance. It does not make a completed
first step a playable sheet. Basic issued equipment is not counted as a selected
Asset. Book PDF 15 / printed 13 gives ordinary later Asset capacity (four Girl,
five Frame); this step only selects starting Assets, not later capacity mechanics.

Mockingbird chooses exactly one of her selected Girl Assets as Void-altered.
Wyvern has an additional Enormous Asset outside normal slots. Bonded's Pair chooses
her Girl Assets, so the owner-only first step leaves that selector disabled and
reports the relationship step as pending. No AI or administrator chooses for her.

## Required later work and unresolved coverage

| Requirement | Source anchor | Current state / next work |
|---|---|---|
| Bonds and mutual player choices | Book PDF 13 / printed 11, individual playbooks | Pending authorized multi-user workflow; reconcile sheet “Intimate” vs book “Intense” wording |
| Status hierarchy, unique Ace/Dog | Book PDF 14 / printed 12 | Pending Handler-authorized assignment; Princess starts Ace |
| Heat and Identity mechanics | Book PDF 10 / printed 8 and relevant Plays | Not initialized or resolved; verify starting Heat explicitly |
| Newgirl Mentor / prior mission discussion | Book PDF 40 | Pending relationship/context step |
| Oldgen's two NPC Bonds | Book PDF 45 | Pending Bond validation |
| Vatgrown DNA basis | Book PDF 48 | Pending player choice |
| AM jailbroken confidant | Book PDF 54 | Pending Bond choice |
| Bonded Pair and Intense Bond | Book PDF 57 | Pending Pair consent and Pair-selected Assets |
| Prince fan demographics | Book PDF 61 | Pending choice of two demographics |
| CONSUME hunger track | Book PDF 65 | Pending special-state audit; do not infer starting value |
| JANUS Harpy Core and initial Tags | Book PDF 68 | Pending distinct Core record and prescribed Tags; pilot does not author Core choices |
| DoctorDoctor obsolescence | Book PDF 71 | Pending eight-box track |
| Red Queen AM roles | Book PDF 88 | Pending five-role allocation |
| Optional short-game starting Requisition | Book creation guidance | Not unlocked; verify mode and exact source before implementation |
| Core Plays, modifiers, consequences, pending choices | Original M2 work order | Not implemented; raw M1 rolls remain nonmechanical test receipts |

No automatic starting Heat, numeric Status, Harpy Core state, Bond consent or playable
activation is inferred from catalogue completeness. Independent review and the full
BUILDER acceptance cases remain outstanding. Tests in `tests/test_creation.py` cover
this implemented step; they cannot certify the entire published ruleset.
