"""Synthetic AI Girls use their approved dossiers and the original reactions workflow."""

import json

import pytest
from test_activity_shadow_readiness import consent, opt, publish_opening, review, submission
from test_activity_shadow_readiness import fixture as fixture
from test_director_activity_scene import P2Scene
from test_director_worldbuilding import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.director_fronts import FrontDraft, FrontEvidence, FrontMove, PreparationTrigger
from girlframe.ai.model_transport import ModelLimits, OpenAIResponses
from girlframe.ai.observation import SceneTurn
from girlframe.ai.pilot_initiative import (
    ARCHETYPE_PROMPTS,
    FRAME_PROMPTS,
    GIRL_PROMPTS,
    pilot_initiative,
)
from girlframe.engine.campaign_opening import CampaignSeats, Opening, PlannedAIPilot
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_development import Subject
from girlframe.engine.m3_world_state import Npc
from girlframe.engine.pilot_portrayal import PILOT_PORTRAYALS, PilotPortrayal
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES
from girlframe.scenes.campaign_time import Anchor, Position, ScenePlan
from girlframe.services.campaign_difficulty import EVENT
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.director_fronts import DirectorFrontService
from girlframe.services.director_time import scene_time
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

VOICE = "PRIVATE_TERN_VOICE"
PLOVER_VOICE = "PRIVATE_PLOVER_VOICE"
PRIVATE = "PRIVATE_PILOT_DISCOVERY"
DIALOGUE = "The case, then. I can call the turns from here if that helps."
NPC = ActorRef(kind="npc", entity="tern")
PLOVER = ActorRef(kind="npc", entity="plover")


class LocalModel:
    def __init__(self):
        self.calls = []
        self.plans = []
        self.audience_answer = None
        self.answer = {"kind": "WAIT", "reason": "pilots_have_the_floor"}
        self.client = OpenAIResponses(
            model="synthetic-pilot",
            api_key="synthetic",
            limits=ModelLimits(attempts=48, output_tokens=500),
            post=self.post,
        )

    def post(self, request, timeout):
        body = json.loads(request.data)
        assert body["store"] is False and "tools" not in body
        offered = json.loads(body["input"][1]["content"])
        packet = offered["packet"]
        if offered["contract"]["title"] == "PilotAudienceDecision":
            self.plans.append(packet)
            choice = self.audience_answer
            if choice is None:
                intended = self.answer if isinstance(self.answer, dict) else {}
                choice = (
                    {"kind": "PRIVATE_INTENT"}
                    if intended.get("kind") == "SCENE_OFFER"
                    else {
                        "kind": "ADDRESS",
                        "recipients": intended.get("intended_recipients")
                        or [packet["report"]["speaker"]],
                    }
                )
            answer = choice(packet) if callable(choice) else choice
        else:
            self.calls.append(packet)
            answer = self.answer(packet) if callable(self.answer) else self.answer
        return json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": json.dumps({"decision": answer})}
                        ],
                    }
                ],
            }
        ).encode()


@pytest.fixture
def rehearsal(fixture):
    original, scene, game, clock, _, _, dice = fixture
    context = original.session.context
    world = ready((context.observations, context, scene, game, dice)).world
    registry = NpcRoleService(world)
    cast = CastService(ActorService(world.missions))
    for actor, job in (
        (NPC, "pilot_candidate"),
        (PLOVER, "ex_pilot"),
        (ActorRef(kind="npc", entity="rue"), "mechanic"),
    ):
        offer = registry.offer(
            ADMIN,
            "offer:" + actor.entity,
            state(game).revision,
            Npc(
                id=actor.entity,
                name=actor.entity.title(),
                jobs=(job,),
                detail="Training bay.",
                controller=OTHER.user_id,
                cell=(0, 0),
            ),
        )
        registry.respond(
            OTHER, "accept:" + actor.entity, offer["id"], state(game).revision, "accept"
        )
        view = cast.view(OTHER, 900)
        cast.change(
            OTHER,
            "cast:" + actor.entity,
            900,
            view["game_revision"],
            view["cast_revision"],
            "join",
            actor,
        )
    cast_view = cast.view(ADMIN, 900)
    cast.change(
        ADMIN,
        "cast-handler",
        900,
        cast_view["game_revision"],
        cast_view["cast_revision"],
        "join",
        ActorRef(kind="handler", entity=str(ADMIN.user_id)),
    )
    plan = Opening(
        scene="approved-introduction",
        channel=901,
        handler=ADMIN.user_id,
        handler_control="ai",
        audience=(ADMIN.user_id, PLAYER.user_id, OTHER.user_id),
        plan="approved-plan",
        goals="Share the work.",
        difficulty="normal",
        introduction="Check in.",
        first_mission_day=4,
        seats=CampaignSeats(
            player_count=2,
            ai_pilots=(
                PlannedAIPilot(
                    callsign="Tern",
                    portrayal=PILOT_PORTRAYALS[0].model_copy(
                        update={
                            "voice": VOICE,
                            "girl_playbook": "OLDGEN",
                            "frame_playbook": "JANUS",
                            "initiative": "Count to two before offering to take a watch.",
                        }
                    ),
                ),
                PlannedAIPilot(
                    callsign="Plover",
                    portrayal=PILOT_PORTRAYALS[1].model_copy(update={"voice": PLOVER_VOICE}),
                ),
            ),
        ),
    )
    with game.store.transaction() as c:
        game.store._audit(c, ADMIN.user_id, "approved-plan", EVENT, plan.model_dump(mode="json"))
    handler, pilot = LocalModel(), LocalModel()
    app = P2Scene.model_fixture(
        context, handler.client, batch=handler.client, pilot_batch=pilot.client
    )
    opt(app, scene)
    app.write(ADMIN, "configure", scene, "configure", {"revision": 0})
    for person in (ADMIN, PLAYER, OTHER):
        consent(app, scene, person)
    publish_opening(app, scene, ADMIN)
    return app, scene, game, clock, handler, pilot


def attach(app, scene, actor=NPC, callsign="Tern"):
    options = app.read(OTHER, scene, "pilot-dossiers")
    proposal = app.write(
        OTHER,
        "pilot-link:" + callsign,
        scene,
        "pilot-dossier-propose",
        {
            "actor": actor.model_dump(mode="json"),
            "origin": {"plan": options["plan"], "callsign": callsign},
        },
    )
    app.write(OTHER, "pilot-confirm:" + callsign, scene, "dossier-confirm", {"id": proposal["id"]})


def play_batch(app, scene, clock, key, *, delta=120):
    submission(app, scene, PLAYER, key, "The case is rattling at the corner.")
    clock.now += delta
    result = review(app, scene)
    return result["model_outcome"] if result else None


def timeline_text(app, scene, viewer):
    return [
        item["text"] for item in app.timeline(viewer, scene)["entries"] if item["kind"] == "npc"
    ]


def pilot_review(app, scene, id_, *recipients):
    return app.write(
        OTHER,
        "approve:" + id_,
        scene,
        "npc-review",
        {
            "proposal": id_,
            "decision": "approve",
            "reason": "Own offer, scoped source.",
            "recipients": list(recipients),
        },
    )


def test_girl_frame_and_individual_prompts_follow_the_approved_dossier(rehearsal):
    app, scene, game, clock, handler, pilot = rehearsal
    attach(app, scene)
    original = state(game)
    for index, (layer, label, text) in enumerate(
        (
            ("girl", "Oldgen", "We used to keep this door unlatched."),
            ("frame", "JANUS", "There's backup power in the last cabinet."),
            ("archetype", "Watchkeeper", "The corner is a blind spot from here."),
        )
    ):
        _, report = submission(app, scene, PLAYER, f"role-cue:{index}", text)
        _, later = submission(app, scene, OTHER, f"later-aside:{index}", "The floor is dry.")
        submission(app, scene, OTHER, f"private-aside:{index}", PRIVATE, channel="private")
        clock.now += 120
        assert review(app, scene)["model_outcome"]["status"] == "wait"
        packet = pilot.calls[-1]
        cue = packet["initiative"]
        assert (cue["layer"], cue["source"], cue["report_id"]) == (
            layer,
            label,
            report["source_id"],
        )
        assert packet["report"]["source_id"] == report["source_id"]
        assert packet["latest_heard_report_id"] == later["source_id"]
        assert packet["nearby_reports"][-1]["source_id"] == later["source_id"]
        assert PRIVATE not in json.dumps(packet)
        assert packet["portrayal_lenses"]["personality"] == (
            "Count to two before offering to take a watch."
        )
        assert "Plover" not in json.dumps({k: v for k, v in packet.items() if k != "audience"})
        assert PLOVER_VOICE not in json.dumps(packet) and not timeline_text(app, scene, PLAYER)
    assert state(game) == original


@pytest.mark.parametrize("withdraw", (False, True))
def test_callback_carries_only_still_authorized_reports_across_batches(rehearsal, withdraw):
    app, scene, game, clock, handler, pilot = rehearsal
    attach(app, scene)
    report = "I saw a warped clip. Nobody checked the latch."
    _, heard = submission(app, scene, PLAYER, "report", report)
    submission(app, scene, PLAYER, "private-note", PRIVATE, channel="private")
    clock.now += 120
    assert review(app, scene)["model_outcome"]["status"] == "wait"
    if withdraw:
        consent(app, scene, PLAYER, value=False)
        consent(app, scene, PLAYER, key="consent-new-epoch")
    _, callback = submission(app, scene, PLAYER, "callback", "Tern, your turn. What did you hear?")
    with game.store.engine.connect() as c:
        speaker = app.session.observer._authorize_input(c, PLAYER, scene, "pilot")[2]
    priority = "Keep the relief crew informed about the unchecked latch."
    pilot.audience_answer = {
        "kind": "ADDRESS",
        "recipients": [speaker.model_dump(mode="json")],
        "intent": {"tactic": "ask", "if_refused": "wait", "priority": priority},
    }
    pilot.answer = {
        "kind": "DIALOGUE",
        "text": "Can you tell me whether the latch is seated?",
        "source_refs": [],
    }
    clock.now += 120
    assert review(app, scene)["model_outcome"]["status"] == "pilot_review"
    for packet in (handler.calls[-1], pilot.plans[-1], pilot.calls[-1]):
        seen = [(row["source_id"], row["text"]) for row in packet.get("earlier_reports", ())]
        assert seen == ([] if withdraw else [(heard["source_id"], report)])
        assert PRIVATE not in json.dumps(packet)
    assert pilot.calls[-1]["latest_heard_report_id"] == callback["source_id"]
    assert pilot.calls[-1]["intent"]["priority"] == priority


def test_scene_memory_withholds_a_carried_report_after_npc_controller_transfer(rehearsal):
    app, origin, game, *_ = rehearsal
    context = app.session.context
    _, old = submission(app, origin, PLAYER, "earlier-copy", "The door is open.")
    _, corrected = submission(
        app,
        origin,
        PLAYER,
        "later-copy",
        "The door sticks.",
        source_id=old["source_id"],
        expected_source_revision=1,
    )
    ref = context.record(
        ADMIN, "corrected-copy", origin, corrected["source_id"], 0, known_by=(NPC,)
    )
    closeout = app.read(ADMIN, origin, "closeout")
    app.close(ADMIN, "close-report-scene", origin, 900, closeout["revision"], ())
    target = game.bind_scene(ADMIN, "open-report-scene", 902)["scene"]
    for viewer in (ADMIN, PLAYER, OTHER):
        game.join_scene(viewer, f"join-report-scene:{viewer.user_id}", 902)
    app.write(ADMIN, "observe-report-scene", target, "configure", {"revision": 0})
    for viewer in (ADMIN, PLAYER, OTHER):
        consent(app, target, viewer)
    missions = MissionService(game.store)
    cast = CastService(ActorService(missions))

    def cast_npc(owner, action):
        view = cast.view(owner, 902)
        cast.change(
            owner,
            f"cast-report:{action}:{owner.user_id}",
            902,
            view["game_revision"],
            view["cast_revision"],
            action,
            NPC,
        )

    cast_npc(OTHER, "join")
    review = app.read(ADMIN, target, "scene-opening")["memory"][0]
    assert review["sources"][0]["id"] == ref["id"]
    app.write(
        ADMIN,
        "carry-report",
        target,
        "scene-memory-carry",
        {
            "source_scene": origin,
            "review": review["review"],
        },
    )
    assert "The door sticks." in context.build(OTHER, target, actor=NPC).model_dump_json()

    roles = NpcRoleService(WorldService(missions))
    transfer = roles.offer_transfer(
        OTHER, "transfer-report-npc", state(game).revision, NPC.entity, PLAYER.user_id
    )
    roles.respond(PLAYER, "accept-report-npc", transfer["id"], state(game).revision, "accept")
    cast_npc(OTHER, "withdraw")
    cast_npc(PLAYER, "join")
    assert not context.build(PLAYER, target, actor=NPC).references
    assert not app.read(ADMIN, target, "scene-opening")["memory"]


def test_ai_pilot_keeps_authorized_memories_when_one_source_is_retired(rehearsal):
    app, scene, game, clock, handler, pilot = rehearsal
    attach(app, scene)
    context = app.session.context
    _, line = submission(app, scene, PLAYER, "source-promise", "Please wait by the ledger.")
    ref = context.record(ADMIN, "record-source", scene, line["source_id"], 0, known_by=(NPC,))
    actor = NPC.model_dump(mode="json")
    prompt = "I want to get my tools back before the third bell."
    promise = "Only Tern recalls she agreed to wait at the ledger."

    def draft(viewer, key, version, memory):
        return app.write(
            viewer,
            key,
            scene,
            "portrayal-memory",
            {"actor": actor, "version": version, "memory": memory},
        )

    def approve(key, proposal):
        return app.write(
            OTHER, key, scene, "portrayal-confirm", {"actor": actor, "id": proposal["id"]}
        )

    goal = {"kind": "pressures", "text": prompt}
    with pytest.raises(WorkflowError):
        draft(PLAYER, "someone-elses-memory", 1, goal)
    first = draft(OTHER, "own-business", 1, goal)
    assert (
        app.read(OTHER, scene, "portrayal-preview", NPC.token)["pending_memory"]["entry"]["text"]
        == prompt
    )
    approve("approve-business", first)
    with pytest.raises(WorkflowError, match="DOSSIER_UNKNOWN_SOURCE"):
        draft(
            OTHER,
            "made-up-promise",
            2,
            {
                "kind": "promises",
                "text": promise,
                "knowledge_refs": ["unavailable-reference"],
            },
        )
    second = draft(
        OTHER,
        "remember-promise",
        2,
        {
            "kind": "promises",
            "text": promise,
            "knowledge_refs": [ref["id"]],
        },
    )
    approve("approve-promise", second)
    assert play_batch(app, scene, clock, "review-memory")["status"] == "wait"
    assert pilot.calls[-1]["dossier"]["state"]["promises"][0]["text"] == promise
    assert promise not in json.dumps(handler.calls)

    revision = context.archive_review(ADMIN, scene)["revision"]
    context.archive(
        ADMIN, "retire-promise", scene, revision, (ref["id"],), "Retire the prompt source."
    )
    game.store.engine.dispose()
    assert play_batch(app, scene, clock, "review-after-retirement")["status"] == "wait"
    assert pilot.calls[-1]["dossier"]["profile"]["voice"] == VOICE
    assert pilot.calls[-1]["dossier"]["state"]["pressures"][0]["text"] == prompt
    assert promise not in json.dumps(pilot.calls[-1])
    history = app.session.dossiers.gm(ADMIN, scene, NPC)["history"]
    assert history[-1]["state"]["promises"][0]["text"] == promise


def test_pilot_pressure_revision_needs_new_known_evidence_and_preserves_other_plans(rehearsal):
    app, scene, game, clock, _, pilot = rehearsal
    attach(app, scene)
    actor = NPC.model_dump(mode="json")
    context = app.session.context
    goal = {"stake": "The scale is needed for the next shift.", "next_step": "Ask the desk."}
    other_goal = {"stake": "The wheel has a wobble.", "next_step": "Borrow a wrench."}

    def draft(key, version, text, plan, *, pressure_id=None, refs=()):
        return app.write(
            OTHER,
            key,
            scene,
            "portrayal-memory",
            {
                "actor": actor,
                "version": version,
                "memory": {
                    "kind": "pressures",
                    "text": text,
                    "pressure": plan,
                    "pressure_id": pressure_id,
                    "knowledge_refs": list(refs),
                },
            },
        )

    def confirm(key, proposal):
        return app.write(
            OTHER, key, scene, "portrayal-confirm", {"actor": actor, "id": proposal["id"]}
        )

    def read_pressures():
        return app.read(OTHER, scene, "portrayal-preview", NPC.token)["state"]["pressures"]

    confirm("approve-scale", draft("scale", 1, "Return the scale.", goal))
    confirm("approve-wheel", draft("wheel", 2, "True the cart wheel.", other_goal))
    scale, wheel = read_pressures()
    receipt = {"stake": goal["stake"], "status": "resolved", "account": "I returned the scale."}
    with pytest.raises(WorkflowError, match="PRESSURE_EVIDENCE"):
        draft("unsupported-resolution", 3, scale["text"], receipt, pressure_id=scale["pressure_id"])

    _, line = submission(app, scene, PLAYER, "receipt", "I saw Tern hand the scale back.")
    ref = context.record(ADMIN, "witness", scene, line["source_id"], 0, known_by=(NPC,))["id"]
    resolved = draft(
        "resolve-scale", 3, scale["text"], receipt, pressure_id=scale["pressure_id"], refs=(ref,)
    )
    assert read_pressures() == [scale, wheel]
    result = confirm("approve-resolution", resolved)
    assert confirm("approve-resolution", resolved) == result
    with pytest.raises(WorkflowError, match="STALE_DOSSIER"):
        draft("old-wheel", 3, "True the cart wheel.", other_goal)
    finished, still_open = read_pressures()
    assert finished["pressure"]["status"] == "resolved" and finished["knowledge_refs"] == [ref]
    assert finished["pressure_id"] == scale["pressure_id"] and still_open == wheel
    game.store.engine.dispose()
    assert play_batch(app, scene, clock, "pressure-packet")["status"] == "wait"
    assert pilot.calls[-1]["dossier"]["state"]["pressures"] == [finished, wheel]


def test_pilot_prompt_catalog_matches_the_playable_books():
    assert GIRL_PROMPTS.keys() == GIRL_TYPES.keys()
    assert FRAME_PROMPTS.keys() == FRAME_TYPES.keys()
    assert set(ARCHETYPE_PROMPTS) == {item.archetype.casefold() for item in PILOT_PORTRAYALS}
    assert (
        pilot_initiative(
            PilotPortrayal(girl_playbook="NEWGIRL"), "heard", "This is my first time."
        ).source
        == "Newgirl"
    )
    assert (
        pilot_initiative(
            PilotPortrayal(frame_playbook="Wyvern 0.4"), "heard", "The path is too narrow."
        ).source
        == "Wyvern 0.4"
    )
    assert (
        pilot_initiative(PilotPortrayal(frame_playbook="JANUS"), "heard", "The path is too narrow.")
        is None
    )

    portrayal = PilotPortrayal(girl_playbook="Oldgen", frame_playbook="Janus")
    text = "We used to have backup power here."
    draws = [
        pilot_initiative(portrayal, "original", text, seed=str(number)) for number in range(40)
    ]
    assert {cue.layer for cue in draws} == {"girl", "frame"}
    for number, cue in enumerate(draws):
        repeated = pilot_initiative(portrayal, "restated", text.upper(), seed=str(number))
        assert repeated.layer == cue.layer


@pytest.mark.parametrize(
    ("original", "fact", "start", "revised", "finish"),
    [
        (
            "I said I’d sit with Lark, so I’m staying. Plover, I can’t help with the wheel before "
            "the bell. My laces will have to wait too. Lark, you have the pen; I’ll speak only "
            "if you ask.",
            "promise",
            "both",
            "I’m staying, Lark. You have the pen.",
            "lark",
        ),
        (
            "I’ll stay with you, Lark. The laces can wait. Plover, I can’t give you a hand at the "
            "bay before the bell.",
            "promise",
            "both",
            "I’m staying at the desk. Plover, can we try the wheel tomorrow?",
            "both",
        ),
        (
            "Plover, I can’t be your second pair of eyes on the wheel tonight. I’ve committed "
            "to staying here.",
            "choice",
            "plover",
            "I’m tied up tonight. Can we try the wheel tomorrow?",
            "plover",
        ),
        (
            "It might, Plover. My old laces keep slipping. I’ll ask at the desk for a place; "
            "I still need to check the timing against watch.",
            "question",
            "both",
            "It might. I’ll ask at the desk and check the timing against watch.",
            "plover",
        ),
        ("I'll be here.", "promise", "both", None, "both"),
    ],
    ids=("terra-first", "terra-second", "sol-private-refusal", "terra-revisit", "one-revision"),
)
def test_audience_scope_replays_withheld_dialogue_once(
    rehearsal, original, fact, start, revised, finish
):
    app, scene, game, clock, _, pilot = rehearsal
    attach(app, scene)
    context = app.session.context
    with game.store.engine.connect() as c:
        lark = app.session.observer._authorize_input(c, PLAYER, scene, "pilot")[2]
    listeners = {"lark": (lark,), "plover": (PLOVER,), "both": (lark, PLOVER)}
    text = {
        "promise": "I’ll come. You get the pen.",
        "choice": "I’m staying, Lark. You have the pen. The laces can wait.",
        "question": "Tern, you said you could take the lift another day. "
        "Would the morning one work for you?",
    }[fact]
    _, event = submission(app, scene, PLAYER, "scoped-memory", text, channel="scene")
    private_listener = PLOVER if fact == "question" else lark
    secret = context.record(
        ADMIN,
        "scope-draft",
        scene,
        event["source_id"],
        0,
        known_by=(NPC, private_listener),
    )["id"]

    def plan(packet):
        attempt = packet.get("revise_for")
        assert secret in packet["dossier"]["source_refs"]
        by_listener = {
            entry["actor"]["entity"]: entry["source_refs"] for entry in packet["audience"]
        }
        assert secret in by_listener[private_listener.entity]
        if attempt:
            assert packet["previous_speech"]["recipients"] == [
                actor.model_dump(mode="json") for actor in listeners[start]
            ]
        return {
            "kind": "ADDRESS",
            "recipients": [
                actor.model_dump(mode="json") for actor in listeners[finish if attempt else start]
            ],
        }

    def write(packet):
        revised_stage = packet.get("revise_for")
        should_hear = revised_stage and listeners[finish] == (private_listener,)
        assert (secret in packet["dossier"]["source_refs"]) == bool(should_hear)
        assert (text in json.dumps(packet, ensure_ascii=False)) == bool(should_hear)
        if revised_stage and revised:
            return {"kind": "DIALOGUE", "text": revised, "source_refs": []}
        return {"kind": "DIALOGUE", "text": original, "source_refs": [secret]}

    pilot.audience_answer, pilot.answer = plan, write
    before = state(game)
    outcome = play_batch(app, scene, clock, "replay")
    assert len(pilot.plans) == len(pilot.calls) == 2 and outcome["revision"] == "citation_scope"
    assert not timeline_text(app, scene, PLAYER)
    if revised:
        proposal = outcome["proposal_id"]
        selected = [actor.model_dump(mode="json") for actor in listeners[finish]]
        pilot_review(app, scene, proposal, *selected)
        receipt = app.write(OTHER, "deliver-revision", scene, "npc-deliver", {"proposal": proposal})
        assert (
            app.write(OTHER, "retry-revision", scene, "npc-deliver", {"proposal": proposal})
            == receipt
        )
        assert app.npc_delivery.hearing(ADMIN, scene, receipt["id"])["text"] == revised
    else:
        assert outcome["status"] == "rejected" and outcome["reason"] == "npc_delivery_knowledge"
        assert not app.read(OTHER, scene, "work")["reactions"]
    assert review(app, scene) is None and state(game) == before


def test_pilot_intent_reaches_draft_and_rejects_an_unavailable_pressure(rehearsal):
    app, scene, game, clock, _, pilot = rehearsal
    attach(app, scene)
    cost = "Lose the practice slot held for the relief crew."
    next_move = "Ask for one more reading from the case operator."
    intent = {
        "tactic": "counteroffer",
        "if_refused": "ask_later",
        "pressure_id": "unknown",
        "priority": "Get a comparable reading.",
        "tradeoff": {"accepted_cost": cost, "next_move": next_move},
    }
    pilot.audience_answer = lambda packet: {
        "kind": "ADDRESS",
        "recipients": [packet["report"]["speaker"]],
        "intent": intent,
    }
    before = state(game)
    assert play_batch(app, scene, clock, "invented-pressure")["reason"] == "pilot_intent_scope"
    assert not pilot.calls
    intent["pressure_id"] = None
    pilot.answer = {
        "kind": "DIALOGUE",
        "text": "Could you take one more reading? I'll give up the slot if that's what it takes.",
        "source_refs": [],
    }
    outcome = play_batch(app, scene, clock, "provisional-ask")
    assert pilot.calls[-1]["intent"] == intent
    draft = app.read(OTHER, scene, "npc-owner-review", outcome["proposal_id"])
    assert not any(private in json.dumps(draft) for private in (cost, next_move, "tradeoff"))
    pilot_review(app, scene, outcome["proposal_id"], pilot.calls[-1]["report"]["speaker"])
    app.write(
        OTHER, "deliver-costly-ask", scene, "npc-deliver", {"proposal": outcome["proposal_id"]}
    )
    assert timeline_text(app, scene, PLAYER) == [pilot.answer["text"]]
    assert state(game) == before


def confirm_term(app, scene, actor, counterpart, reference, text, kind="condition"):
    draft = app.write(
        OTHER,
        f"term:{reference}:{actor.entity}",
        scene,
        "portrayal-memory",
        {
            "actor": actor.model_dump(mode="json"),
            "version": app.read(OTHER, scene, "portrayal-preview", actor.token)["dossier_version"],
            "memory": {
                "kind": "terms",
                "term": kind,
                "subject": counterpart.model_dump(mode="json"),
                "text": text,
                "knowledge_refs": [reference],
            },
        },
    )
    return app.write(
        OTHER,
        f"accept-term:{draft['id']}",
        scene,
        "portrayal-confirm",
        {
            "actor": actor.model_dump(mode="json"),
            "id": draft["id"],
        },
    )


def test_pilot_keeps_spoken_term_for_its_counterpart(rehearsal):
    app, scene, game, clock, _, pilot = rehearsal
    attach(app, scene)
    with game.store.engine.connect() as c:
        lark = app.session.observer._authorize_input(c, PLAYER, scene, "pilot")[2]
        handler = app.session.observer._authorize_input(c, ADMIN, scene, "handler")[2]
    terms = "Ask me before putting my name on the handover."
    pilot.answer = {"kind": "DIALOGUE", "text": terms, "source_refs": []}
    outcome = play_batch(app, scene, clock, "state-terms")
    proposal = outcome["proposal_id"]
    pilot_review(app, scene, proposal, lark.model_dump(mode="json"))
    sent = app.write(OTHER, "deliver-term", scene, "npc-deliver", {"proposal": proposal})
    with pytest.raises(WorkflowError, match="TERM_SOURCE"):
        confirm_term(app, scene, NPC, handler, sent["reference"], terms)
    confirm_term(app, scene, NPC, lark, sent["reference"], terms)
    pilot.answer = {"kind": "WAIT", "reason": "pilots_have_the_floor"}
    pilot.audience_answer = {"kind": "ADDRESS", "recipients": [PLOVER.model_dump(mode="json")]}
    assert play_batch(app, scene, clock, "other-audience")["status"] == "wait"
    assert pilot.plans[-1]["dossier"]["state"]["terms"][0]["text"] == terms
    assert "terms" not in pilot.calls[-1]["dossier"]["state"]
    pilot.audience_answer = None
    assert play_batch(app, scene, clock, "actual-counterpart")["status"] == "wait"
    assert pilot.calls[-1]["dossier"]["state"]["terms"][0]["text"] == terms


def test_front_offers_a_move_only_to_the_authorized_pilot_and_audience(rehearsal):
    app, scene, game, clock, handler, pilot = rehearsal
    attach(app, scene)
    context = app.session.context
    with game.store.engine.connect() as c:
        lark = app.session.observer._authorize_input(c, PLAYER, scene, "pilot")[2]
    _, line = submission(app, scene, PLAYER, "empty-saddle", "The cart has only one place.")
    ref = context.record(ADMIN, "cart-ref", scene, line["source_id"], 0, known_by=(lark, NPC))["id"]
    subject = Subject(kind="npc", id=NPC.entity)
    evidence = FrontEvidence(kind="reference", id=ref)
    text = "Suggest carrying the parts in two trips."
    move = FrontMove(
        id="two-trips", subject=subject, text=text, evidence_refs=(evidence,), portrayed_by=NPC
    )
    draft = FrontDraft(
        key="cart",
        title="GM cart inventory",
        situation="Private ordering notes.",
        fact_refs=(evidence,),
        possible_moves=(move,),
    )
    fronts = DirectorFrontService(context)
    before = state(game)
    fronts.save(ADMIN, "cart-front", scene, before.revision, draft)
    frozen = state(game)

    def choose(packet):
        assert packet["opportunity"]["text"] == text
        assert "GM cart inventory" not in json.dumps(packet)
        return {
            "kind": "ADDRESS",
            "recipients": [packet["report"]["speaker"]],
            "intent": {
                "tactic": "offer",
                "if_refused": "try_elsewhere",
                "move_id": packet["opportunity"]["id"],
            },
        }

    pilot.audience_answer = choose
    assert play_batch(app, scene, clock, "cart-open")["status"] == "wait"
    assert pilot.calls[-1]["opportunity"]["text"] == text
    assert text not in json.dumps(handler.calls) and state(game) == frozen


def test_declining_a_due_preparation_keeps_it_closed_after_reopen(rehearsal):
    app, scene, game, clock, _, _ = rehearsal
    calendar = CampaignTimeService(game.store)
    position = Position(day=4, slot="morning")
    anchor = Anchor(chapter="Inspection", position=position)
    calendar.initialize(ADMIN, "begin-inspection", anchor)
    with game.store.engine.connect() as c:
        revision = game.scene(c, 900, check_slot=False)["revision"]
    calendar.schedule(
        ADMIN,
        "book-inspection",
        900,
        scene,
        revision,
        calendar.projection(ADMIN)["anchor_receipt"],
        ScenePlan(start=position, end=position, participants=(1, 2, 3), location="Inspection bay"),
    )
    _, line = submission(app, scene, PLAYER, "case-label", "The dry label is blank.")
    context = app.session.context
    receipt = context.record(
        ADMIN, "label-evidence", scene, line["source_id"], 0, known_by=(PLOVER,)
    )
    evidence = FrontEvidence(kind="reference", id=receipt["id"])
    subject = Subject(kind="npc", id=PLOVER.entity)
    move = FrontMove(
        id="label",
        subject=subject,
        text="Prepare a spare label.",
        evidence_refs=(evidence,),
        portrayed_by=PLOVER,
        location="Inspection bay",
        trigger=PreparationTrigger(earliest=anchor),
    )
    DirectorFrontService(context).save(
        ADMIN,
        "label-front",
        scene,
        state(game).revision,
        FrontDraft(
            key="label",
            title="Inspect labels",
            situation="A sample needs identifying.",
            fact_refs=(evidence,),
            possible_moves=(move,),
        ),
    )
    card = app.read(OTHER, scene, "work")["next_plan"]
    assert card["status"] == "ready"
    payload = {"move": card["id"], "decision": "decline"}
    receipt = app.write(OTHER, "decline-label", scene, "front-preparation", payload)
    game.store.engine.dispose()
    clock.now += 36_000
    assert app.read(OTHER, scene, "work")["next_plan"] == {"status": "no_reply_needed"}
    assert app.write(OTHER, "decline-label", scene, "front-preparation", payload) == receipt
    with pytest.raises(WorkflowError, match="STALE_FRONT_MOVE"):
        app.write(
            OTHER, "revive-label", scene, "front-preparation", payload | {"decision": "prepare"}
        )


def test_pilot_context_change_during_audience_selection_stops_the_draft(rehearsal):
    app, scene, _, clock, _, pilot = rehearsal
    attach(app, scene)

    def moving_scene(packet):
        submission(app, scene, PLAYER, "new-context", "The case is quiet now.")
        return {"kind": "ADDRESS", "recipients": [packet["report"]["speaker"]]}

    pilot.audience_answer = moving_scene
    assert play_batch(app, scene, clock, "stale-audience")["status"] == "stale"
    assert len(pilot.plans) == 1 and not pilot.calls
    assert not app.read(OTHER, scene, "work")["reactions"]


def test_approved_ai_girl_uses_shared_batch_and_owned_delivery(rehearsal):
    app, scene, game, clock, handler, pilot = rehearsal
    assert play_batch(app, scene, clock, "no-dossier")["status"] == "wait"
    assert not pilot.calls
    attach(app, scene)
    submission(app, scene, OTHER, "unsent", PRIVATE, channel="private")
    submission(app, scene, OTHER, "gm-source", f"GM, {PRIVATE}")
    before = state(game)
    with game.store.engine.connect() as c:
        time_before = scene_time(c, game.store.campaign_id, scene)

    pilot.answer = lambda packet: {
        "kind": "DIALOGUE",
        "text": DIALOGUE,
        "source_refs": [packet["report"]["source_id"]],
    }
    assert play_batch(app, scene, clock, "new-report", delta=119) is None
    clock.now += 1
    outcome = review(app, scene)["model_outcome"]
    assert outcome["status"] == "pilot_review" and outcome["pilot"] == NPC.token
    [packet] = pilot.calls
    assert packet["callsign"] == "Tern" and packet["dossier"]["profile"]["voice"] == VOICE
    assert packet["dossier"]["actor"] == NPC.model_dump(mode="json")
    assert packet["report"]["classification"] == "reported_claim"
    assert PRIVATE not in json.dumps(packet) and VOICE not in json.dumps(handler.calls)
    assert len(handler.calls) == 2 and review(app, scene) is None

    proposal = outcome["proposal_id"]
    with pytest.raises(WorkflowError, match="REACTION_NOT_OWNED"):
        app.read(PLAYER, scene, "npc-owner-review", proposal)
    assert not timeline_text(app, scene, PLAYER)
    own = app.read(OTHER, scene, "npc-owner-review", proposal)
    assert own["proposal"]["text"] == DIALOGUE
    assert not own["proposal"].get("cited_references")
    assert packet["report"]["speaker"] in [value["actor"] for value in own["delivery_candidates"]]
    assert all(item["id"] != proposal for item in app.read(PLAYER, scene, "work")["reactions"])
    with pytest.raises(WorkflowError, match="AI_PILOT_AUDIENCE"):
        pilot_review(app, scene, proposal)
    pilot_review(app, scene, proposal, packet["report"]["speaker"])
    [pending] = app.read(OTHER, scene, "work")["reactions"]
    assert pending["status"] == "awaiting_delivery"
    with pytest.raises(WorkflowError, match="REACTION_NOT_OWNED"):
        app.write(ADMIN, "wrong-controller", scene, "npc-deliver", {"proposal": proposal})

    game.store.engine.dispose()
    restarted = P2Scene.model_fixture(
        app.session.context, handler.client, batch=handler.client, pilot_batch=pilot.client
    )
    sent = restarted.write(OTHER, "deliver-girl", scene, "npc-deliver", {"proposal": proposal})
    assert (
        restarted.write(OTHER, "retry-girl", scene, "npc-deliver", {"proposal": proposal}) == sent
    )
    assert not sent["effects_applied"] and review(restarted, scene) is None
    assert timeline_text(restarted, scene, PLAYER) == [DIALOGUE]
    assert not timeline_text(restarted, scene, ADMIN)
    assert not restarted.read(OTHER, scene, "work")["reactions"]
    handler.answer = lambda packet: {
        "kind": "NPC_DIALOGUE",
        "reason": "response_need",
        "text": "I can't see around that corner. Let me know what you find.",
        "source_refs": [],
        "report_ids": [packet["reports"][-1]["source_id"]],
        "intended_recipients": [packet["reports"][-1]["speaker"]],
    }
    submission(restarted, scene, PLAYER, "handler-turn", "Handler, can you see the corner?")
    clock.now += 120
    assert review(restarted, scene)["model_outcome"]["status"] == "draft"
    assert len(pilot.calls) == 1
    assert state(game) == before
    with game.store.engine.connect() as c:
        assert scene_time(c, game.store.campaign_id, scene) == time_before


def test_ai_pilot_rejects_unknown_evidence_even_with_the_heard_turn(rehearsal):
    app, scene, game, clock, _, pilot = rehearsal
    attach(app, scene)
    original = state(game)
    pilot.answer = lambda packet: {
        "kind": "DIALOGUE",
        "text": DIALOGUE,
        "source_refs": [packet["report"]["source_id"], "unknown-evidence"],
    }
    outcome = play_batch(app, scene, clock, "unknown-citation")
    assert outcome["status"] == "rejected" and outcome["reason"] == "reaction_scope"
    assert not timeline_text(app, scene, PLAYER) and state(game) == original


def test_pilot_offers_and_rejections_cannot_change_native_state(rehearsal):
    app, scene, game, clock, _, pilot = rehearsal
    attach(app, scene)
    before = state(game)
    pilot.answer = {
        "kind": "SCENE_OFFER",
        "text": "I'd like to steady the case.",
        "source_refs": [],
    }
    tradeoff = {"accepted_cost": "Give up my watch slot.", "next_move": "Offer to steady the case."}
    plan = {"tactic": "offer", "if_refused": "wait", "tradeoff": tradeoff}
    pilot.audience_answer = {"kind": "PRIVATE_INTENT", "intent": plan | {"move_id": "unapproved"}}
    assert play_batch(app, scene, clock, "unapproved-move")["reason"] == "pilot_intent_scope"
    assert not pilot.calls
    pilot.audience_answer["intent"] = plan
    intent = play_batch(app, scene, clock, "intent")
    assert pilot.calls[-1]["intent"]["tradeoff"] == tradeoff
    pilot.audience_answer = None
    decision = pilot_review(app, scene, intent["proposal_id"])
    assert intent["reason"] == "proposed_intent"
    assert decision["next_step"] == "native_service_or_scene_invitation"
    assert not timeline_text(app, scene, PLAYER)
    pilot.answer = {"kind": "apply_play", "heat": 0}
    assert play_batch(app, scene, clock, "invalid")["reason"] == "invalid_model_decision"
    pilot.answer = {"kind": "DIALOGUE", "text": "You decide to drop it.", "source_refs": []}
    assert play_batch(app, scene, clock, "agency")["reason"] == "batch_player_agency"

    def stale(_packet):
        submission(app, scene, PLAYER, "correction", "The noise stopped.")
        return {"kind": "DIALOGUE", "text": DIALOGUE, "source_refs": []}

    pilot.answer = stale
    assert play_batch(app, scene, clock, "while-in-flight")["status"] == "stale"
    assert not timeline_text(app, scene, PLAYER)

    pilot.answer = {"kind": "DIALOGUE", "text": DIALOGUE, "source_refs": []}
    clock.now += 120
    fresh = review(app, scene)["model_outcome"]
    pilot_review(app, scene, fresh["proposal_id"], pilot.calls[-1]["report"]["speaker"])
    consent(app, scene, PLAYER, value=False)
    with pytest.raises(WorkflowError, match="(?i)(consent|disabled)"):
        app.write(
            OTHER, "after-withdrawal", scene, "npc-deliver", {"proposal": fresh["proposal_id"]}
        )
    assert state(game) == before


def test_eligible_girls_rotate_and_keep_portrayals_separate(rehearsal):
    app, scene, _, clock, _, pilot = rehearsal
    attach(app, scene)
    attach(app, scene, PLOVER, "Plover")
    for beat, actor in enumerate((PLOVER, NPC)):
        outcome = play_batch(app, scene, clock, f"rotate:{beat}")
        assert outcome["status"] == "wait" and outcome["pilot"] == actor.token
    first, second = pilot.calls
    assert first["dossier"]["profile"]["voice"] == PLOVER_VOICE
    assert second["dossier"]["profile"]["voice"] == VOICE
    assert VOICE not in json.dumps(first) and PLOVER_VOICE not in json.dumps(second)


def test_ai_girl_offers_help_and_yields_to_a_heard_peer(rehearsal):
    app, scene, game, clock, _, pilot = rehearsal
    attach(app, scene)
    before = state(game)
    pilot.answer = {
        "kind": "DIALOGUE",
        "text": "I can call the turns from here, if you want.",
        "source_refs": [],
        "fiction": {"own_action": "I lower my pencil.", "offers_help": True},
    }
    offer_work = play_batch(app, scene, clock, "offer-count")["proposal_id"]
    offer_read = app.read(OTHER, scene, "npc-owner-review", offer_work)
    assert offer_read["proposal"]["fiction"]["own_action"] == "I lower my pencil."
    listener = pilot.calls[-1]["report"]["speaker"]
    pilot_review(app, scene, offer_work, listener)
    offer = app.write(OTHER, "deliver-offer", scene, "npc-deliver", {"proposal": offer_work})
    [heard] = [row for row in app.timeline(PLAYER, scene)["entries"] if row["kind"] == "npc"]
    assert heard["action"] == "I lower my pencil."
    assert not timeline_text(app, scene, ADMIN)

    repeat = play_batch(app, scene, clock, "offer-again")["proposal_id"]
    with pytest.raises(WorkflowError, match="FICTION_ALREADY_SAID"):
        pilot_review(app, scene, repeat, listener)

    def handoff(packet):
        assert any("I'll count" in report["text"] for report in packet["nearby_reports"])
        assert packet["recent_contributions"][-1]["reference"] == offer["reference"]
        assert packet["recent_contributions"][-1]["open_offer"] is True
        return {
            "kind": "DIALOGUE",
            "text": "Good. You two have it. I'll keep the channel clear.",
            "source_refs": [],
            "fiction": {"follows_offer": offer["reference"]},
        }

    submission(app, scene, OTHER, "other-takes-count", "I'll count from my side.")
    submission(app, scene, PLAYER, "declines", "We've got it, Tern. Thanks.")
    pilot.answer = handoff
    clock.now += 120
    follow = review(app, scene)["model_outcome"]["proposal_id"]
    with game.store.engine.connect() as c:
        actor = app.session.observer._authorize_input(c, ADMIN, scene, "handler")[2]
    with pytest.raises(WorkflowError, match="FICTION_OFFER_UNAVAILABLE|AI_PILOT_AUDIENCE"):
        pilot_review(app, scene, follow, listener, actor.model_dump(mode="json"))
    pilot_review(app, scene, follow, listener)
    app.write(OTHER, "deliver-handoff", scene, "npc-deliver", {"proposal": follow})

    pilot.answer = {
        "kind": "DIALOGUE",
        "text": "Still here.",
        "source_refs": [],
        "fiction": {"own_action": "I mark 2 Strain."},
    }
    assert play_batch(app, scene, clock, "reject-mechanics")["reason"] == "fiction_action_rules"
    assert len(timeline_text(app, scene, PLAYER)) == 2
    assert state(game) == before


def test_explicit_peer_reply_keeps_both_ai_models_out_of_the_covered_turn(rehearsal):
    app, scene, game, clock, handler, pilot = rehearsal
    attach(app, scene)
    before = state(game)
    _, opening = submission(app, scene, PLAYER, "count", "I can't count and grip the case.")
    link = SceneTurn(source_id=opening["source_id"], revision=opening["source_revision"])
    with pytest.raises(WorkflowError, match="PEER_TURN_UNAVAILABLE"):
        submission(app, scene, PLAYER, "own-cover", "I'll do it.", covers_turn=link)
    _, reply = submission(app, scene, OTHER, "peer-cover", "I'll take the count.", covers_turn=link)
    clock.now += 120
    assert review(app, scene)["model_outcome"]["status"] == "wait"
    assert not handler.calls and not pilot.calls
    assert not timeline_text(app, scene, PLAYER)

    # A separate turn stays eligible. Correcting the original makes the old cover stale.
    submission(
        app,
        scene,
        PLAYER,
        "new-need",
        "Kite, I need you to keep the two rails in view.",
        source_id=opening["source_id"],
        expected_source_revision=opening["source_revision"],
    )
    clock.now += 120
    assert review(app, scene)["model_outcome"]["status"] == "wait"
    assert handler.calls[-1]["reports"][0]["source_id"] == opening["source_id"]
    assert pilot.calls[-1]["report"]["source_id"] == opening["source_id"]
    assert all(
        report["source_id"] != reply["source_id"] for report in pilot.calls[-1]["nearby_reports"]
    )
    assert state(game) == before
