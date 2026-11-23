"""Run the private Activity's mission lifecycle on an isolated HarpyEngine ledger."""

from uuid import uuid4

import mission_lab

# isort: split
import pytest
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction
from girlframe.services.m2_game import GameService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_off_duty_cycle import recover_both
from test_strain import facts
from test_strain_effect_service import selected
from test_strain_service import ready
from test_world import initial

from handler_punishments import HandlerPunishments
from mission_desk import MissionDesk
from off_duty_followups import OffDutyFollowups

ledger = ledger_fixture


def test_mission_desk_debrief_then_off_duty_and_next_dispatch(ledger, monkeypatch):
    monkeypatch.setenv(
        "GIRLFRAME_RULES_REGISTRY", str(mission_lab.ENGINE / "rules/registry.json")
    )
    strain, game = ready(ledger)
    mission_lab.enable_private_subsystems(game)
    missions = strain.missions
    desk = MissionDesk(missions)
    policy = game.store.policy
    world = initial()
    WorldService(missions).initialize(
        ADMIN,
        "mission-world",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    with game.store.transaction() as c:
        current = state(game)
        for sheet in current.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, ADMIN.user_id, "mission-fixture", "synthetic.baseline", current)
    strain.configure(
        ADMIN, "scenario", state(game).revision, "business_as_usual", frozenset()
    )

    def command(action, viewer=ADMIN, key=None, **data):
        return desk.perform(viewer, key or str(uuid4()), {"action": action, **data})

    offered = command("offer", objective="Survey Relay Nine", pilots=["2", "3"])
    identity = offered["id"]
    assert desk.view(PLAYER, "Pilot", lifecycle=True)["desk"] is None
    assert desk.view(ADMIN, "Handler", lifecycle=True)["offers"][0]["actions"] == [
        "cancel"
    ]
    with pytest.raises(WorkflowError):
        command("dispatch", id=identity, revision=offered["revision"])
    accepted = missions.respond(
        PLAYER, "pilot-accept", identity, offered["revision"], "accept"
    )
    both = missions.respond(
        OTHER, "other-accept", identity, accepted["revision"], "accept"
    )
    with pytest.raises(WorkflowError):
        command("dispatch", PLAYER, id=identity, revision=both["revision"])
    started = command("dispatch", id=identity, revision=both["revision"])
    assert started["phase"] == "active"
    before = {uid: sheet.permissions for uid, sheet in state(game).sheets.items()}
    report = "Retrieved the relay log and verified the beacon."
    ended = command(
        "debrief",
        key="mission-debrief",
        id=identity,
        revision=started["revision"],
        success=True,
        debrief=report,
    )
    assert ended["phase"] == "awaiting_consequences"
    assert state(game).sheets["2"].permissions == before["2"] + 2
    assert state(game).sheets["3"].permissions == before["3"] + 1

    # Reopen the service and its SQLite connections from the saved ledger.
    game.store.engine.dispose()
    store = OnboardingStore(game.store.engine, policy)
    game = GameService(store)
    missions = MissionService(store)
    desk = MissionDesk(missions)
    assert (
        command(
            "debrief",
            key="mission-debrief",
            id=identity,
            revision=started["revision"],
            success=True,
            debrief=report,
        )
        == ended
    )
    assert state(game).sheets["2"].permissions == before["2"] + 2
    pilot_readback = desk.view(PLAYER, "Pilot", lifecycle=True)["offers"][0]
    assert pilot_readback["debrief"] == report and pilot_readback["success"]
    assert "actions" not in pilot_readback and "reactions" not in pilot_readback
    with pytest.raises(WorkflowError, match="still pending"):
        command("advance", id=identity, revision=ended["revision"])
    with pytest.raises(WorkflowError, match="Finish all mission work"):
        command("off_duty")

    punishment = HandlerPunishments(game)
    card = next(
        x for x in punishment.view(ADMIN) if "Dog's Punishment" in x["instruction"]
    )
    discipline = {
        key: card[key] for key in ("id", "revision", "work_revision", "action")
    }
    discipline["answer"] = {"kind": "stimulant_injection"}
    with pytest.raises(WorkflowError):
        punishment.perform(PLAYER, "wrong-punishment", discipline)
    punishment.perform(ADMIN, "mission-punishment", discipline)
    complete = command("advance", id=identity, revision=ended["revision"])
    assert complete["phase"] == "complete"

    period = command("off_duty", key="start-off-duty")
    assert command("off_duty", key="start-off-duty") == period
    with pytest.raises(WorkflowError, match="Finish the current Off-Duty"):
        command("offer", objective="Survey the uplink", pilots=["2", "3"])
    cycle_desk = OffDutyFollowups(game)
    strain = cycle_desk.strain.service
    strain.prepare(
        ADMIN,
        "strain-start",
        period["id"],
        period["revision"],
        state(game).revision,
        facts(at_least_half_have_void=False, no_girl_void=True),
    )
    outcomes = {
        "void": (1, 1, selected()),
        "rebellion": (
            1,
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="A local group appears",
                target="city0",
                faction=Faction(
                    id="mission-group",
                    name="Local group",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Local dissent",
                ),
            ),
        ),
        "budget": (
            5,
            2,
            Choice(
                rule_id="strain.budget.low.5.2",
                account="Rooms reassigned",
                rooms=((2, 3),),
            ),
        ),
    }
    from test_strain_service import D6

    for track, (face, column, effect) in outcomes.items():
        strain.dice = D6(face)
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.roll(ADMIN, "roll-" + track, request.id, 1, state(game).revision)
        strain.choose(
            ADMIN, "choose-" + track, request.id, 2, state(game).revision, column
        )
        EffectService(strain).apply(
            ADMIN,
            "effect-" + track,
            request.id + ":effect",
            1,
            state(game).revision,
            effect,
        )

    def duty_payload(actor, action, answer):
        readback = cycle_desk.view(actor)
        return {k: readback[k] for k in ("period", "revision", "game_revision")} | {
            "action": action,
            "answer": answer,
        }

    def duty(actor, action, answer):
        return cycle_desk.perform(
            actor, str(uuid4()), duty_payload(actor, action, answer)
        )

    duty(ADMIN, "activate_period", {})
    recover_both(cycle_desk.cycle, game, period["id"])
    duty(
        ADMIN,
        "set_handler_scene",
        {
            "kind": "routine",
            "participants": ["2"],
            "summary": "Private mission rest review",
            "recipient": None,
            "context": None,
        },
    )
    duty(ADMIN, "acknowledge_handler_scene", {})
    duty(PLAYER, "acknowledge_handler_scene", {})
    duty(
        ADMIN, "review_status", {"order": ["3", "2"], "account": "Filed annual review."}
    )
    finish = cycle_desk.view(ADMIN)["closing"]["finish"]
    moves = [
        {"gorgon": row["id"], "destination": row["cells"][0]} for row in finish["moves"]
    ]
    final = duty_payload(ADMIN, "finish_period", {"moves": moves, "changes": []})
    closed = cycle_desk.perform(ADMIN, "close-off-duty", final)
    assert closed["phase"] == "complete"
    assert cycle_desk.perform(ADMIN, "close-off-duty", final) == closed
    assert state(game).world.completed_off_duty == (period["id"],)
    assert desk.view(ADMIN, "Handler", lifecycle=True)["desk"]["off_duty"] is None

    next_mission = command("offer", objective="Survey the uplink", pilots=["2", "3"])
    yes = missions.respond(PLAYER, "next-accept", next_mission["id"], 1, "accept")
    no = missions.respond(
        OTHER, "next-decline", next_mission["id"], yes["revision"], "decline"
    )
    second = command("dispatch", id=next_mission["id"], revision=no["revision"])
    assert second["phase"] == "active"
    assert missions.get(ADMIN, second["id"])["mission"]["participants"] == [2]
    assert missions.get(ADMIN, identity)["mission"]["debrief"] == report
