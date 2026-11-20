# P2 Handler archetypes in a matched relay mission

Seven isolated campaigns ran the same relay calibration mission on HarpyEngine
`51860070f9bc6429cf8df08dded5f0894d0c257e`. Each activated an original Handler
sheet with the corresponding playbook and used two synthetic Pilots, Lark and
Kite. Each run exposed all seven shared Handler Plays, completed a reviewed
**Brief Them on the Situation**, and resolved the same Pilot-owned **Keep Your
Head**. The mission closed through the normal rewards and discipline workflow.
The Scientist’s lab work used the following Off-Duty period.

| Handler | Where the optional response opened | Delivered fixture line | Verified signature mechanic |
| --- | --- | --- | --- |
| Mistress | Cooperation and the personal opening | “You stayed for both lists. Bring yours here so I can sign it myself.” | **Catch More Flies With Honey.** Kite answered an Order immediately, accepted the offered Status increase, and became Ace. |
| Dogrunner | A reported mistake | “Whose initials are on that total? Bring me the original sheet.” | **Dress Them Down.** The reviewed offer linked the earned native grant. Lark lost Status and received the Tag for becoming the Dog. |
| Scientist | A replicated reading | “Good. Leave both instruments in place. Record the conditions beside the reading.” | **Head to the Lab.** Both original participants attested. The lab restored an existing Void-touched Girl Asset, installed a new Void Asset, and recorded the Project step. |
| Frantic | One technician for two consoles, and the personal opening | “One tech. Two releases. Hold the second console. I'll ask for a new slot.” | **Break Down.** The saved total was 9, including three operational bases. Kite confirmed finding the Handler. The Play queued two discipline obligations. |
| Insurgent | Foundation pressure to name dissenters | “Readings and time on this channel. Keep the Pilots' names at your desk.” | **Rebel Sympathizers.** Lark’s native Disobey succeeded. The Handler confirmed the witnessed lapse, producing the private Surveilled Tag. |
| Trainer | A procedure out of order | “Read me the isolator step first. We will run the sequence from there.” | **Conditioning Phrase.** The installed Speak opened Kite’s private answer and the Trainer’s hearing confirmation. |
| Advocate | A supervisor answering for a Pilot, and the personal opening | “You had the floor. If you still want to answer, tell me which route you chose.” | **Get Them Alone.** Lark supplied her own answer in the two-person scene. The resulting private Tag and Order used their native owners. |

## Where the voices overlap

All three of these Handlers replied when Lark said the stopped alarm was still
in her head. The different replies illustrate how the profiles can share a cue.

- **Mistress** offered proximity to her own desk. “You can stay by my desk a while. I'll keep the door open.”
- **Frantic** offered immediate relief from one demand. “Right. Alarm's done. I'll hold the line. Take off your headset if you want.”
- **Advocate** let Lark decide whether to stay on comms or talk privately. “Do you want a minute off comms? I'll stay if you'd rather talk.”

The matched deck had eight cue opportunities and two routine lines per run.
The engine delivered ten optional replies across 56 cue opportunities. The 46
other cue/Handler pairings and all 14 routine turns stayed silent. Matching cues
also waited before review, and none of the seven private inputs created a draft.
The approved dialogue was visible to the addressed Pilot. The bystander could
not retrieve it, and the Handler packets excluded the unreported private input.

The mechanical differences were clearest when a signature changed what an
original player could do next. The optional responses still rely on a reviewed
cue to open. The spoken lines were authored offline fixtures. These runs cover
one signature workflow per archetype. Dogrunner also exercised the Director
offer-to-grant path. The other signatures used their native triggers, scene
controls or owned follow-through. Production model voice, autonomous cue
recognition, additional signature branches, and real-player pacing remain open.

## Reproduce

The matched test writes each cue decision, fixture reply, and native result to
stdout. The existing shared-Play check separately completes all seven basic
Handler Plays. Both use disposable databases and offline fixtures.

- Matched missions **7 passed in 56.42 seconds**. [Results](../var/p2-handler-archetype-missions/matched-missions.xml)
- Shared Play completion **7 passed in 15.46 seconds**. [Results](../var/p2-handler-archetype-missions/shared-plays.xml)
- Follow-up checks of the Scientist’s Asset change, Insurgent’s Tag audience, and Advocate’s private Order **3 passed in 27.19 seconds**, overlapping the matched missions. [Results](../var/p2-handler-archetype-missions/effect-assertions.xml)

```sh
PYTHONPATH="$PWD/src" python -m pytest -q -s tests/rules/test_p2_handler_archetype_missions.py
PYTHONPATH="$PWD/src" python -m pytest -q tests/rules/test_director_handler_play_examples.py -k every_basic
```

[Matched mission test](../tests/rules/test_p2_handler_archetype_missions.py) · [Shared Handler Plays](P2_HANDLER_ALL_PLAYS.md) · [Handler profiles](P2_HANDLER_CHARACTER.md)
