"""A synthetic three-Girl rehearsal through real Activity review and delivery."""

import json
from time import monotonic, sleep

import pytest
from run_m5_model_missions import write_json
from test_activity_shadow_readiness import consent, publish_opening, review, submission
from test_director_continuity import carry
from test_ledger import ADMIN, OTHER, PLAYER
from test_m2_game import state
from test_m5_activity_pilots import NPC, PLOVER, attach, fixture, pilot_review, rehearsal

from girlframe.ai.director_dossiers import DossierPerspective, PressurePlan, RelationshipPerspective
from girlframe.ai.director_fronts import FrontDraft, FrontEvidence, FrontParticipant
from girlframe.ai.knowledge import Disclosure, KnowledgeProposal
from girlframe.engine.m3_world_development import Subject
from girlframe.engine.pilot_portrayal import PILOT_PORTRAYALS
from girlframe.services.director_fronts import DirectorFrontService, records, times
from girlframe.services.director_time import scene_time
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError

OFFER = "I’ll sit with you at the ledger desk after shift. Just ask if you want me to speak."
PROMISE = "I’ll come. You get the pen."


def steer_dossier(app, scene, actor, *, relationship, promise=None, fresh=False):
    dossiers = app.session.dossiers
    previous = dossiers.role_packet(OTHER, scene, actor)
    dynamic = previous.state.model_copy(
        update={
            "relationships": (relationship,),
            "promises": (promise,) if promise is not None else (),
        }
    )
    key = f"{actor.entity}:dossier:{previous.dossier_version}"
    profile = previous.profile
    if fresh:
        style = PILOT_PORTRAYALS[0 if actor == NPC else 2]
        planned = profile.pilot_portrayal
        traits = style.model_copy(
            update={
                "girl_playbook": planned.girl_playbook,
                "frame_playbook": planned.frame_playbook,
            }
        )
        profile = profile.model_copy(
            update={
                "voice": traits.voice,
                "behavior": traits.approach,
                "pilot_portrayal": traits,
                "reaction_tendencies": (traits.pressure,),
                "values": (traits.value,),
                "fears": (traits.fear,),
                "contradictions": (traits.contradiction,),
            }
        )
    proposal = dossiers.propose(
        OTHER, key, scene, actor, previous.dossier_version, profile, dynamic
    )
    dossiers.confirm(OTHER, key + ":confirm", scene, proposal["id"])


def save_pressure(app, scene, actor, text, plan, *, evidence=(), pressure_id=None):
    preview = app.read(OTHER, scene, "portrayal-preview", actor.token)
    key = f"{actor.entity}:pressure:{preview['dossier_version']}"
    memory = {
        "kind": "pressures",
        "text": text,
        "pressure": plan.model_dump(mode="json"),
        "knowledge_refs": list(evidence),
        **({"pressure_id": pressure_id} if pressure_id else {}),
    }
    draft = app.write(
        OTHER,
        key,
        scene,
        "portrayal-memory",
        {
            "actor": actor.model_dump(mode="json"),
            "version": preview["dossier_version"],
            "memory": memory,
        },
    )
    app.write(
        OTHER,
        key + ":confirm",
        scene,
        "portrayal-confirm",
        {"actor": actor.model_dump(mode="json"), "id": draft["id"]},
    )
    return next(
        item["pressure_id"]
        for item in app.read(OTHER, scene, "portrayal-preview", actor.token)["state"]["pressures"]
        if item["text"] == text
    )


def hear_aside(app, scene, key, text, listener):
    _, source = submission(app, scene, PLAYER, key, text, channel="scene")
    knowledge = app.session.knowledge
    request = knowledge.open(ADMIN, key + ":classify", scene, source["source_id"])
    proposal = knowledge.propose(
        ADMIN,
        key + ":propose",
        scene,
        request["id"],
        KnowledgeProposal(
            request_id=request["id"], disclosures=(Disclosure(quote=text, recipients=(listener,)),)
        ),
    )
    knowledge.confirm(ADMIN, key + ":approve", scene, proposal["id"])


def receive(path):
    deadline = monotonic() + 1200
    while not path.exists() and monotonic() < deadline:
        sleep(0.25)
    if not path.exists():
        raise TimeoutError(f"Missing {path.name}")
    return json.loads(path.read_text())


def run(store, exchange, *, model_exchange=False, revisit_only=False):
    app, first, game, clock, handler, pilot = rehearsal.__wrapped__(fixture.__wrapped__(store))
    attach(app, first)
    with store.engine.connect() as c:
        lark = app.session.observer._authorize_input(c, PLAYER, first, "pilot")[2]
    tern_view = RelationshipPerspective(
        subject=lark,
        text="I tried to help Lark by taking over before. I owe her a chance to speak first.",
    )
    plover_view = RelationshipPerspective(
        subject=lark,
        text="Lark keeps her own counsel. I trust her figures, and leave the rest to her.",
    )
    market = "Get new bootlaces before watch."
    market_plan = PressurePlan(
        stake="The old laces keep slipping.", next_step="Take the market lift."
    )
    ledger = "Sit beside Lark while she corrects the ledger."
    ledger_plan = PressurePlan(
        stake="Lark asked for my company and wants to speak for herself.",
        next_step="Take the chair beside the clerk.",
    )
    steer_dossier(app, first, NPC, relationship=tern_view, fresh=model_exchange)
    market_id = save_pressure(app, first, NPC, market, market_plan)
    journal = []
    decisions = []
    deliveries = {}

    def choose_at(beat):
        stub = pilot.client._post

        def post(request, timeout):
            body = json.loads(request.data)
            offered = json.loads(body["input"][1]["content"])
            number = len(decisions) + 1
            planning = offered["contract"]["title"] == "PilotAudienceDecision"
            stage = "audience" if planning else "draft"
            payload = {
                "beat": beat,
                "stage": stage,
                "instructions": body["input"][0]["content"],
                **offered,
            }
            write_json(exchange / f"request-{number:02}.json", payload)
            selected = receive(exchange / f"decision-{number:02}.json")["decision"]
            decisions.append({"beat": beat, "stage": stage, "decision": selected})
            if planning:
                pilot.audience_answer = selected
            else:
                pilot.answer = selected
            return stub(request, timeout)

        return post

    def say(scene, key, callsign, decision, listeners, *, reject_wider=False, fresh=False):
        before = state(game)
        with store.engine.connect() as c:
            time = scene_time(c, store.campaign_id, scene)
        pilot.answer = decision
        pilot.audience_answer = {
            "kind": "ADDRESS",
            "recipients": [actor.model_dump(mode="json") for actor in listeners],
        }
        clock.now += 120
        fresh = fresh and model_exchange
        stub = pilot.client._post
        if fresh:
            pilot.client._post = choose_at(key)
        try:
            outcome = review(app, scene)["model_outcome"]
        finally:
            pilot.client._post = stub
            pilot.audience_answer = None
        packet = pilot.plans[-1]
        assert packet["callsign"] == callsign, packet["callsign"]
        if fresh:
            decisions[-1]["outcome"] = outcome
        assert state(game) == before
        if fresh and (
            outcome["status"] != "pilot_review" or outcome["reason"] == "proposed_intent"
        ):
            return None
        assert outcome["status"] == "pilot_review", outcome
        proposal = outcome["proposal_id"]
        intended = app.read(OTHER, scene, "npc-owner-review", proposal)["proposal"].get(
            "intended_recipients"
        )
        recipients = intended or [actor.model_dump(mode="json") for actor in listeners]
        audience = [listener["actor"] for listener in packet["audience"]]
        assert all(recipient in audience for recipient in recipients)
        if reject_wider and not fresh:
            with pytest.raises(WorkflowError, match="AI_PILOT_AUDIENCE|FICTION_OFFER_UNAVAILABLE"):
                pilot_review(app, scene, proposal, *recipients, lark.model_dump(mode="json"))
        try:
            pilot_review(app, scene, proposal, *recipients)
        except WorkflowError as error:
            if not fresh:
                raise
            decisions[-1]["approval_blocked"] = str(error).partition(":")[0]
            return None
        sent = app.write(OTHER, key, scene, "npc-deliver", {"proposal": proposal})
        assert (
            app.write(OTHER, key + ":retry", scene, "npc-deliver", {"proposal": proposal}) == sent
        )
        assert not sent["effects_applied"] and state(game) == before
        with store.engine.connect() as c:
            assert scene_time(c, store.campaign_id, scene) == time
        assert times(state(game)) == times(before)
        hearing = app.npc_delivery.hearing(ADMIN, scene, sent["id"])
        assert hearing["recipients"] == recipients
        journal.append({"scene": scene, "beat": key, "packet": packet, "delivery": hearing})
        deliveries[key] = {
            "scene": scene,
            "callsign": callsign,
            "receipt": sent["reference"],
            "hearing": hearing,
        }
        if fresh:
            decisions[-1]["delivery"] = hearing
        return sent["reference"]

    def pressure_review(scene, checkpoint):
        eligible = {
            key: item
            for key, item in deliveries.items()
            if item["scene"] == scene and item["callsign"] == "Tern"
        }
        if not eligible:
            return
        write_json(exchange / f"review-{checkpoint}.json", eligible)
        reviewed = receive(exchange / f"controller-{checkpoint}.json")
        pressures = {
            "ledger": (ledger_id, ledger, ledger_plan),
            "market": (market_id, market, market_plan),
        }
        seen = set()
        for change in reviewed:
            name = change["pressure"]
            assert name not in seen
            seen.add(name)
            identity, text, initial = pressures[name]
            plan = PressurePlan(
                stake=initial.stake,
                status=change["status"],
                next_step=change.get("next_step"),
                account=change["account"],
            )
            save_pressure(
                app,
                scene,
                NPC,
                text,
                plan,
                pressure_id=identity,
                evidence=(eligible[change["beat"]]["receipt"],),
            )

    def next_scene(channel, cast_actors):
        game.bind_scene(ADMIN, f"bind:{channel}", channel)
        for actor in (ADMIN, PLAYER, OTHER):
            game.join_scene(actor, f"join:{channel}:{actor.user_id}", channel)
        cast = CastService(ActorService(MissionService(store)))
        for actor in cast_actors:
            current = cast.view(OTHER, channel)
            cast.change(
                OTHER,
                f"cast:{channel}:{actor.entity}",
                channel,
                current["game_revision"],
                current["cast_revision"],
                "join",
                actor,
            )
        with store.engine.connect() as c:
            scene = game.scene(c, channel)["id"]
        app.write(ADMIN, f"configure:{channel}", scene, "configure", {"revision": 0})
        for actor in (ADMIN, PLAYER, OTHER):
            consent(app, scene, actor)
        return scene

    original = "Would you sit with me at the ledger desk after shift? Keep this between us for now."
    hear_aside(app, first, "private-ask", original, NPC)
    offer = say(
        first,
        "deliver-offer",
        "Tern",
        {"kind": "DIALOGUE", "text": OFFER, "source_refs": [], "fiction": {"offers_help": True}},
        (lark,),
    )
    assert journal[-1]["packet"]["report"]["text"] == original
    assert [listener["actor"] for listener in journal[-1]["packet"]["audience"]] == [
        lark.model_dump(mode="json")
    ]
    accepted = "Yes, please sit with me. I want to make the correction myself."
    hear_aside(app, first, "accept-private-help", accepted, NPC)

    def follow(packet):
        assert any(
            item["reference"] == offer and item["open_offer"]
            for item in packet["recent_contributions"]
        )
        return {
            "kind": "DIALOGUE",
            "text": PROMISE,
            "source_refs": [],
            "fiction": {"follows_offer": offer},
        }

    kept = say(first, "deliver-private-commitment", "Tern", follow, (lark,))
    promise = DossierPerspective(
        text="I agreed to wait with Lark at the desk.", knowledge_refs=(kept,)
    )
    steer_dossier(app, first, NPC, relationship=tern_view, promise=promise, fresh=model_exchange)
    ledger_id = save_pressure(app, first, NPC, ledger, ledger_plan, evidence=(kept,))
    assert OFFER not in json.dumps(handler.calls) and PROMISE not in json.dumps(handler.calls)
    preview = app.read(ADMIN, first, "closeout")
    app.close(ADMIN, "close-quiet-bench", first, 900, preview["revision"], ())

    second = next_scene(902, (NPC, PLOVER))
    free_ledger = model_exchange and not revisit_only
    attach(app, second, PLOVER, "Plover")
    steer_dossier(app, second, PLOVER, relationship=plover_view, fresh=model_exchange)
    carried = carry(
        app.session.context, first, second, (offer, kept), key="carry-witnessed-commitment"
    )
    _, notice_input = submission(
        app,
        second,
        PLAYER,
        "when-the-lift-leaves",
        "The docket says the market lift leaves and the repair bay locks at the bell.",
    )
    context = app.session.context
    with store.engine.connect() as c:
        order = len(context._references(c, second))
    notice = context.record(
        ADMIN,
        "bell-notice",
        second,
        notice_input["source_id"],
        order,
        known_by=(lark, NPC, PLOVER),
    )["id"]
    fronts = DirectorFrontService(context)
    front = FrontDraft(
        key="repair-shift",
        title="PRIVATE_REPAIR_FRONT",
        situation="The shared bell limits work at the desk, lift and repair bay.",
        participants=tuple(
            FrontParticipant(subject=Subject(kind="npc", id=actor.entity))
            for actor in (NPC, PLOVER)
        ),
        fact_refs=(FrontEvidence(kind="reference", id=notice),),
        deadline_tick=1,
    )
    fronts.save(ADMIN, "repair-front", second, state(game).revision, front)
    save_pressure(
        app,
        second,
        PLOVER,
        "True the cart wheel before the bay closes.",
        PressurePlan(stake="The next crew needs that cart.", next_step="Ask Tern for a hand."),
        evidence=(notice,),
    )
    publish_opening(
        app,
        second,
        ADMIN,
        location="Ledger desk",
        intro="The last market lift leaves at the bell. The clerk is taking corrections now.",
    )

    plover = say(
        second,
        "deliver-chalk-offer",
        "Plover",
        {
            "kind": "DIALOGUE",
            "text": "Can you spare a hand with the wheel? "
            "If you're staying, you can have my chalk.",
            "source_refs": [],
            "fiction": {"offers_help": True},
            "intended_recipients": [actor.model_dump(mode="json") for actor in (lark, NPC)],
        },
        (lark, NPC),
        fresh=free_ledger,
    )
    packet = pilot.plans[-1]
    assert not packet["dossier"]["state"]["promises"] and plover_view.text in json.dumps(packet)
    assert packet["front_refs"] == [notice]
    assert len(packet["dossier"]["state"]["pressures"]) == 1
    assert not any(
        text in json.dumps(packet, ensure_ascii=False) for text in (OFFER, PROMISE, tern_view.text)
    )
    submission(
        app,
        second,
        PLAYER,
        "clerk-has-room",
        "There’s a seat if anybody is staying, but the lift will be gone by the time I’m done.",
    )

    def accept_chalk(packet):
        assert any(entry["reference"] == plover for entry in packet["received_offers"])
        return {
            "kind": "DIALOGUE",
            "text": "Leave the chalk with me, thanks. I can't help with the wheel before lockup.",
            "source_refs": [],
            "fiction": {"answers_offer": plover},
        }

    say(
        second,
        "accept-chalk",
        "Tern",
        accept_chalk,
        (PLOVER,),
        reject_wider=True,
        fresh=free_ledger,
    )
    submission(app, second, PLAYER, "dig-for-stamp", "The clerk is digging out the date stamp.")
    quiet = {"kind": "WAIT", "reason": "pilots_have_the_floor"}
    if free_ledger:
        say(second, "stamp-pause", "Plover", quiet, (lark, NPC), fresh=True)
    else:
        pilot.answer = quiet
        clock.now += 120
        assert review(app, second)["model_outcome"]["status"] == "wait"
    assert pilot.plans[-1]["callsign"] == "Plover"
    submission(app, second, PLAYER, "seat-by-clerk", "The seat beside the clerk is free now.")

    def choose(packet):
        dossier = packet["dossier"]
        assert tern_view.text in json.dumps(dossier) and plover_view.text not in json.dumps(dossier)
        assert dossier["state"]["promises"] == [promise.model_dump(mode="json")]
        assert {item["pressure"]["status"] for item in dossier["state"]["pressures"]} == {"open"}
        assert len(dossier["state"]["pressures"]) == 2
        assert packet["front_refs"] == [notice]
        planning = pilot.plans[-1]["dossier"]["context"]["references"]
        assert any(ref.get("origin_reference") == kept for ref in planning)
        assert all(ref.get("origin_reference") != kept for ref in dossier["context"]["references"])
        assert not any(entry["reference"] == plover for entry in packet["received_offers"])
        return {
            "kind": "DIALOGUE",
            "text": "I’ll stay. I can take the market lift another day.",
            "source_refs": [],
            "fiction": {"own_action": "I take the chair by the clerk."},
            "intended_recipients": [actor.model_dump(mode="json") for actor in (lark, PLOVER)],
        }

    choice = say(second, "deliver-choice", "Tern", choose, (lark, PLOVER), fresh=free_ledger)
    if free_ledger:
        pressure_review(second, "ledger")
    else:
        save_pressure(
            app,
            second,
            NPC,
            ledger,
            PressurePlan(
                stake=ledger_plan.stake, status="resolved", account="I took the chair beside Lark."
            ),
            evidence=(choice,),
            pressure_id=ledger_id,
        )
        save_pressure(
            app,
            second,
            NPC,
            market,
            PressurePlan(
                stake=market_plan.stake,
                status="deferred",
                next_step="Ask about a later lift.",
                account="I chose to stay at the ledger instead of taking this lift.",
            ),
            evidence=(choice,),
            pressure_id=market_id,
        )
    assert records(state(game))[0].status == "active"
    world_before_bell = state(game).model_dump(exclude={"facts", "revision"})
    review_at_bell = fronts.fictional_time(
        ADMIN, "the-bell", second, state(game).revision, 1, "The shift bell sounds."
    )
    assert review_at_bell["ready"] and records(state(game))[0].status == "ready"
    assert not review_at_bell["effects_applied"]
    assert state(game).model_dump(exclude={"facts", "revision"}) == world_before_bell
    preview = app.read(ADMIN, second, "closeout")
    app.close(ADMIN, "close-ledger-desk", second, 902, preview["revision"], ())
    third = next_scene(903, (NPC, PLOVER))
    transferred = carry(
        context,
        second,
        third,
        (
            *carried["references"].values(),
            notice,
            *(item["receipt"] for item in deliveries.values() if item["scene"] == second),
        ),
        key="carry-the-unfinished-errand",
    )["references"]
    store.engine.dispose()
    publish_opening(
        app, third, ADMIN, location="Yard", intro="The next watch is checking its gear."
    )
    _, lift_input = submission(
        app,
        third,
        PLAYER,
        "another-lift",
        "The morning lift has one place left. "
        "The desk says it can take the repair cart or one person.",
    )
    with store.engine.connect() as c:
        order = len(context._references(c, third))
    morning_lift = context.record(
        ADMIN,
        "morning-lift-notice",
        third,
        lift_input["source_id"],
        order,
        known_by=(lark, NPC, PLOVER),
    )["id"]

    def return_to_errand(packet):
        pressures = {
            item["pressure_id"]: item["pressure"]["status"]
            for item in packet["dossier"]["state"]["pressures"]
        }
        assert pressures == {market_id: "deferred", ledger_id: "resolved"}
        assert packet["front_refs"] == [transferred[notice]]
        assert morning_lift in packet["dossier"]["source_refs"]
        return {
            "kind": "DIALOGUE",
            "text": "Is there a place for me on that lift? I still need those laces.",
            "source_refs": [morning_lift],
        }

    # A newly cast scene rotates by name, so Plover may hear the news and leave the floor to Tern.
    if model_exchange:
        say(third, "yard-first", "Plover", quiet, (lark, NPC), fresh=True)
    else:
        pilot.answer = quiet
        clock.now += 120
        assert review(app, third)["model_outcome"]["status"] == "wait"
    plover_packet = pilot.plans[-1]
    assert plover_packet["callsign"] == "Plover"
    [wheel] = plover_packet["dossier"]["state"]["pressures"]
    assert wheel["text"] == "True the cart wheel before the bay closes."
    assert wheel["pressure"]["status"] == "open"
    assert ledger not in json.dumps(plover_packet)
    submission(
        app, third, PLAYER, "seats-open", "The desk wants to know who needs the space on the lift."
    )
    reopened = say(third, "ask-for-place", "Tern", return_to_errand, (lark,), fresh=True)
    if model_exchange:
        pressure_review(third, "yard")
        write_json(exchange / "decisions.json", decisions)
    else:
        save_pressure(
            app,
            third,
            NPC,
            market,
            PressurePlan(
                stake=market_plan.stake,
                next_step="Wait for the desk to confirm a seat.",
                account="I asked about the morning lift after hearing it had room.",
            ),
            evidence=(reopened,),
            pressure_id=market_id,
        )
    final = app.read(OTHER, third, "portrayal-preview", NPC.token)["state"]["pressures"]
    if not model_exchange:
        assert {item["pressure_id"]: item["pressure"]["status"] for item in final} == {
            market_id: "open",
            ledger_id: "resolved",
        }
    assert "PRIVATE_REPAIR_FRONT" not in json.dumps(journal)
    assert OFFER not in json.dumps(handler.calls, ensure_ascii=False)
    assert PROMISE not in json.dumps(handler.calls, ensure_ascii=False)
    write_json(exchange / "relationship-journal.json", journal)
    write_json(
        exchange / "result.json",
        {
            "synthetic": True,
            "relationship_rehearsal": True,
            "model_decisions": len(decisions),
            "fresh_beats": sum("outcome" in decision for decision in decisions),
            **({"matched_revisit": True} if revisit_only else {}),
            "approved_deliveries": len(journal),
            "scenes": 3,
            "pressure_statuses_after_revisit": {
                item["text"]: item["pressure"]["status"] for item in final
            },
            "effects_applied": False,
        },
    )
