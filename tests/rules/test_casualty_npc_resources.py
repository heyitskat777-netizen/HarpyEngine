"""Owned Casualty/NPC outcomes use real original resources and printed NPC harm."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change as cast_change
from test_casualty import ready, tags
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_casualty import open_choice
from girlframe.engine import m3_casualty as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_battle_npc import NpcDamageService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_casualty import CasualtyService, prove_sex
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_resources import NpcResourcesService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def _source(store, tmp_path, monkeypatch, *, record=True):
    game, worker, gateway, service = ready(store, tmp_path, monkeypatch, marked=True)
    missions = MissionService(store)
    npc = ActorRef(kind="npc", entity="real-casualty-counterpart")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("civilian",),
            controller=1,
            detail="PRIVATE_NPC_REAL_BODY",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_change(CastService(ActorService(missions)), ADMIN, "join", npc)
    BodyFactsService(game).record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        npc,
        "human_npc",
        "PRIVATE actual witnessed original body and brain",
    )
    resources = NpcResourcesService(game)
    if record:
        resources.record(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            900,
            npc,
            2,
            (("An actual marked Identity", True), ("An actual unmarked Identity", False)),
            "PRIVATE actual witnessed original NPC Heat and Identities",
        )
    session = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "PRIVATE actual independently chosen native encounter",
    )["id"]
    service.confirm(
        ADMIN,
        str(uuid4()),
        session,
        state(game).revision,
        True,
        "PRIVATE original NPC controller voluntarily agrees",
        npc_contact_account="Actual original bodies in contact outside enclosures at this location",
    )
    return game, worker, gateway, service, resources, npc, session


def _begin(game, npc, session):
    return game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=session,
            target_actor=npc,
            heat=0,
            context="Actual accepted original native source",
            trigger_confirmed=True,
        ),
    )["action_id"]


def _native(game, viewer, kind, **values):
    row = next(x for x in game.choices(viewer) if x["kind"] == kind)

    async def submit():
        interaction = current(viewer.user_id, int(uuid4().int % 1_000_000_000))
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, game.decision(viewer, row["id"]))
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        sent = current(viewer.user_id, int(uuid4().int % 1_000_000_000))
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        assert not interaction.edit_original_response.call_args.kwargs["allowed_mentions"].everyone

    asyncio.run(submit())
    return row


def test_actual_npc_high_independent_heat_part_and_printed_damage_complete_one_source(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service, resources, npc, session = _source(
        ledger, tmp_path, monkeypatch, record=False
    )
    before = state(game)
    with pytest.raises(WorkflowError, match="NPC_RESOURCE_SETUP_REQUIRED"):
        _begin(game, npc, session)
    assert state(game) == before and game.dice.calls == 0
    resources.record(
        ADMIN,
        str(uuid4()),
        before.revision,
        900,
        npc,
        2,
        (("An actual marked Identity", True),),
        "PRIVATE witnessed existing NPC resources",
    )
    game.dice = Dice((6, 6))
    action = _begin(game, npc, session)
    tick(worker, gateway, 3)
    tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    original_other = state(game).sheets["3"].model_copy(deep=True)
    original_npc = resources.view(ADMIN, npc)["resources"]
    npc_heat = next(x for x in game.choices(ADMIN) if x["kind"] == "casualty_high_heat")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), npc_heat["id"], npc_heat["revision"], ChoiceAnswer(number=4)
        )
    _native(game, PLAYER, "casualty_high_heat", heat=("4",))
    _native(game, ADMIN, "casualty_high_heat", heat=("3",))
    assert not any(x["kind"] == "casualty_high_asset" for x in game.choices(PLAYER))
    _native(
        game,
        ADMIN,
        "casualty_high_part",
        parts=("hands",),
        text="NPC independently breaks the original hands",
    )
    actual = state(game)
    assert rules.part_state(actual, current_ref(actual, 2), "hands") == "broken"
    assert resources.view(ADMIN, npc)["resources"]["heat"] == original_npc["heat"] + 3
    assert actual.sheets["3"] == original_other and "1" not in actual.sheets
    assert depth(actual, current_ref(actual, 2), npc) == 0
    _native(
        game,
        PLAYER,
        "casualty_high_asset",
        options=("npc_damage",),
        text="Casualty actually harms this original NPC",
    )
    assert game.inspect(PLAYER, action)["state"] != "complete"
    harm = NpcDamageService(ledger)
    with ledger.engine.connect() as c:
        work = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.campaign_id == ledger.campaign_id,
                    t.m3["m3_required_work"].c.kind == "npc_damage",
                    t.m3["m3_required_work"].c.state == "pending",
                )
            )
            .mappings()
            .one()
        )
    request = harm.get(PLAYER, work["id"])
    with pytest.raises(WorkflowError):
        harm.get(OTHER, work["id"])
    key = str(uuid4())
    args = (
        PLAYER,
        key,
        work["id"],
        request["revision"],
        "injure_tag",
        "Actual source harm gravely injures this NPC",
    )
    applied = harm.respond(*args, tag="PRIVATE actual broken and bleeding")
    assert harm.respond(*args, tag="PRIVATE actual broken and bleeding") == applied
    finished = state(game)
    assert depth(finished, current_ref(finished, 2), npc) == 1
    assert any(x.label == "PRIVATE actual broken and bleeding" for x in actor_tags(finished, npc))
    assert (
        next(x for x in rules.records(finished, rules.SexSession) if x.id == session).phase
        == "complete"
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1
    assert len(resources.view(ADMIN, npc)["resources"]["awards"]) == 1
    assert CasualtyService(game).view(ADMIN, session)["phase"] == "complete"
    game.rebuild()
    assert state(game) == finished


def test_actual_npc_mid_optional_unmark_preserves_original_owned_resources(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service, resources, npc, session = _source(ledger, tmp_path, monkeypatch)
    game.dice = Dice((4, 4))
    action = _begin(game, npc, session)
    tick(worker, gateway, 3)
    tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    _native(
        game,
        PLAYER,
        "casualty_present",
        parts=("legs",),
        text="Casualty presents her actual original legs",
    )
    _native(
        game,
        ADMIN,
        "casualty_focus",
        legs=("focus",),
        text="The independently controlled NPC actually focuses",
    )
    before = state(game)
    inventory = resources.view(ADMIN, npc)["resources"]
    marked = next(x["id"] for x in inventory["identities"] if x["marked"])
    choice = next(x for x in game.choices(ADMIN) if x["kind"] == "casualty_unmark")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("unmark",), denied=(marked,)),
        )
    assert state(game) == before
    _native(game, ADMIN, "casualty_unmark", options=("unmark",), identity=(marked,))
    _native(game, PLAYER, "casualty_unmark", options=("skip",))
    after = state(game)
    assert not next(
        x for x in resources.view(ADMIN, npc)["resources"]["identities"] if x["id"] == marked
    )["marked"]
    assert after.sheets == before.sheets
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert prove_sex(game, c, after, session).phase == "complete"
    assert service.view(ADMIN, session)["phase"] == "complete"
    with pytest.raises(WorkflowError):
        service.view(OTHER, session)
