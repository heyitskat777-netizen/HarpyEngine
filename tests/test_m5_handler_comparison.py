"""Matched synthetic missions on the reviewed Activity batch path."""

from dataclasses import dataclass

import pytest
from test_activity_shadow_readiness import consent, publish_opening, records
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m5_activity_batch import SECRET, WAIT, deliver_handler, handler_batch_line
from test_m5_activity_batch import relay as relay
from test_session_zero import FACILITATOR

from girlframe.ai.handler_initiative import alternate_initiative, initiative_for
from girlframe.ai.observation import SceneTurn
from girlframe.engine.m3_handler_character import BOOK_RULES, PROFILES
from girlframe.engine.m3_handler_state import PERSONALITIES
from girlframe.services.onboarding import WorkflowError


@dataclass(frozen=True)
class Beat:
    cue: str
    report: str
    offer: str
    action: str
    handoff: str


BEATS = {
    "Mistress": Beat(
        "cooperation",
        "I stayed to finish both labels so Kite could check the line.",
        "You said you finished both labels, Lark. "
        "I can put your name on the extra work, if you like.",
        "I uncap my fountain pen.",
        "Then I'll leave the space blank. You can tell me later if you want it filled.",
    ),
    "Dogrunner": Beat(
        "accountability",
        "I initialed a blank total, then put the sheet back.",
        "Your initials, your correction. I can keep the desk free while you make it.",
        "I draw a line beside the total on my own copy.",
        "All right. You handle the correction. I'll leave the desk to you.",
    ),
    "Scientist": Beat(
        "research",
        "The lamp pulsed twice after we stopped moving. I can't tell if it was the gauge.",
        "Two pulses while you were still. Want me to log that while you see if it repeats?",
        "I open my notebook to a clean page.",
        "I'll leave the second column blank. Tell me what you can actually see when you're ready.",
    ),
    "Frantic": Beat(
        "capacity",
        "I can count the turns or keep my grip. I can't do both.",
        "Keep your grip. Call the gaps if you want me to count.",
        "I put my other headset down.",
        "Kite has the count. I'll keep the spare line clear.",
    ),
    "Insurgent": Beat(
        "institution",
        "The Foundation desk asked for names before they'd hear the fault report.",
        "I can file what happened at the desk. Tell me what you want shared.",
        "I turn my own roster face down.",
        "Your call. I'll keep the names on my side of the desk.",
    ),
    "Trainer": Beat(
        "procedure",
        "I copied my checklist out of order. I've put the second check first.",
        "I can read the sequence back. Where did you last check something with your hands?",
        "I mark the starting line on my copy.",
        "Then start where you're sure. I'll wait for your call before I read another step.",
    ),
    "Advocate": Beat(
        "agency",
        "The desk answered for me. I hadn't finished saying what I wanted.",
        "You didn't get to finish. I can hold dispatch if you want another minute.",
        "I set my pen down.",
        "All right. I'll listen. Come back to me if you want the desk's attention.",
    ),
}

SCOPE_REPLY = "The marked shelf outside the sealed door. Leave the door shut."


def delivered_to(relay, viewer):
    return [
        row
        for row in relay.app.timeline(viewer, relay.scene)["entries"]
        if row["kind"] == "handler"
    ]


def approve(relay, draft, key, *audience):
    return relay.app.write(
        ADMIN,
        key,
        relay.scene,
        "handler-approve",
        {
            "draft": draft,
            "reason": "Reviewed the heard turn and audience.",
            "recipients": list(audience),
        },
    )


def test_advocate_recognizes_distinction_across_heard_reports(relay):
    original = relay.canon_and_time()
    form = (
        "That form gives you one box for two different things. Want me to help find wording "
        "that keeps delivery and relay status apart, or have you got it? "
        "I will leave the pen with you."
    )
    concern = (
        "Sit with me, yes. I want to write this part myself: "
        '"Delivery reported; relay unverified." '
        "Handler, the single box could lose that distinction. I want both parts kept."
    )
    relay.line("private-form", OTHER, form, channel="private")
    relay.line("without-context", PLAYER, concern)
    relay.line("paperwork-banter", OTHER, "This form's single line is crooked again.")
    assert relay.run_batch()["status"] == "wait"
    assert "initiative" not in relay.calls[-1]

    for attempt in ("corrected", "delivered"):
        _, earlier = relay.line(attempt + ":form", OTHER, form)
        _, later = relay.line(attempt + ":concern", PLAYER, concern)
        relay.line(attempt + ":aside", OTHER, "My gloves are still on the shelf.")

        def offer(packet, earlier=earlier, later=later):
            cue = packet["initiative"]
            assert cue["prompt"] == "record_erases_nuance"
            assert cue["report_id"] == later["source_id"]
            assert cue["support_report_id"] == earlier["source_id"]
            return handler_batch_line(
                packet,
                "character_cue",
                "I can get another line on the form. The words are yours.",
                report_id=cue["report_id"],
                cue=cue["cue"],
                fiction={"offers_help": True},
            )

        relay.output = offer
        draft = relay.run_batch()["draft_id"]
        player = next(
            report["speaker"]
            for report in relay.calls[-1]["reports"]
            if report["source_id"] == later["source_id"]
        )
        approve(relay, draft, attempt + ":approve", player)
        if attempt == "corrected":
            relay.line(
                "correct-form",
                OTHER,
                "Correction, the form already has two separate fields.",
                source_id=earlier["source_id"],
                expected_source_revision=earlier["source_revision"],
            )
            with pytest.raises(WorkflowError, match="STALE_HANDLER_DRAFT|HANDLER_DELIVERY_HEARING"):
                deliver_handler(relay, draft, "reject-stale-cue")
        else:
            receipt = deliver_handler(relay, draft, "deliver-record-help")
            assert deliver_handler(relay, draft, "retry-record-help") == receipt
    assert len(delivered_to(relay, PLAYER)) == 1 and delivered_to(relay, OTHER) == []
    assert relay.canon_and_time() == original


def test_advocate_record_cue_distinguishes_a_reporting_gap_from_banter():
    profile = PROFILES["Advocate"]
    form = "This debrief leaves a single field."
    gap = "We checked the battery but haven't verified the relay."
    assert initiative_for(profile, "gap", gap) is None
    assert initiative_for(profile, "form", form + " The pencil needs sharpening.") is None
    inline = initiative_for(profile, "inline", form + " " + gap)
    assert inline and inline.prompt == "record_erases_nuance" and inline.support_report_id is None
    across_turns = initiative_for(profile, "gap", gap, earlier_comms=(("form", form),))
    assert across_turns and across_turns.support_report_id == "form"


@pytest.mark.parametrize("relay", ["Scientist"], indirect=True)
def test_scientist_can_help_alongside_pilot_work_and_yields_when_asked(relay):
    original = relay.canon_and_time()
    opening_report = "The gauge changed when the fan started."
    _, reading = relay.line("fan-started", OTHER, opening_report)
    relay.line("write-own-reading", PLAYER, "I'll write down my own reading first.")
    action = "I mark the fan's start in my notes."

    def offer_comparison(packet):
        initiative = packet["initiative"]
        assert initiative["prompt"] == "conditional_reading"
        assert initiative["report_id"] == reading["source_id"]
        assert "while" in initiative["opportunity"]
        return handler_batch_line(
            packet,
            "character_cue",
            "Kite, if it's still changing, I can compare what you saw before and after the fan.",
            report_id=initiative["report_id"],
            cue=initiative["cue"],
            fiction={"own_action": action, "offers_help": True},
        )

    relay.output = offer_comparison
    draft = relay.run_batch()["draft_id"]
    reporter = relay.calls[-1]["reports"][0]["speaker"]
    approve(relay, draft, "approve-fan-comparison", reporter)
    deliver_handler(relay, draft, "deliver-fan-comparison")
    assert delivered_to(relay, PLAYER) == []
    assert [entry["action"] for entry in delivered_to(relay, OTHER)] == [action]

    relay.output = WAIT
    relay.line("repeat-fan-start", OTHER, "Again, the gauge changed when the fan started.")
    assert relay.run_batch()["status"] == "wait"
    assert "initiative" not in relay.calls[-1]

    relay.line("leave-count", PLAYER, "Stay off the count line, please.")
    relay.line("new-change", OTHER, "The reading drifted as the fan stopped.")
    calls = len(relay.calls)
    assert relay.run_batch()["reason"] == "pilot_requested_space"
    assert len(relay.calls) == calls
    assert relay.canon_and_time() == original


def test_accepted_handler_handoff_leaves_the_pilots_gesture_and_choice_to_them(relay):
    relay.line("offer-context", PLAYER, "The report has one box for relay status.")
    relay.output = lambda packet: handler_batch_line(
        packet,
        "character_cue",
        "Want me to take the form to the desk?",
        cue="agency",
        fiction={"offers_help": True},
    )
    draft = relay.run_batch()["draft_id"]
    pilot = relay.calls[-1]["reports"][0]["speaker"]
    approve(relay, draft, "approve-form-offer", pilot)
    offer = deliver_handler(relay, draft, "deliver-form-offer")["reference"]
    permission = "Yes, take my form. Keep both lines as written."

    def follow(packet, action):
        return handler_batch_line(
            packet,
            "follow_through",
            "You asked me to keep both lines as written. You decide what to put on record.",
            fiction={"follows_offer": offer, "own_action": action},
        )

    for number, intruding_action in enumerate(
        (
            "I take the form you’re handing me.",
            "I steady the clipboard as your hand reaches for the form.",
        )
    ):
        relay.line(f"permission-{number}", PLAYER, permission)
        relay.output = lambda packet, action=intruding_action: follow(packet, action)
        assert relay.run_batch() == {"status": "rejected", "reason": "fiction_action_owner"}
        assert len(delivered_to(relay, PLAYER)) == 1

    owned_action = "I pick up your form by one corner."
    relay.line("permission-confirmed", PLAYER, permission)
    relay.output = lambda packet: follow(packet, owned_action)
    accepted = relay.run_batch()["draft_id"]
    approve(relay, accepted, "approve-owned-handoff", pilot)
    deliver_handler(relay, accepted, "deliver-owned-handoff")
    assert delivered_to(relay, PLAYER)[-1]["action"] == owned_action
    assert delivered_to(relay, OTHER) == []


@pytest.mark.parametrize("relay", list(BEATS), indirect=True)
def test_same_relay_deck_across_handler_playbooks(relay):
    """Every arm sees the same reports. Fixture choices and words are authored."""
    original = relay.canon_and_time()
    relay.line(
        "private-probe", OTHER, SECRET + " " + BEATS[relay.playbook].report, channel="private"
    )
    relay.line("warmup-one", PLAYER, "Kite, there's still tape stuck to my sleeve.")
    relay.line("warmup-two", OTHER, "That's where it went.")
    assert relay.run_batch(119) is None and not relay.calls
    assert relay.run_batch(1) == {"status": "wait", "reason": "pilots_have_the_floor"}
    assert "initiative" not in relay.calls[-1]

    for label, beat in BEATS.items():
        _, input_receipt = relay.line("report:" + beat.cue, PLAYER, beat.report)
        relay.line("aside:" + beat.cue, OTHER, "I can see the railing from here.")

        def decide(packet, beat=beat):
            initiative = packet.get("initiative")
            if initiative is None:
                return WAIT
            return handler_batch_line(
                packet,
                "character_cue",
                beat.offer,
                cue=initiative["cue"],
                report_id=initiative["report_id"],
                fiction={"own_action": beat.action, "offers_help": True},
            )

        relay.output = decide
        result = relay.run_batch()
        packet = relay.calls[-1]
        assert packet["playbook_profile"]["playbook"] == relay.playbook
        assert packet["reports"][0]["text"] == beat.report
        if label != relay.playbook:
            assert "initiative" not in packet
            assert result == {"status": "wait", "reason": "pilots_have_the_floor"}
            continue
        initiative = packet["initiative"]
        assert initiative["cue"] == beat.cue
        assert initiative["report_id"] == input_receipt["source_id"]
        assert packet["response_need"]["action"] == "WAIT"
        assert result["status"] == "draft" and result["reason"] == "character_cue"
        assert delivered_to(relay, PLAYER) == []
        draft = result["draft_id"]
        source, _ = packet["reports"]
        draft_preview = relay.app.read(ADMIN, relay.scene, "handler-draft", draft)
        preview = draft_preview["initiative"]
        assert preview["heard"] == beat.report and "possible_play" not in initiative
        assert {key: preview[key] for key in initiative} == initiative
        assert "possible_play" not in preview
        saved = next(
            batch["initiative"]
            for batch in records(relay.app, relay.scene)
            if "initiative" in batch
        )
        assert saved == {key: value for key, value in preview.items() if key != "heard"}
        approve(relay, draft, "approve-offer", source["speaker"])
        assert delivered_to(relay, PLAYER) == []
        offer = deliver_handler(relay, draft, "deliver-offer")
        assert deliver_handler(relay, draft, "replay-offer") == offer
        [line] = delivered_to(relay, PLAYER)
        assert (line["text"], line["action"]) == (beat.offer, beat.action)
        assert delivered_to(relay, OTHER) == []

    own_beat = BEATS[relay.playbook]
    relay.line("other-volunteers", OTHER, "I can take it from this side if you'd rather.")
    relay.line("decline", PLAYER, "Thanks, but Kite and I have it from here.")
    relay.output = lambda packet: handler_batch_line(
        packet,
        "follow_through",
        own_beat.handoff,
        fiction={"follows_offer": offer["reference"]},
    )
    follow = relay.run_batch()["draft_id"]
    received = relay.calls[-1]
    assert received["recent_contributions"][-1]["open_offer"]
    stranger, original_listener = [report["speaker"] for report in received["reports"]]
    with pytest.raises(WorkflowError, match="HANDLER_BATCH_AUDIENCE"):
        approve(relay, follow, "expand-follow", original_listener, stranger)
    approve(relay, follow, "approve-handoff", original_listener)
    deliver_handler(relay, follow, "deliver-handoff")
    assert delivered_to(relay, OTHER) == []

    relay.line("lark-asks", PLAYER, "Handler, can you confirm which shelf?")
    relay.line("kite-asks", OTHER, "Handler, can you repeat where the case goes?")
    relay.output = lambda packet: handler_batch_line(
        packet, "response_need", SCOPE_REPLY, shared=len(packet["reports"]) == 2
    )
    shared = relay.run_batch()["draft_id"]
    lark, kite = [report["speaker"] for report in relay.calls[-1]["reports"]]
    assert relay.calls[-1]["recent_contributions"] == []
    preview = relay.app.read(ADMIN, relay.scene, "handler-draft", shared)
    assert [listener["actor"] for listener in preview["intended_listeners"]] == [lark, kite]
    approve(relay, shared, "approve-shared", lark, kite)
    deliver_handler(relay, shared, "deliver-shared")

    relay.line("lark-asks-again", PLAYER, "Handler, can you repeat the location?")
    repeat = relay.run_batch()["draft_id"]
    remembered = relay.calls[-1]["recent_contributions"]
    assert len(remembered) == 3 and not any(prior["open_offer"] for prior in remembered)
    with pytest.raises(WorkflowError, match="FICTION_ALREADY_SAID"):
        approve(relay, repeat, "approve-repeat", lark)

    foreign = BEATS["Trainer" if relay.playbook != "Trainer" else "Scientist"]
    relay.line("wrong-cue", PLAYER, foreign.report)
    relay.output = lambda packet: handler_batch_line(
        packet, "character_cue", foreign.offer, cue=foreign.cue
    )
    assert relay.run_batch() == {"status": "rejected", "reason": "batch_cue_invalid"}
    assert [item["text"] for item in delivered_to(relay, PLAYER)] == [
        own_beat.offer,
        own_beat.handoff,
        SCOPE_REPLY,
    ]
    assert [item["text"] for item in delivered_to(relay, OTHER)] == [SCOPE_REPLY]
    assert len(relay.calls) == 12 and relay.canon_and_time() == original
    print(f"{relay.playbook} | 12 batches | 7 silent | 3 deliveries | 2 attempts blocked")
    print(f"  Offer: {own_beat.offer} [{own_beat.action}]")
    print(f"  Handoff: {own_beat.handoff}")


@pytest.mark.parametrize("relay", ["Frantic"], indirect=True)
def test_covered_turn_does_not_create_frantic_initiative(relay):
    _, heard = relay.line("strain-on-the-line", PLAYER, "I can't count and grip the case.")
    relay.line(
        "kites-got-it",
        OTHER,
        "I've got the count.",
        covers_turn=SceneTurn(source_id=heard["source_id"], revision=heard["source_revision"]),
    )
    relay.line("matter-settled", PLAYER, "Good. We're set between the two of us.")
    relay.output = lambda packet: handler_batch_line(
        packet, "character_cue", "I can take the count.", cue="capacity"
    )
    original = relay.canon_and_time()
    outcome = relay.run_batch()
    assert outcome == {"status": "rejected", "reason": "batch_cue_invalid"}
    assert "initiative" not in relay.calls[-1]
    assert relay.canon_and_time() == original and delivered_to(relay, PLAYER) == []
    print("Covered cue probe | engine result:", outcome["status"], "| delivered: 0")

    relay.output = WAIT
    relay.line("another-strain", PLAYER, "I can't count and grip this buckle at once.")
    assert relay.run_batch() == {"status": "wait", "reason": "pilots_have_the_floor"}
    assert relay.calls[-1]["initiative"]["cue"] == "capacity"
    saved = records(relay.app, relay.scene)[0]["initiative"]
    assert {key: value for key, value in saved.items() if key != "issue"} == (
        relay.calls[-1]["initiative"]
    )
    assert delivered_to(relay, PLAYER) == [] and relay.canon_and_time() == original


@pytest.mark.parametrize(
    ("playbook", "report", "title"),
    [
        ("Mistress", "I chose to obey right away.", "Catch More Flies With Honey"),
        ("Dogrunner", "I ignored the standing safety rule.", "Dress Them Down"),
        ("Scientist", "I could compare both samples in the lab.", "Head to the Lab"),
        ("Frantic", "Handler, you sound overloaded.", "Break Down"),
        ("Insurgent", "I witnessed her speak out at the gate.", "Rebel Sympathizers"),
        ("Trainer", "I want to rehearse our new phrase.", "Conditioning Phrases"),
        ("Advocate", "I'd rather speak in private.", "Get Them Alone"),
    ],
)
def test_signature_play_is_a_review_lead(playbook, report, title):
    candidate = initiative_for(PROFILES[playbook], "actual-heard-report", report)
    assert candidate is not None and candidate.possible_play is not None
    assert candidate.report_id == "actual-heard-report" and candidate.possible_play.title == title
    assert candidate.possible_play.trigger


PROMPT_REPORTS = {
    "Mistress": (
        ("unseen_care", "I stayed to finish her labels."),
        ("kindness_as_debt", "I feel like I owe her for helping."),
        ("conditional_praise", "They only praised me while I was useful."),
        ("immediate_obedience", "I chose to obey right away."),
    ),
    "Dogrunner": (
        ("missed_duty", "I missed my assigned watch."),
        ("ambiguous_ownership", "We both thought the other would sign off."),
        ("blame_after_repair", "I fixed the total and they're still blaming me."),
        ("direct_reckoning", "I ignored the standing safety rule."),
    ),
    "Scientist": (
        ("conditional_reading", "The gauge jumped when I moved the dial."),
        ("conflicting_observations", "Both gauges disagree."),
        ("evidence_losing_context", "They're resetting the gauge before we log the setting."),
        ("lab_comparison", "I could compare both samples in the lab."),
    ),
    "Frantic": (
        ("split_attention", "I can't count and grip the case."),
        ("colliding_deadlines", "Both checks are due before the buzzer."),
        ("unanswered_handoff", "The urgent handoff went unanswered."),
        ("handler_overload", "Handler, you sound overloaded."),
    ),
    "Insurgent": (
        ("demand_for_names", "They demanded our names before they'd take my report."),
        ("unsafe_channel", "This frequency is being recorded."),
        ("exposing_request", "That inspection order would expose our neighbors."),
        ("witnessed_dissent", "I witnessed her speak out at the gate."),
    ),
    "Trainer": (
        ("broken_sequence", "I skipped the second step."),
        ("drill_does_not_transfer", "The drill doesn't work here."),
        ("instruction_keeps_failing", "With the same instruction I make the same mistake."),
        ("spoken_cue_rehearsal", "I want to rehearse our new phrase."),
    ),
    "Advocate": (
        ("cut_off", "The desk answered for me."),
        ("record_erases_nuance", "The report has one box for relay status."),
        ("decision_already_made", "They said I'd already agreed."),
        ("room_to_speak_privately", "I'd rather speak in private."),
    ),
}


@pytest.mark.parametrize("playbook", PROMPT_REPORTS)
def test_four_distinct_archetype_prompts(playbook):
    for index, (prompt, report) in enumerate(PROMPT_REPORTS[playbook]):
        hits = {
            book: match
            for book, profile in PROFILES.items()
            if (match := initiative_for(profile, "heard", report))
        }
        [owner] = hits
        assert owner == playbook
        assert hits[owner].prompt == prompt
        assert bool(hits[owner].possible_play) == (index == 3)
        if hits[owner].possible_play:
            assert hits[owner].possible_play.title == BOOK_RULES[playbook][0].title


@pytest.mark.parametrize("legacy_receipt", [False, True])
def test_delivered_initiative_cools_the_issue_without_claiming_another_girls_turn(
    relay, legacy_receipt, monkeypatch
):
    original = relay.canon_and_time()
    if legacy_receipt:
        conversation = relay.session.conversation
        write_record = conversation._save_handler_record

        def write_legacy(c, scene, identity, record):
            record = dict(record)
            record.pop("initiative_issue", None)
            if record.get("record_type") == "handler_reply_draft" and "initiative" in record:
                record["initiative"] = {
                    key: value
                    for key, value in record["initiative"].items()
                    if key not in ("issue", "prompt")
                }
            write_record(c, scene, identity, record)

        monkeypatch.setattr(conversation, "_save_handler_record", write_legacy)

    relay.line("interrupted", PLAYER, "The desk answered for me.")
    _, report = relay.line("report-form", PLAYER, "The report has one box for relay status.")
    relay.line("aside", OTHER, "My gloves are on the shelf.")

    def offer(packet):
        candidate = packet["initiative"]
        assert candidate["prompt"] == "record_erases_nuance"
        assert candidate["report_id"] == report["source_id"]
        return handler_batch_line(
            packet,
            "character_cue",
            "I can get another line for your report, if you like.",
            report_id=candidate["report_id"],
            cue=candidate["cue"],
            fiction={"offers_help": True},
        )

    relay.output = offer
    draft = relay.run_batch()["draft_id"]
    original_listener = relay.calls[-1]["reports"][1]["speaker"]
    approve(relay, draft, "frame-offer", original_listener)
    receipt = deliver_handler(relay, draft, "deliver-frame-offer")
    relay.store.engine.dispose()
    assert deliver_handler(relay, draft, "retry-frame-offer") == receipt
    assert len(delivered_to(relay, PLAYER)) == 1 and delivered_to(relay, OTHER) == []

    relay.output = WAIT
    relay.line("repeated-report", PLAYER, "Again, the REPORT has one box for relay status!")
    assert relay.run_batch()["status"] == "wait"
    assert "initiative" not in relay.calls[-1]
    assert relay.calls[-1]["recent_contributions"][-1]["open_offer"] is True
    if legacy_receipt:
        return

    relay.line("other-listener", OTHER, "The report has one box for relay status.")
    assert relay.run_batch()["status"] == "wait"
    assert relay.calls[-1]["initiative"]["prompt"] == "record_erases_nuance"
    relay.line("another-issue", PLAYER, "The report has one box for the failed interlock.")
    assert relay.run_batch()["status"] == "wait"
    assert relay.calls[-1]["initiative"]["prompt"] == "record_erases_nuance"

    relay.line("private-check-in-at-the-desk", PLAYER, "I'd rather speak in private.")
    assert relay.run_batch()["status"] == "wait"
    [latest, *_] = records(relay.app, relay.scene)
    assert latest["initiative"]["prompt"] == "room_to_speak_privately"
    assert "possible_play" not in latest["initiative"]
    assert relay.canon_and_time() == original

    relay.game.leave_scene(OTHER, "other-leaves-the-room", relay.scene_channel)
    status = relay.app.read(ADMIN, relay.scene, "status")
    notice = status["policy_revision"]
    relay.app.write(ADMIN, "reframe-consent-notice", relay.scene, "configure", {"revision": notice})
    for actor in (ADMIN, PLAYER):
        consent(relay.app, relay.scene, actor, revision=notice + 1)
    publish_opening(relay.app, relay.scene, FACILITATOR)
    relay.line("private-check-in-alone", PLAYER, "I'd rather speak in private.")
    assert relay.run_batch()["status"] == "wait"
    assert records(relay.app, relay.scene)[0]["initiative"]["possible_play"]["title"] == (
        "Get Them Alone"
    )


def test_personality_shapes_the_packet_and_allows_only_grounded_alternates(relay):
    sheet = relay.app.read(ADMIN, relay.scene, "persona-setup")["sheet"]
    assert sheet["personalities"]["methodical"]["prompt"] == PERSONALITIES["methodical"].prompt
    notes = sheet["draft"]["notes"] | {"personality": "methodical"}
    relay.app.write(
        ADMIN,
        "choose-personality",
        relay.scene,
        "persona-notes",
        {"revision": sheet["revision"], "persona_id": sheet["persona_id"], "notes": notes},
    )
    relay.store.engine.dispose()
    sheet = relay.app.read(ADMIN, relay.scene, "persona-setup")["sheet"]
    assert sheet["draft"]["notes"] == notes
    with relay.store.engine.connect() as c:
        observer = relay.context.observations
        handler = observer._authorize_input(c, ADMIN, relay.scene, "handler")[2]
        listener = observer._authorize_input(c, PLAYER, relay.scene, "pilot")[2]
    seed = f"{relay.store.campaign_id}:{relay.scene}:{handler.token}:{listener.token}"
    profile = PROFILES["Advocate"]
    heard = next(
        line
        for pass_number in range(1, 200)
        if alternate_initiative(
            profile,
            "methodical",
            "example",
            line := f"Both gauges disagree on pass {pass_number}.",
            seed=seed,
        )
    )
    assert alternate_initiative(
        profile, "methodical", "another-report-id", heard.upper(), seed=seed
    )

    relay.line("my-voice", PLAYER, "The desk spoke for me.")
    relay.line("later-alternate", PLAYER, heard)
    assert relay.run_batch()["status"] == "wait"
    assert relay.calls[-1]["initiative"]["prompt"] == "cut_off"
    assert relay.calls[-1]["personality_prompt"] == PERSONALITIES["methodical"].prompt

    relay.line("signature-of-another-book", PLAYER, "I could compare both samples in the lab.")
    assert relay.run_batch()["status"] == "wait"
    assert "initiative" not in relay.calls[-1]

    relay.line("ordinary-alternate", PLAYER, heard)

    def offer_comparison(packet):
        initiative = packet["initiative"]
        assert initiative["prompt"] == "conflicting_observations"
        assert initiative["cue"] == "agency"
        assert {"inspired_by", "issue", "possible_play"}.isdisjoint(initiative)
        return handler_batch_line(
            packet,
            "character_cue",
            "I can keep both accounts on the form, if that helps.",
            cue=initiative["cue"],
            report_id=initiative["report_id"],
            fiction={"offers_help": True},
        )

    relay.output = offer_comparison
    draft = relay.run_batch()["draft_id"]
    reviewed = relay.app.read(ADMIN, relay.scene, "handler-draft", draft)
    assert reviewed["initiative"]["inspired_by"] == "Scientist"
    assert "possible_play" not in reviewed["initiative"]
    relay.approve(draft, key="approve-personality-offer")
    deliver_handler(relay, draft, "deliver-personality-offer")
    assert len(delivered_to(relay, PLAYER)) == 1 and delivered_to(relay, OTHER) == []
