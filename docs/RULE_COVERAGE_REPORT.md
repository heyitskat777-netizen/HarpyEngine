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
| Bonds and mutual player choices | Book PDF 13 / printed 11, individual playbooks | Private player proposals and mutual setup agreement implemented; NPC/Handler workflows pending. UI uses book “Intense”; sheet terminology discrepancy remains documented. |
| Status hierarchy, unique Ace/Dog | Book PDF 14 / printed 12 | Handler-authorized starting order implemented; Princess first, unique Ace/Dog. In-play changes and benefits pending. |
| Heat and Identity mechanics | Book PDF 10 / printed 8 and relevant Plays | Not initialized or resolved; verify starting Heat explicitly |
| Newgirl Mentor / prior mission discussion | Book PDF 40 | Handler nomination and subsequent mutual proposal implemented (PDF 42 / printed 40); Mentor callsign requests and effective Status comparison implemented; activation/name application and Cadre discussion pending. |
| Oldgen's two NPC Bonds | Book PDF 45 | Exactly two sourced NPC role choices implemented; other Bond mechanics pending. |
| Vatgrown DNA basis | Book PDF 48 | Implemented private player-authored field; creates no Bond/Tag |
| AM jailbroken confidant | Book PDF 54 | Pending Bond choice |
| Bonded Pair and Intense Bond | Book PDF 57 | Private Pair proposal/acceptance and Pair-only Asset naming implemented; owner supplies descriptions. |
| Prince fanbase | Book PDF 61–62, sheet PDF 18 | Implemented two demographics, two demanded and two rejected qualities, with printed custom slots |
| CONSUME hunger track | Book PDF 65 | Three levels recorded; starting value and mechanics pending. |
| JANUS Harpy Core and initial Tags | Book PDF 68 | Versioned distinct unnamed Core baseline with four prescribed Tags implemented; no Core Plays or naming. |
| DoctorDoctor obsolescence | Book PDF 71 | Eight-box capacity recorded; starting marked count and mechanics pending. |
| Red Queen AM roles | Book PDF 88 | Five roles and four-self/one-other default recorded; starting external role/recipient agreement implemented; AM mechanics pending. |
| Optional short-game starting Requisition | Book creation guidance | Not unlocked; verify mode and exact source before implementation |
| Core Plays, modifiers, consequences, pending choices | Original M2 work order | Not implemented; raw M1 rolls remain nonmechanical test receipts |

No automatic starting Heat, numeric Status, Harpy Core state, Bond consent or playable
activation is inferred from catalogue completeness. Independent review and the full
BUILDER acceptance cases remain outstanding. Tests in `tests/test_creation.py` cover
this implemented step; they cannot certify the entire published ruleset.

## M2B source follow-up

Book PDF 61–62 and sheet 18 agree on Prince's five printed demographics, one custom
demographic space, ten printed qualities and two custom quality spaces. The sheet
capitalizes some labels differently; book labels are retained. The fanbase requires
two demographics, two demanded qualities and two rejected qualities. Native selectors
support partial progress and explicit custom slots. Validation forbids a quality
being both demanded and rejected and prevents duplicate custom labels. This
consistency check does not invent a consequence for an invalid form. Custom labels
remain owner-authored descriptions. Demographics are represented as additional
Identities separately from the Girl's four starting Identities; marking, replacing,
demand checks, Permission and Play effects remain unimplemented.

Vatgrown's PDF 48 DNA-basis choice is a private descriptive field. It does not create
a mutual relationship, apply a Tag, or certify another player's consent. Saved JSON
from M2A remains readable with these optional fields absent. Existing private records
are not rewritten. No new database migration is required.

## M2C starting-Bond audit

Book PDF 13 / printed 11 defines Bonds as shared mutual ties, at Personal or Intense
depth. The ten Girl creation pages above were checked for starting player-Bond
requirements and short paraphrased prompt labels. Nine branches support owner
proposals, with Bonded using Intense and the other eight Personal. AM's counterpart
knows she is Jailbroken; this is explicitly disclosed during review.

Newgirl's initial creation page alone is insufficient to determine who chooses the
Mentor. PDF 42 / printed 40 explicitly assigns that choice to the Handler. Her
player-selected proposals are therefore blocked with UNSUPPORTED_RULE. A later
Handler-authorized assignment flow must establish that relationship. The sheet's
“Intimate” wording does not override the rulebook's “Intense” label in this UI.

The new records represent mutually reviewed draft setup agreements only. They do
not resolve Bond weakening/strengthening, Heat, modifier rules, fictional actions,
NPC/Handler control, Mentor duties or Pair Asset authority. Incoming agreements
are not automatically counted as a completed outgoing creation choice; the future
full creation validator must reconcile all starting requirements. Either party
can withdraw OOC setup agreement without performing a fictional Bond Play.

## M2D Handler and NPC source follow-up

PDF 14 / printed 12 gives four Status levels: Handler, Ace, Wings, Dog. Only one
Pilot can be Ace and one Dog; positions are strictly ordered. The Handler assigns
starting order. This delivery records a complete reviewed starting order and enforces
Princess's starting Ace requirement (PDF 31 / printed 29). A one-Pilot Cadre cannot
receive two distinct endpoint labels without an additional rule decision, so setup
returns UNSUPPORTED_RULE. Multiple Princesses likewise require a source/roster
decision. The UI supports 2–25 Pilots. Handler is outside Pilot ranks. This does not
implement in-play shifting, Permissions, orders or Punishments.

Handler appointment is application governance, explicitly confirmed by a configured
administrator; it is not an invented game mechanic. It grants no private character
access. Handler changes clear current setup with a visible confirmation warning.
The Newgirl rule at PDF 42 / printed 40 now authorizes a Handler nomination. That
nomination gates the existing voluntary two-player setup proposal; reassignment
invalidates old consent tokens. The same source also requires Mentor-chosen callsign
and effective higher Status. Those remain pending, not silently implemented as an
automatic rename or roster reorder. Cadre prior-mission discussion is also pending.

NPC choices were checked against each Girl creation page in the source table. Each
has four listed NPC roles; most choose 1–2, Oldgen exactly 2. Dropdown labels are
short paraphrases tied to stable source-order slots. Optional NPC names and feelings
remain private draft descriptions. PDF 13 / printed 11 explicitly allows feelings
to remain unwritten; written feelings are never mandatory. No unstated starting
NPC Bond depth, shared NPC identity, world canon or NPC control behavior is inferred.

## M2E Pair authority and Frame baselines

PDF 57 / printed 55 explicitly delegates two Girl Asset names to the Pair and
descriptions to the Bonded player. The allocation service writes names only, tied
to a current accepted Pair proposal. It reads no private creation body. Owner
descriptions are separately stored with the exact allocation token and validated
against those names on every save. Stale/withdrawn agreements cannot authorize
new choices or replay old allocation commands. Historical records remain immutable.

Frame baseline schema 1 records only these audited facts: PDF 68 / printed 66 gives
a separate unnamed Harpy Core with Drugged, Restrained, Muzzled, Recovering from
Surgery as explicit starting Tags. Naming the Core is prohibited; no name field is
accepted. This is a nested draft entity, not a fully implemented targetable game
character. PDF 71 / printed 69 shows eight obsolescence boxes; PDF 65 / printed 63
defines Quiet, Gnawing, Ravenous. Starting marked-box and starvation values are not
guessed. PDF 74 / printed 72 provides Wyvern's fixed extra Enormous. PDF 88–89 /
printed 86–87 provides Queen, Consort, Knight, Doll, Traitor AM roles and default
four assigned to self, one to another Girl. Actual role/recipient selection and
agreement remain pending, rather than assigning arbitrary characters.

Baselines are generated from verified facts, validated against the selected Frame
and serialized on explicit owner save with schema version and source pages. Old
JSON remains readable. No Heat, Permissions, fictional consequences, Core choices,
AM compulsion or initial unresolved counters are inferred by this delivery.

## M2F Court and Mentor choices

Rechecked book PDF 88–89 / printed 86–87: Queen, Consort, Knight, Doll, Traitor
are the five AM roles. At creation, four belong to the Red Queen pilot and one to
another Girl. The pilot chooses the external role/recipient and the recipient
confirms OOC setup agreement. All five choices are tested, including assigning
Queen externally; no controller permission, marking or compulsory action follows
from setup acceptance. Initial NPC/Handler recipients are excluded because the
creation note specifies another Girl, rather than the later general transfer rule.

Rechecked PDF 42 / printed 40: Mentor chooses Newgirl callsign and always counts
as higher Status. Requests require current Handler nomination plus mutually
accepted Mentor relationship. Mentor authors and Newgirl accepts the draft name;
it is saved for final-sheet activation, with no premature profile/nickname mutation
that would stale the nomination itself. The comparison helper recognizes accepted
Mentor authority in both directions without reordering physical Status. It uses
active Handler and fresh starting ranks otherwise. Unknown/stale or reciprocal
Mentor comparisons return unresolved, not a fabricated favorable result. These
read-only comparisons are not authorization to commit in-play effects.

Other Mentor duties (Off-Duty participation, Punishments and Tag rules) require
later Play/scene services. No such behavior is claimed. Starting resource review,
Cadre discussion, complete sheet validation, activation and independent rules
review remain outstanding.

## M2I creation-review audit

Rechecked book PDF 7/10/13/14/40/42/60/65/71 and corresponding official sheets.
PDF 7 / printed 5 explicitly lists the room/bunk, knife, clothing and neural link;
these are starting-access facts on the private review sheet, without invented Asset
bonuses. PDF 40 / printed 38 requires Newgirl to tell each Cadre member whether
zero or one mission has been shared. Saved declarations now cover current Pilot
counterparts and the appointed Handler, with an explicit owner discussion attestation.
The bot does not claim a private form itself told the table or secured consent.

PDF 13 states that Bonds are mutual. An ordinary Personal-Bond playbook can now
explicitly count a current accepted incoming Personal Bond instead of attempting a
duplicate reverse proposal. Mentor and Pair selection retain their specific roles
and required depths. Incoming Intense is not automatically weakened to Personal;
conflicts that cannot satisfy a small roster remain unresolved. Already-originated
eligible proposals continue to record the source owner's starting choice.

No explicit general starting Heat value or starting CONSUME level was found in the
supplied creation text. DoctorDoctor's eight-box track is visually empty but no
numeric initialization was inferred as an engine rule. The owner explicitly approved
Heat 0, Quiet hunger and 0 marked boxes as campaign defaults. Trusted local policy
records owner approval provenance, separate from Handler-confirmed overrides and
source-backed track facts. The optional initial Requisition at PDF 60 / printed 58
remains excluded in regular mode; the short-game variant is explicitly unsupported.
No gameplay resource pool is initialized by recording these rulings.

`/character review` checks saved fields and current accepted agreements, full Status
roster, role/depth, Newgirl history and explicit resource rulings. Review snapshots
include received Court roles for recipients as well as the pilot's own allocation.
All values remain draft/private. Complete official creation, NPC depth/initial
marked states, final publication/name application, playable activation and runtime
mechanics still require independent review/implementation. See
`docs/M2_RULES_REVIEW_PACKET.md`. Complete-builder acceptance stays NOT_RUN.

## M2J additional mandatory playbook audit

The next-pass source audit found creation requirements outside the first Assets/
Bonds page. Book PDF 32 / printed 30, sheet 6: Princess selects one standard, a
bonded Girl selects one, Handler selects one; the Handler's counts as an order.
The source does not require distinctness across these three roles. Native choices
retain role attribution and private owner review, including the custom source slot.
No order or compulsory consequence runs during draft setup.

Book PDF 46 / printed 44, sheet 11: Oldgen selects two maxims. Book PDF 49 / printed
47, sheet 12: Vatgrown's Handler and starting NPC Bonds are Investors; each has one
or two desires, with the Handler choosing its own. Owner chooses NPC-role desires;
the Handler authors its own request without needing a fictional Pilot sheet.
Removing an NPC role filters incompatible current choices, preserving prior history.

Book PDF 82 / printed 80 explicitly says CHANGELING's starting bonded characters
have Psych Strings. Draft review anchors now include every current accepted player
Bond plus selected NPC roles. NPC anchors remain owner-local role references, not
new world-canon NPC IDs. The sheet's shortened rule is not used to erase the book's
explicit starting note. No Psych String use/control or Bond-depth mechanics run.

Book PDF 44 / printed 42 lists Casualty's nine body parts. PDF 58 / printed 56 gives
Bonded the protected Paired Identity Hers. These facts appear on the owner review.

The owner separately approved unmarked Identities/maxims, undamaged Assets/body
parts, Personal NPC Bonds, 0 Permissions, no acquired Requisitions and no extra Tags
as campaign defaults, retaining printed exceptions. They are stored as trusted
owner-approved policy and private review inputs, not asserted to be numeric defaults
printed in the book. No fictional resources are automatically initialized.

Review source version 2 adds these checks; version 1 remains readable history.
Independent full-source review and playable activation remain pending. Earlier
implemented-step checks were not certification of these formerly missing branches.

## M2K pilot runtime subset

Activation now initializes versioned canonical pilot state from current complete
saved review input, with explicit public fields and no reactivation reset. Core
Heat/Identities/Tags/Bonds/Status and the five rolled Plays are implemented; Receive
Orders and the selected Handler briefing are diceless. The registry records source
pages, tiers, supported exceptions, interface contracts and executable test symbols.
See `M2_REVIEW_HANDOFF.md` for exact scope and unsupported rules. Independent review
and human playtest are pending. No complete published-rule claim is made.
