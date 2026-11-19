"""One synthetic store, real mission rewards/Strain/recovery, then next dispatch."""

import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from test_director_continuity import carry, new_scene, reference, roles
from test_director_session import command
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_off_duty_cycle import call, movement, roll_for
from test_p2_connected_campaign import narrate
from test_strain import facts
from test_strain_service import ready
from test_world import gorgon, initial

from girlframe.ai.gm_outcomes import KeepOutcome, OutcomeProposal
from girlframe.ai.gm_protocol import Assessment, Demand, TaskFrame, TraitClaim
from girlframe.ai.observation import ObservationPolicy
from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def launch(missions, key, objective):
    offer = missions.offer(ADMIN, key + ":offer", objective, (2, 3))
    accepted = missions.respond(PLAYER, key + ":pilot", offer["id"], 1, "accept")
    accepted = missions.respond(OTHER, key + ":other", offer["id"], accepted["revision"], "accept")
    return missions.start(ADMIN, key + ":dispatch", offer["id"], accepted["revision"])


def keep(session, game, scene, channel, key):
    declaration = "GM, I declare Keep Your Head to hold the relay calibration needle on its mark."
    turn = session.submit(
        PLAYER, scene, command(session.observer, scene, key + ":input", declaration)
    )
    action = game.begin(
        PLAYER,
        key + ":play",
        channel,
        state(game).sheets["2"].revision,
        PlayInput(play="keep_your_head", heat=0, trigger_confirmed=True, context=declaration),
    )["action_id"]
    session.bind_action(
        ADMIN, key + ":bind", scene, turn["conversation"]["gm"]["play_review_id"], action
    )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    source = next(
        x
        for x in session.work(ADMIN, scene, gm=True)["outcome_sources"]
        if x["operation"] == "keep"
    )
    request = session.outcomes.open(
        ADMIN,
        key + ":open",
        scene,
        "choice",
        source["source_id"],
        TaskFrame(
            stakes="Hold the relay calibration needle on its mark.",
            demands=(Demand(id="control", question="Can the Pilot maintain precise control?"),),
        ),
    )
    packet = session.outcomes.packet(ADMIN, scene, request["id"])
    proposal = session.outcomes.propose(
        ADMIN,
        key + ":propose",
        scene,
        request["id"],
        OutcomeProposal(
            request_id=packet.request_id,
            decision=KeepOutcome(
                verdict="enough",
                narration="The Pilot holds the relay needle steady.",
                assessments=(
                    Assessment(
                        demand_id="control",
                        sufficient=True,
                        evidence_ids=("source", "native", "traits"),
                        traits=(TraitClaim(trait="in_control", polarity="are"),),
                        private_reason="Control supports the stated precision task.",
                    ),
                ),
            ),
            cited_evidence=("source", "native"),
            private_reasoning="PRIVATE_CYCLE_GM_REASON",
        ),
    )
    assert game.inspect(PLAYER, action)["state"] != "complete"
    with pytest.raises(WorkflowError):
        session.outcomes.confirm(PLAYER, key + ":wrong-owner", scene, proposal["id"])
    session.outcomes.confirm(ADMIN, key + ":confirm", scene, proposal["id"])
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    narration = narrate(
        session, scene, action, key + ":readback", "The relay calibration succeeds."
    )
    assert "PRIVATE_CYCLE_GM_REASON" not in json.dumps(narration)
    return action, narration


def test_mission_rewards_complete_off_duty_and_next_mission_share_one_campaign(ledger):
    strain, game = ready(ledger)
    missions = strain.missions
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    world = initial()
    WorldService(missions).initialize(
        ADMIN, "cycle-world", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    # Authored initial fixture, before the rehearsal starts: no current Void Assets.
    # The low-severity branch follows the existing Off-Duty test baseline.
    with ledger.transaction() as c:
        baseline = state(game)
        for sheet in baseline.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, "cycle-baseline", "synthetic.baseline", baseline)
    strain.configure(
        ADMIN, "cycle-scenario", state(game).revision, "business_as_usual", frozenset()
    )
    observer = DirectorObservationService(ledger, synthetic=True)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    observer.configure_scene(ADMIN, "cycle-observe", scene, 0, ObservationPolicy(mode="shadow"))
    for viewer in (ADMIN, PLAYER, OTHER):
        observer.set_consent(viewer, f"cycle-consent:{viewer.user_id}", scene, 1, consent=True)
    context = DirectorContextService(observer)
    session = DirectorSessionService(context)
    handler, pilot = roles(observer, scene)
    objective, _ = reference(
        context,
        scene,
        "cycle-brief",
        "Inspect and recalibrate the relay.",
        (handler, pilot),
        "briefing",
    )
    private, _ = reference(context, scene, "cycle-private", "PRIVATE_CYCLE_PILOT_NOTES", (pilot,))
    first = launch(missions, "mission-one", "Inspect and recalibrate the relay.")
    announced = session.submit(
        PLAYER, scene, command(observer, scene, "brief-turn", "I check my harness.")
    )
    assert announced["conversation"]["handler_decision"]["decision"]["reason"] == "known_update"
    action, narration = keep(session, game, scene, 900, "relay")
    memory = context.record(
        ADMIN,
        "cycle-outcome",
        scene,
        narration["id"],
        2,
        known_by=(handler, pilot),
        topic="debrief",
    )
    before = state(game)
    ended = missions.end(
        ADMIN,
        "mission-one:end",
        first["id"],
        first["revision"],
        True,
        debrief="PRIVATE_NATIVE_MISSION_DEBRIEF",
    )
    assert ended["rewards_committed"]
    assert (state(game).sheets["2"].permissions, state(game).sheets["3"].permissions) == (
        before.sheets["2"].permissions + 2,
        before.sheets["3"].permissions + 1,
    )
    pending = session.campaign_work(ADMIN, scene)
    discipline_work = next(x for x in pending["required_work"] if x["kind"] == "punishment")
    assert discipline_work["owner_id"] == "1" and discipline_work["subject_id"] == "3"
    with pytest.raises(WorkflowError, match="still pending"):
        missions.complete(ADMIN, "no-discipline-skip", first["id"], ended["revision"])
    discipline = PunishmentService(ledger)
    review = discipline.get(ADMIN, discipline_work["id"])
    with pytest.raises(WorkflowError):
        discipline.apply(
            OTHER,
            "not-discipline-owner",
            discipline_work["id"],
            review["revision"],
            review["game_revision"],
            Details(kind="stimulant_injection"),
        )
    discipline.apply(
        ADMIN,
        "cycle-discipline",
        discipline_work["id"],
        review["revision"],
        review["game_revision"],
        Details(kind="stimulant_injection"),
    )
    completed = missions.complete(ADMIN, "mission-one:complete", first["id"], ended["revision"])
    assert completed["phase"] == "complete"
    reward_snapshot = {uid: s.permissions for uid, s in state(game).sheets.items()}
    ledger.engine.dispose()
    assert (
        MissionService(ledger).end(
            ADMIN,
            "mission-one:end",
            first["id"],
            first["revision"],
            True,
            debrief="PRIVATE_NATIVE_MISSION_DEBRIEF",
        )
        == ended
    )
    assert {uid: s.permissions for uid, s in state(game).sheets.items()} == reward_snapshot

    period = strain.periods.begin(ADMIN, "cycle-period")
    dashboard = session.campaign_work(ADMIN, scene)
    assert not dashboard["missions"]["desk"]["can_offer"]
    assert dashboard["period"]["phase"] == "preparing"
    assert any(x["kind"] == "off_duty_strain_start" for x in dashboard["required_work"])
    before_read = state(game).model_dump_json()
    with ledger.engine.connect() as c:
        event_count = c.scalar(sa.select(sa.func.count()).select_from(t.events))
    assert session.campaign_work(ADMIN, scene) == dashboard
    assert state(game).model_dump_json() == before_read
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.events)) == event_count
    with pytest.raises(WorkflowError, match="Off-Duty"):
        missions.offer(ADMIN, "no-period-skip", "A premature mission", (2, 3))
    strain.prepare(
        ADMIN,
        "cycle-prepare",
        period["id"],
        period["revision"],
        state(game).revision,
        facts(no_girl_void=True, last_mission_success_no_frame_death_infrastructure_loss=True),
    )
    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="Strain"):
        call(cycle, game, ADMIN, period["id"], "activate")
    effects = EffectService(strain)
    selections = {
        "void": (
            1,
            Choice(
                rule_id="strain.void.low.1.1",
                account="A new threat approaches the city.",
                gorgon=gorgon("directed", "cycle-directed", (10, 0)),
            ),
        ),
        "rebellion": (
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="A rebel cell forms.",
                target="city0",
                faction=Faction(
                    id="cycle-rebels",
                    name="Synthetic local cell",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Local dissent",
                ),
            ),
        ),
        "budget": (
            5,
            Choice(
                rule_id="strain.budget.low.5.2", account="Rooms are reassigned.", rooms=((2, 3),)
            ),
        ),
    }
    for request in tuple(state(game).strain.requests):
        face, choice = selections[request.track]
        strain.dice.face = face
        strain.roll(ADMIN, "cycle-roll:" + request.track, request.id, 1, state(game).revision)
        strain.choose(
            ADMIN,
            "cycle-column:" + request.track,
            request.id,
            2,
            state(game).revision,
            2 if request.track == "budget" else 1,
        )
        effects.apply(
            ADMIN,
            "cycle-effect:" + request.track,
            request.id + ":effect",
            1,
            state(game).revision,
            choice,
        )
    assert strain.dice.calls == 3
    assert len(state(game).world.gorgons) == 2 and state(game).world.factions
    assert not any(
        x["kind"] in ("strain_roll", "strain_event")
        for x in session.campaign_work(ADMIN, scene)["required_work"]
    )
    call(cycle, game, ADMIN, period["id"], "activate")

    roll_for(cycle, game, period["id"], PLAYER, (2, 2))
    call(
        cycle,
        game,
        PLAYER,
        period["id"],
        "scene",
        "barracks",
        (2, 3),
        "PRIVATE_CYCLE_PILOT_SCENE",
    )
    call(cycle, game, PLAYER, period["id"], "acknowledge", 2)
    with pytest.raises(WorkflowError):
        call(cycle, game, ADMIN, period["id"], "acknowledge", 2)
    call(cycle, game, OTHER, period["id"], "acknowledge", 2)
    call(cycle, game, PLAYER, period["id"], "recover", RecoveryChoice())
    roll_for(cycle, game, period["id"], OTHER, (4, 4))
    call(cycle, game, OTHER, period["id"], "scene", None, (), "")
    call(cycle, game, OTHER, period["id"], "recover", RecoveryChoice())
    assert "PRIVATE_CYCLE_PILOT_SCENE" not in json.dumps(session.campaign_work(ADMIN, scene))
    assert "PRIVATE_CYCLE_PILOT_SCENE" in json.dumps(session.campaign_work(OTHER, scene))
    call(
        cycle,
        game,
        ADMIN,
        period["id"],
        "handler_scene",
        "routine",
        (1, 2),
        "PRIVATE_CYCLE_HANDLER_SCENE",
    )
    call(cycle, game, ADMIN, period["id"], "acknowledge", None)
    with pytest.raises(WorkflowError, match="actual work"):
        call(cycle, game, ADMIN, period["id"], "review_status", (3, 2), "Too soon")
    call(cycle, game, PLAYER, period["id"], "acknowledge", None)
    assert "PRIVATE_CYCLE_HANDLER_SCENE" not in json.dumps(session.campaign_work(OTHER, scene))
    ledger.engine.dispose()
    cycle = CycleService(strain.periods)
    call(cycle, game, ADMIN, period["id"], "review_status", (3, 2), "PRIVATE_CYCLE_STATUS_REASON")
    finished = call(cycle, game, ADMIN, period["id"], "finish", movement(game))
    assert finished["phase"] == "complete" and state(game).order == (3, 2)
    assert state(game).world.completed_off_duty == (period["id"],)
    assert session.campaign_work(PLAYER, scene)["period"] is None
    assert session.campaign_work(PLAYER, scene, period_id=period["id"])["period"]["own"][
        "recovered"
    ]
    assert not session.campaign_work(ADMIN, scene)["required_work"]
    assert not session.campaign_work(PLAYER, scene)["required_work"]
    assert not session.campaign_work(OTHER, scene)["required_work"]

    # One original store, next real native scene, preserved memory and changed Status.
    target = new_scene(observer)
    carry(context, scene, target, (objective, private, memory["id"]), "cycle-next-scene")
    session = DirectorSessionService(DirectorContextService(observer))
    second = launch(missions, "mission-two", "Survey the new Directed Gorgon approach.")
    assert missions.get(PLAYER, second["id"])["mission"]["phase"] == "active"
    game.dice.faces = (4, 5)
    second_action, _ = keep(session, game, target, 901, "next-relay")
    assert (
        "PRIVATE_CYCLE_PILOT_NOTES"
        not in session.context.build(ADMIN, target, actor=handler).model_dump_json()
    )
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_receipts"])) == 4
        metadata = " ".join(c.scalars(sa.select(t.events.c.payload_json)))
        outcomes = " ".join(c.scalars(sa.select(t.commands.c.outcome_json)))
        assert "PRIVATE_CYCLE_PILOT_SCENE" not in metadata + outcomes
        assert "PRIVATE_CYCLE_HANDLER_SCENE" not in metadata + outcomes
    output = Path("var/p2-mission-cycle.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "synthetic_only": True,
                "external_tokens": 0,
                "external_cost": 0,
                "first_mission": first["id"],
                "completed_mission_phase": completed["phase"],
                "reward_permissions": reward_snapshot,
                "off_duty": finished,
                "strain_effects": [x.rule_id for x in state(game).strain.events],
                "next_mission": second["id"],
                "next_mission_phase": "active",
                "native_actions": [action, second_action],
                "native_receipts": 4,
                "current_status_order": list(state(game).order),
                "unresolved_period_work": 0,
            },
            indent=2,
        )
        + "\n"
    )
