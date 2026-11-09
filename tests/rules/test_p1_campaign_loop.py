"""Deferred P1 human-operated journey; synthetic approvals never certify a release."""

from uuid import uuid4

import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, Gateway, answer, pass_tags, start, state, tick
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
from test_punishment_service import submit
from test_strain import facts
from test_strain_service import ready
from test_world import gorgon, initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService

ledger = ledger_fixture


def test_human_mission_play_discipline_off_duty_recovery_and_next_mission(ledger, monkeypatch):
    # No provider key or live service is needed by the human-operated path.
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DiscordBot", "DISCORD_BOT_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    strain, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    world = initial()
    missions = strain.missions
    WorldService(missions).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    # Legal synthetic starting condition, before the journey and its source histories.
    with ledger.transaction() as c:
        baseline = state(game)
        for sheet in baseline.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.initial_nonvoid_condition", baseline)
    strain.configure(ADMIN, str(uuid4()), state(game).revision, "business_as_usual", frozenset())

    offered = missions.offer(ADMIN, str(uuid4()), "PRIVATE_P1_FIRST_OBJECTIVE", (2, 3))
    accepted = missions.respond(PLAYER, str(uuid4()), offered["id"], offered["revision"], "accept")
    accepted = missions.respond(OTHER, str(uuid4()), offered["id"], accepted["revision"], "accept")
    launched = missions.start(ADMIN, str(uuid4()), offered["id"], accepted["revision"])

    game.dice = Dice((4, 5))
    worker, gateway = GameWorker(game), Gateway()
    action = start(game)
    tick(worker, gateway)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="PRIVATE_P1_ENOUGH_TO_PROCEED")
    tick(worker, gateway, 8)
    saved_receipt = game.inspect(PLAYER, action)["receipt"]
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1

    ended = missions.end(ADMIN, str(uuid4()), offered["id"], launched["revision"], True)
    discipline = PunishmentService(ledger, missions.access.registry)
    pending = missions.get(ADMIN, offered["id"])["work"]
    assert len(pending) == 1 and pending[0]["kind"] == "punishment" and pending[0]["subject"] == 3
    submit(discipline, ADMIN, pending[0]["id"], Details(kind="stimulant_injection"), str(uuid4()))
    complete = missions.complete(ADMIN, str(uuid4()), offered["id"], ended["revision"])
    assert complete["phase"] == "complete"
    assert state(game).sheets["2"].permissions == 2 and state(game).sheets["3"].permissions == 1

    period = strain.periods.begin(ADMIN, str(uuid4()))
    current = state(game)
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period["id"],
        period["revision"],
        current.revision,
        facts(no_girl_void=True),
    )
    choices = (
        (
            "void",
            1,
            Choice(
                rule_id="strain.void.low.1.1",
                account="Actual next map threat",
                gorgon=gorgon("directed", "p1-next-threat", (10, 0)),
            ),
        ),
        (
            "rebellion",
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="Actual local dissent",
                target="city0",
                faction=Faction(
                    id="p1-local-group",
                    name="Local group",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Synthetic local dissent",
                ),
            ),
        ),
        (
            "budget",
            5,
            Choice(
                rule_id="strain.budget.low.5.2",
                account="Actual shared accommodation",
                rooms=((2, 3),),
            ),
        ),
    )
    effects = EffectService(strain)
    for track, face, choice in choices:
        request = next(
            x
            for x in state(game).strain.requests
            if x.period_id == period["id"] and x.track == track
        )
        strain.dice.face = face
        rolled = strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(
            ADMIN,
            str(uuid4()),
            request.id,
            rolled["revision"],
            state(game).revision,
            2 if track == "budget" else 1,
        )
        effects.apply(ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice)

    cycle = CycleService(strain.periods)
    activate(cycle, game, period["id"])
    recover_both(cycle, game, period["id"])
    finish_routine(cycle, game, period["id"])
    assert call(cycle, game, ADMIN, period["id"], "finish", movement(game))["phase"] == "complete"
    assert CycleService(strain.periods).review(PLAYER, period["id"])["own"]["recovered"]
    assert game.inspect(PLAYER, action)["receipt"] == saved_receipt

    restarted = MissionService(ledger, missions.access.registry)
    second = restarted.offer(ADMIN, str(uuid4()), "PRIVATE_P1_NEXT_OBJECTIVE", (2, 3))
    for viewer in (PLAYER, OTHER):
        second = restarted.respond(viewer, str(uuid4()), second["id"], second["revision"], "accept")
    assert (
        restarted.start(ADMIN, str(uuid4()), second["id"], second["revision"])["phase"] == "active"
    )
    assert state(game).world.completed_off_duty == (period["id"],)
    with ledger.engine.connect() as c:
        assert strain.periods._pending(c, period["id"]) == []
        public = str(list(c.scalars(sa.select(t.events.c.payload_json)))) + str(
            list(c.scalars(sa.select(t.commands.c.outcome_json)))
        )
    for secret in (
        "PRIVATE_P1_FIRST_OBJECTIVE",
        "PRIVATE_P1_NEXT_OBJECTIVE",
        "PRIVATE_P1_ENOUGH_TO_PROCEED",
        "PRIVATE_HANDLER_SCENE",
        "PRIVATE_PERFORMANCE_ACCOUNT",
    ):
        assert secret not in public
