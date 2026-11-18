# P2 Handler pacing rehearsal

The Handler participated in bursts when the scene called for her. Across four
100-input scenes, Anchor delivered 14 contributions, including 10 with an
action of her own. She answered four direct questions. Six interventions
followed a new scoped operational report or briefing, two answered indirect
requests, and two addressed open concerns after the original pilot responded.
Two contributions completed native Handler Plays.

| Scene | With reviewed needs | Automatic needs only | What happened |
| --- | ---: | ---: | --- |
| Barracks | 3 / 100 | 2 / 100 | Anchor sorted seals alongside a pilot and made room at the bench when a test buzzer got stuck. The quiet opening about the alarm went unanswered in both runs. |
| Hallway | 4 / 100 | 4 / 100 | Anchor acknowledged the limits of her information, delivered a native briefing, and marked an unknown reflection. The reviewed run followed through when it was identified. The automatic run logged the tactical update with a generic acknowledgment. |
| Simulator | 4 / 100 | 3 / 100 | Anchor stayed at her console while a pilot chose what to do, accepted the pilot's refusal, and used **Place an expectation on them** to record the check-in before a reset. The refusal was silent without review. |
| Debrief | 3 / 100 | 2 / 100 | Anchor turned over her own recorder and made time for a private conversation. She retained the original report alongside its correction. The invitation to sit was missed without review. |

Both versions used GM review before delivering generated dialogue and actions.
The automatic column disables explicit **need** review. The inputs and their
knowledge disclosures are paired across versions. With reviewed needs, 386 of
400 inputs produced no Handler reply. Each scene had a continuous pause of
46–56 inputs. The hallway had three interventions from turn 38 through turn 46.
The simulator had a reply to an indicator report on turn 33 and a follow-up
on turn 35. That clustering read well against the quiet stretches. The rate
reflects the number of authored opportunities and the deliberately long routine
stretches. A fixed replies-per-message target would ignore why she is there.

## What felt like a person

- **Barracks, turn 22.** “Slide that box over. I'm lousy at sorting by colour,
  but I can read tiny numbers.” Anchor takes a stool and turns the label tray
  toward the light. Only the addressed pilot receives and learns the contribution.
- **Hallway, turns 29–30.** A pilot privately sees a violet strip. Anchor tells
  the other pilot, “I haven't had a report from behind it. I can wait here with
  you.” She has something personal to offer within her actual knowledge.
- **Simulator, turn 35.** “Then stay in the seat. I can take my copy of the
  checklist to the control desk when you're ready.” Her proposed action
  changes after the pilot declines. The pilot retains control of her seat
  and her next action.
- **Debrief, turn 39.** “I'll keep the first account beside your correction.
  You came back to tell us. That matters.” Anchor recognizes what it cost to
  correct the record, with no change to the pilot's Status.

The automatic condition produced 11 replies of which six included an action.
It missed three conversational openings and lost the specific follow-through
on a fourth. Both automatic branches left the original concern open. Both
reviewed branches closed it on delivery. The barracks line about still hearing
the alarm is the clearest remaining gap. It was an actual heard report with
no request, operational trigger, or open concern. An optional acknowledgment for
personally relevant moments would help. It should require a real lead from
what the Handler heard and stay suppressible when the table is carrying the
conversation. Keep the existing quiet windows and assess openings with human
readers before setting any pacing target.

## Four-mission campaign

The 601-input continuity run delivered 54 Handler replies, or 9.0%. Of these,
49 answered direct questions and five volunteered an operational update with
an action. Anchor completed two native briefing Plays. The fixture used only
11 distinct reply texts across the whole campaign. Most of the extra traffic
was objective and limits readback. That higher rate felt more like a briefing
desk than the quieter scenes where Anchor acted alongside the pilots.

All four missions reached a final outcome, including a failed extraction. Both
Off-Duty periods completed, 17 native pilot receipts were recorded, and no
native choices remained pending. The role audit detected zero of the six tested
private content fragments, and reopening and replaying added no events.

## GM boundary

The four scenes generated two visible GM route decisions. A Check Your Sensors
declaration was referred to the native Play. A question about whether a
correction costs Heat received a generic Play-workflow referral and no specific
cost ruling. Neither message advanced the fiction or spent anything. Every
published in-character contribution in these four scenes came from the Handler.
The GM engine should surface specific structured rule answers where supported
and keep any approved outcome readback in the rules/results surface. The
Activity should use the GM route decision to hide the routine WAIT records.
The sustained run also exercised 13 approved outcome readbacks tied to native
receipts. Its GM judgments were typed, fixture-authored inputs to existing owner
confirmation workflows.

## Reproduction and scope

Run `.venv/bin/python tools/playtest_handler_pacing.py --scene barracks
--directory var/NEW`. Scene names are `barracks`, `hallway`, `simulator`, and
`debrief`. Add `--without-need-review` for the automatic condition. Each scene
exports its marked transcript and routing events. Both versions exercise actual
routing, source scope, GM review, Handler preview and delivery, and the existing
native confirm workflow for the two Plays. The words, knowledge acquisitions
and review decisions are authored fixtures. They show how this voice fits the
engine and where the gate misses documented opportunities. They do not measure
live model judgment or human-table pacing. Model calls and cost were zero.

- [Barracks transcript](../var/p2-handler-pacing-barracks-20261117/transcript.md)
- [Hallway transcript](../var/p2-handler-pacing-hallway-20261117/transcript.md)
- [Simulator transcript](../var/p2-handler-pacing-simulator-20261117/transcript.md)
- [Debrief transcript](../var/p2-handler-pacing-debrief-20261117/transcript.md)
- [Paired routing counts](../var/p2-handler-pacing-paired-20261117.json)
- [601-input campaign transcript](../var/p2-handler-pacing-control-20261117/campaign-transcript.md)
- [601-input campaign role audit](../var/p2-handler-pacing-control-20261117/independent-artifact-audit.json)
