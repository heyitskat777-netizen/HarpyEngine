"""Genuine low Stim NPC effect, owned Order response and real drug expiry."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change as cast_change
from test_dose_up import ready
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current
from test_stim_sex import choose

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_stim_sex import open_stim
from girlframe.engine import m3_stim_sex as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_orders import NpcOrderService, order, source
from girlframe.services.m3_stim_npc import order_authority
from girlframe.services.m3_stim_sex import SexService, _drug, prove_effect
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def ready_npc(ledger, tmp_path, monkeypatch):
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    service = SexService(game)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="actual-stim-order-counterpart")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("guard",),
            controller=1,
            detail="Ordinary original synthetic NPC",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_service = CastService(ActorService(missions))
    cast_change(cast_service, ADMIN, "join", npc)
    BodyFactsService(game).record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        npc,
        "human_npc",
        "Actual original ordinary human body and brain",
    )
    return game, worker, gateway, service, npc, cast_service


def low_orders(game, worker, gateway, service, npc):
    identity = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "PRIVATE_STIM_ORDER_SOURCE Actual voluntary original encounter",
    )["id"]
    service.respond(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "Actual original NPC controller confirms this encounter",
        npc_contact_account="Actual body contact here, outside enclosures and rides",
    )
    game.dice.faces = (1, 1)
    before = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=identity,
            target_actor=npc,
            heat=0,
            context="Actual confirmed original encounter",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    choose(game, ADMIN, "stim_sex_drug", ("quick",), native=True)
    choose(
        game,
        ADMIN,
        "stim_sex_effects",
        ("orders", "bond", "tag"),
        tag="Distracted",
        native=True,
    )
    choose(game, ADMIN, "stim_sex_optional", ("decline",), native=True)
    tick(worker, gateway, 8)
    return identity, action, before


def test_actual_low_npc_drug_order_native_reply_and_expiry(ledger, tmp_path, monkeypatch):
    game, worker, gateway, service, npc, cast_service = ready_npc(ledger, tmp_path, monkeypatch)
    identity, action, before = low_orders(game, worker, gateway, service, npc)
    actual = state(game)
    pilot = current_ref(actual, 2)
    effect = next(x for x in rules.records(actual, rules.Effect) if x.kind == "orders")
    drug = next(x for x in rules.records(actual, rules.Drug) if x.id == effect.drug)
    assert effect.giver == npc and effect.target == pilot and drug.target == pilot
    assert actual.order == before.order and not actual.alpha_broken
    assert actual.sheets["2"].heat == before.sheets["2"].heat
    assert depth(actual, npc, pilot) == depth(before, npc, pilot) + 1
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert service.view(ADMIN, identity)["npc_order_effect"] == effect.id
    assert service.view(PLAYER, identity)["npc_order_effect"] is None
    with pytest.raises(WorkflowError):
        service.view(OTHER, identity)
    orders = NpcOrderService(game)
    assert not orders.preview(PLAYER, 900, 2, origin_kind="stim_sex")["issuers"]
    with pytest.raises(WorkflowError):
        orders.issue(
            PLAYER,
            str(uuid4()),
            900,
            npc,
            2,
            actual.revision,
            "Not my NPC",
            origin_kind="stim_sex",
            source_effect=effect.id,
        )
    with pytest.raises(WorkflowError, match="unexpired drug authority"):
        orders.issue(
            ADMIN,
            str(uuid4()),
            900,
            npc,
            2,
            actual.revision,
            "No substituted source",
            origin_kind="stim_sex",
            source_effect="not-this-effect",
        )
    assert state(game) == actual

    async def issue_native():
        interaction = current(1, 97501)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_stim(interaction, service, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert "may Disobey" in form.instructions
        form.values["instruction"] = "Sit down and drink some water"
        responded = current(1, 97502)
        await form.confirm.callback(responded)
        assert form.completed, responded.edit_original_response.call_args_list

    asyncio.run(issue_native())
    with ledger.engine.connect() as c:
        root_id = c.scalar(
            sa.select(t.m2["m2_actions"].c.id).where(
                t.m2["m2_actions"].c.campaign_id == ledger.campaign_id,
                sa.func.json_extract(t.m2["m2_actions"].c.body_json, "$.npc_order.origin_kind")
                == "stim_sex",
            )
        )
        root = game.action(c, root_id)
        saved_order = order(game, c, root)
        source(game, c, state(game), saved_order)
        assert saved_order.condition == effect.id and saved_order.issuer == npc
        assert saved_order.controller == ADMIN.user_id and saved_order.target == pilot
    tick(worker, gateway, 3)

    async def obey_native():
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "order_response")
        interaction = current(2, 97503)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert "Actual NPC issuer: Pat" in form.instructions
        assert "disobey" in dict(form.fields[0].options)
        form.values["options"] = ("obedient",)
        await form.confirm.callback(current(2, 97504))
        assert form.completed

    asyncio.run(obey_native())
    tick(worker, gateway, 8)
    assert game.inspect(PLAYER, root_id)["state"] == "complete"
    assert game.dice.calls == 1
    for number in (1, 2):
        game.close_scene(ADMIN, str(uuid4()), 900)
        game.bind_scene(ADMIN, str(uuid4()), 900)
        for person in (ADMIN, PLAYER, OTHER):
            game.join_scene(person, str(uuid4()), 900)
        cast_change(cast_service, ADMIN, "join", npc)
        issuers = orders.preview(ADMIN, 900, 2, origin_kind="stim_sex")["issuers"]
        assert bool(issuers) == (number == 1)
    final = state(game)
    assert rules.expired(final, drug.id)
    assert not any(x.id == drug.id for x in actor_tags(final, pilot))
    assert service.view(ADMIN, identity)["npc_order_effect"] is None
    with pytest.raises(WorkflowError, match="unexpired drug authority"):
        orders.issue(
            ADMIN,
            str(uuid4()),
            900,
            npc,
            2,
            final.revision,
            "Expired source cannot issue another Order",
            origin_kind="stim_sex",
            source_effect=effect.id,
        )
    assert state(game) == final
    with ledger.engine.connect() as c:
        assert _drug(game, c, final, drug.id) == drug
        assert prove_effect(game, c, final, effect.id) == effect
        assert order_authority(game, c, final, npc, pilot, effect_id=effect.id) is None
    assert "PRIVATE_STIM_ORDER_SOURCE" not in str(gateway.messages)


def test_each_stim_pane_keeps_its_original_active_npc_order_source(ledger, tmp_path, monkeypatch):
    game, worker, gateway, service, npc, cast_service = ready_npc(ledger, tmp_path, monkeypatch)
    first, first_action, _ = low_orders(game, worker, gateway, service, npc)

    def next_scene():
        game.close_scene(ADMIN, str(uuid4()), 900)
        game.bind_scene(ADMIN, str(uuid4()), 900)
        for person in (ADMIN, PLAYER, OTHER):
            game.join_scene(person, str(uuid4()), 900)
        cast_change(cast_service, ADMIN, "join", npc)

    next_scene()
    second, second_action, _ = low_orders(game, worker, gateway, service, npc)
    actual = state(game)
    pilot = current_ref(actual, 2)
    effects = {x.action: x for x in rules.records(actual, rules.Effect) if x.kind == "orders"}
    first_effect, second_effect = effects[first_action], effects[second_action]
    assert first_effect.id != second_effect.id
    with ledger.engine.connect() as c:
        assert order_authority(game, c, actual, npc, pilot) == second_effect
        assert order_authority(game, c, actual, npc, pilot, session_id=first) == first_effect
        assert (
            order_authority(
                game, c, actual, npc, pilot, session_id=first, effect_id=second_effect.id
            )
            is None
        )
        first_drug = _drug(game, c, actual, first_effect.drug)
        second_drug = _drug(game, c, actual, second_effect.drug)
        assert first_drug.session == first and second_drug.session == second
        assert rules.active(actual, first_drug) and rules.active(actual, second_drug)
    assert service.view(ADMIN, first)["npc_order_effect"] == first_effect.id
    assert service.view(ADMIN, second)["npc_order_effect"] == second_effect.id
    assert service.view(PLAYER, first)["npc_order_effect"] is None

    async def issue_from_older_pane():
        interaction = current(1, 97601)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_stim(interaction, service, first)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values["instruction"] = "Take a seat while this original drug lasts"
        responded = current(1, 97602)
        await form.confirm.callback(responded)
        assert form.completed, responded.edit_original_response.call_args_list

    asyncio.run(issue_from_older_pane())
    with ledger.engine.connect() as c:
        root_id = c.scalar(
            sa.select(t.m2["m2_actions"].c.id).where(
                t.m2["m2_actions"].c.campaign_id == ledger.campaign_id,
                sa.func.json_extract(t.m2["m2_actions"].c.body_json, "$.npc_order.origin_kind")
                == "stim_sex",
            )
        )
        saved_order = order(game, c, game.action(c, root_id))
        source(game, c, state(game), saved_order)
        assert saved_order.condition == first_effect.id
        assert saved_order.issuer == npc and saved_order.target == pilot
        assert saved_order.controller == ADMIN.user_id
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("obedient",))
    tick(worker, gateway, 8)
    assert game.inspect(PLAYER, root_id)["state"] == "complete"

    next_scene()
    final = state(game)
    assert rules.expired(final, first_drug.id) and rules.active(final, second_drug)
    assert service.view(ADMIN, first)["npc_order_effect"] is None
    assert service.view(ADMIN, second)["npc_order_effect"] == second_effect.id
    with pytest.raises(WorkflowError, match="unexpired drug authority"):
        NpcOrderService(game).issue(
            ADMIN,
            str(uuid4()),
            900,
            npc,
            2,
            final.revision,
            "Never replace this expired pane's source with the newer drug",
            origin_kind="stim_sex",
            source_effect=first_effect.id,
        )
    assert state(game) == final
    assert game.dice.calls == 2
    assert "PRIVATE_STIM_ORDER_SOURCE" not in str(gateway.messages)
