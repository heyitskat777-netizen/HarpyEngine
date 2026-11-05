"""Actual televised fight uses owned participation and a genuine completed combat."""

import asyncio
from uuid import uuid4

import sqlalchemy as sa
from test_battle_pipeline import table
from test_battle_service import confirm
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_physical_operations import place
from test_strain_effect_service import selected
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_budget_fight import open_fight
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_budget_fight import get
from girlframe.engine.m3_strain_effects import Choice
from girlframe.services.inbox import InboxService
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_budget_fight import FightService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService


def test_actual_televised_source_attendance_off_duty_combat_and_native_ending(ledger):
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
    WorldService(strain.missions).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    with ledger.transaction() as c:
        placed = place(place(state(game), 2), 3)
        for sheet in placed.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.prior_actual_positions", placed)
    period = prepared(strain, game, high=frozenset({"budget"}))
    effects = EffectService(strain)
    for track, face, column in (("void", 1, 1), ("rebellion", 1, 2), ("budget", 4, 1)):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        if track != "budget":
            choice = (
                selected()
                if track == "void"
                else Choice(rule_id="strain.rebellion.low.1.2", account="Actual control slip")
            )
            effects.apply(
                ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice
            )
    source = request.id + ":effect"
    identity = source + ":fight"

    async def setup():
        interaction = current(1, 29200)
        await interaction.response.defer(ephemeral=True)
        await open_effect(interaction, effects, source)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            fighters=("2", "3"),
            fight_channel=("900",),
            account="The broadcast equipment is set up for this actual fight",
        )
        await form.confirm.callback(current(1, 29201))
        assert form.completed

    asyncio.run(setup())
    service = FightService(ledger)
    assert get(state(game), identity).phase == "attendance"
    for viewer in (PLAYER, OTHER):
        assert (
            next(x for x in InboxService(ledger).items(viewer) if x.identity == identity).task
            == "m3_budget_fight"
        )

    async def response(user, number, account):
        interaction = current(user, number)
        await interaction.response.defer(ephemeral=True)
        await open_fight(interaction, service, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(confirm=("yes",), account=account)
        await form.confirm.callback(current(user, number + 1))
        assert form.completed

    for uid in (2, 3):
        asyncio.run(
            response(uid, 29210 + 2 * uid, "I actually participate in this televised fight")
        )
    cycle = CycleService(strain.periods)
    activate(cycle, game, period)
    assert service.view(ADMIN, identity)["completed"] == 0
    battle = BattleService(ledger)
    preview = battle.preview(PLAYER, 900)
    actor = next(x for x in preview["actors"] if x["ref"]["entity"] == "2")
    target = next(x for x in preview["actors"] if x["ref"]["entity"] == "3")
    own_id = next(
        x.id for x in state(game).sheets["2"].assets if x.family == "frame" and not x.damaged
    )
    own = next(x for x in actor["assets"] if x["id"] == own_id)
    opposing_id = next(
        x.id for x in state(game).sheets["3"].assets if x.family == "frame" and not x.damaged
    )
    opposing = next(x for x in target["assets"] if x["id"] == opposing_id)
    declaration = Declaration.model_validate(
        dict(
            play="all_out_assault",
            actor=actor["ref"],
            target=target["ref"],
            attacking_asset=own["id"],
            target_asset=opposing["id"],
            actor_sha256=actor["sha256"],
            target_sha256=target["sha256"],
            account="An actual opening in our televised fight",
        )
    )
    context = confirm(battle, game, preview, declaration)
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="all_out_assault",
            heat=0,
            target_actor=declaration.target,
            attacking_asset=declaration.attacking_asset,
            target_asset=declaration.target_asset,
            battle_context=context,
            context=declaration.account,
            trigger_confirmed=True,
            piloting=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    table(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert next(x for x in state(game).sheets["3"].assets if x.id == opposing["id"]).damaged
    tick(worker, gateway, 5)
    assert service.view(ADMIN, identity)["completed"] == 1
    asyncio.run(
        response(1, 29230, "The actual broadcast ends after that real fight and its consequences")
    )
    result = get(state(game), identity)
    assert result.phase == "complete" and result.actions == (action,)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        work = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(work)
                .where(work.c.campaign_id == ledger.campaign_id, work.c.id == identity)
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert row["state"] == "resolved" and row["off_duty_id"] == period
