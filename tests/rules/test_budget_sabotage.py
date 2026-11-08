"""Private Asset cards trigger on genuine use, retain the real roll and expire once."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_strain_service import D6, prepared
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_budget_sabotage import Pin, traps
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_secret_asset_cards_native_engage_failure_preserves_roll_and_single_use(ledger):
    missions, game = service(ledger, girl="ALPHA")
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={
                    "subsystems": approval.subsystems | {"world", "plays", "playbooks", "strain"}
                },
            )
        }
    )
    world = initial()
    WorldService(missions).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    strain = StrainService(OffDutyService(missions), dice=D6(2))
    prepared(strain, game)
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
    strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)
    effects = EffectService(strain)
    work = request.id + ":effect"
    a = next(x for x in state(game).sheets["2"].assets if x.family == "frame")
    b = next(x for x in state(game).sheets["3"].assets if x.family == "frame")
    pins = (
        Pin(owner=current_ref(state(game), 2), asset=a.id),
        Pin(owner=current_ref(state(game), 3), asset=b.id),
    )

    async def plan():
        interaction = current(1, 28800)
        await interaction.response.defer(ephemeral=True)
        await open_effect(interaction, effects, work)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = dict(
            assets=tuple(x.token for x in pins),
            account="Two secretly selected original Cadre Assets",
        )
        await form.confirm.callback(current(1, 28801))
        assert form.completed

    asyncio.run(plan())
    assert len(traps(state(game))) == 2
    with pytest.raises(WorkflowError):
        effects.get(PLAYER, work)
    unused = next(x for x in traps(state(game)) if x.pin == pins[1])
    original_assets = copy.deepcopy(state(game).sheets["2"].assets)
    worker, gateway = GameWorker(game), Gateway()

    def engage():
        return game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="engage",
                heat=0,
                target_actor=current_ref(state(game), 3),
                context="I attempt actual battlefield maneuvers with this Asset",
                trigger_confirmed=True,
            ),
        )["action_id"]

    async def choose(viewer, row, number, values):
        interaction = current(viewer.user_id, number)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = values
        await form.confirm.callback(current(viewer.user_id, number + 1))
        assert form.completed

    first = engage()
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = copy.deepcopy(game.inspect(PLAYER, first)["receipt"])
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "engage_maneuvers")
    actor_choice = dict(
        maneuvers=("pin", "advance"),
        asset_pin=(a.id,),
        asset_advance=(a.id,),
        text="The actual actor attempts these maneuvers using its owned hardware",
    )
    asyncio.run(choose(PLAYER, row, 28802, actor_choice))
    pending = next(x for x in game.choices(ADMIN) if x["kind"] == "budget_asset_calamity")
    detail = game.decision(ADMIN, pending["id"])
    assert len(detail["asset_calamities"]) == 1
    assert unused.id not in json.dumps(game.inspect(PLAYER, first))
    revealed = next(x for x in traps(state(game)) if x.pin == pins[0])
    assert revealed.phase == "revealed" and game.inspect(PLAYER, first)["state"] != "complete"
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "held"
    account = "The attempted actuator seizes; those intended maneuvers fail"
    asyncio.run(choose(ADMIN, pending, 28804, {revealed.id: account}))
    result = game.inspect(PLAYER, first)
    assert result["state"] == "complete" and result["result"]["maneuvers"] == {}
    assert result["receipt"] == receipt and game.dice.calls == 1
    assert state(game).sheets["2"].assets == original_assets
    assert next(x for x in traps(state(game)) if x.id == revealed.id).phase == "spent"
    assert next(x for x in traps(state(game)) if x.id == unused.id).phase == "armed"
    tick(worker, gateway, 4)
    assert any(x.get("asset_calamities") == [account] for x in gateway.messages.values())
    second = engage()
    tick(worker, gateway, 3)
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "engage_maneuvers")
    asyncio.run(choose(PLAYER, row, 28806, actor_choice))
    assert game.inspect(PLAYER, second)["state"] == "complete"
    assert game.inspect(PLAYER, second)["result"]["maneuvers"] == {"pin": a.id, "advance": a.id}
    assert game.dice.calls == 2
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
