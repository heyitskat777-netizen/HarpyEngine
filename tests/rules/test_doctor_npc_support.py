"""Printed p71: an actual NPC protects Doctor or owns its high-result refusal."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_doctor_npc_nanobot import setup as npc_setup
from test_doctor_runtime import acquire
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_doctor import open_choice, open_request, open_roll
from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_battle import damage
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_doctor import DoctorService
from girlframe.services.m3_doctor_procedures import ProcedureService
from girlframe.services.onboarding import WorkflowError


def setup(ledger, tmp_path, monkeypatch):
    game, worker, gateway, protector, _ = npc_setup(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.NANO, rules.TRACK, rules.SUPPORT))
    acquire(game, rules.SUPPORT)
    return game, worker, gateway, protector


def begin_support(game, protector, faces):
    source = DoctorService(game)
    assert protector.token in {x["token"] for x in source.menu(PLAYER, 900)["npc_support_targets"]}
    game.dice.faces = faces

    async def begin():
        interaction = current(2, int(uuid4().int % 1000000000))
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_roll(interaction, source)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("doctor_support",),
            target=(protector.token,),
            heat=("1",),
            account="PRIVATE_SUPPORT_SOURCE: I actually hide behind this original NPC",
        )
        submit = current(2, int(uuid4().int % 1000000000))
        await form.confirm.callback(submit)
        assert form.completed, submit.edit_original_response.call_args_list
        await form.confirm.callback(submit)

    asyncio.run(begin())
    with game.store.engine.connect() as c:
        actions = t.m2["m2_actions"]
        return c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == game.store.campaign_id,
                actions.c.state.not_in(("complete", "aborted")),
            )
        )


def respond(game, viewer, kind, **values):
    row = next(x for x in game.choices(viewer) if x["kind"] == kind)

    async def submit():
        interaction = current(viewer.user_id, int(uuid4().int % 1000000000))
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, DoctorService(game), row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submitted = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        await form.confirm.callback(submitted)
        return form

    return asyncio.run(submit())


def test_native_npc_support_preserves_real_protector_bond_harm_guard_and_owned_stop(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, protector = setup(ledger, tmp_path, monkeypatch)
    before = state(game)
    doctor = current_ref(before, 2)
    action = begin_support(game, protector, (4, 4))
    tick(worker, gateway, 3)
    pass_tags(game)
    record = next(
        x
        for x in rules.values(state(game), "doctor_protection", rules.Protection)
        if x.id == action
    )
    assert record.phase == "protecting" and record.protector == protector and record.controller == 1
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "doctor_support_response")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("protect",))
        )
    respond(game, ADMIN, "doctor_support_response", decision=("protect",), bond=("yes",))
    actual = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt is not None and game.dice.calls == 1
    assert actual.sheets["2"].heat == before.sheets["2"].heat - 1
    assert actual.sheets["2"].obsolescence_marked == before.sheets["2"].obsolescence_marked
    assert actual.sheets["3"] == before.sheets["3"] and protector.entity not in actual.sheets
    assert depth(actual, doctor, protector) == depth(before, doctor, protector) + 1
    assert actual.placements == before.placements
    record = next(
        x for x in rules.values(actual, "doctor_protection", rules.Protection) if x.id == action
    )
    assert record.phase == "protecting"
    with ledger.engine.connect() as c:
        bindings = profiles(c, ledger.campaign_id)
        asset = next(x.id for x in actual.sheets["2"].assets if not x.damaged)
        with pytest.raises(ValueError, match="protector"):
            damage(actual, doctor, asset, bindings, str(uuid4()), opponent=current_ref(actual, 3))
        hurt, _ = damage(actual, doctor, asset, bindings, str(uuid4()), opponent=protector)
        assert next(x for x in hurt.sheets["2"].assets if x.id == asset).damaged
        assert any(x.get("kind") == "doctor_protector_harm" for x in hurt.facts)
    controls = ProcedureService(game)
    with pytest.raises(WorkflowError):
        controls.stop_protecting(OTHER, str(uuid4()), action, actual.revision, "Not my NPC")

    async def stop():
        interaction = current(1, 991901)
        await interaction.response.defer(ephemeral=True)
        await open_request(interaction, DoctorService(game), action)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="PRIVATE_PROTECTION_END: I actually stop shielding Doctor")
        submit = current(1, 991902)
        await form.confirm.callback(submit)
        assert form.completed, submit.edit_original_response.call_args_list
        await form.confirm.callback(submit)

    asyncio.run(stop())
    final = state(game)
    record = next(
        x for x in rules.values(final, "doctor_protection", rules.Protection) if x.id == action
    )
    assert record.phase == "ended" and record.end_event is not None
    with ledger.engine.connect() as c:
        damaged, _ = damage(
            final,
            doctor,
            asset,
            profiles(c, ledger.campaign_id),
            str(uuid4()),
            opponent=current_ref(final, 3),
        )
        assert next(x for x in damaged.sheets["2"].assets if x.id == asset).damaged
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1
    tick(worker, gateway, 8)
    assert "PRIVATE_" not in str(gateway.messages)


def test_native_npc_support_high_refusal_gives_actual_npc_tag_not_controller_status(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, protector = setup(ledger, tmp_path, monkeypatch)
    before = state(game)
    doctor = current_ref(before, 2)
    action = begin_support(game, protector, (6, 6))
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    respond(game, ADMIN, "doctor_support_response", decision=("refuse",), bond=("no",))
    assert game.inspect(PLAYER, action)["state"] != "complete"
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "doctor_support_refused")
    unchanged = state(game)
    with pytest.raises(WorkflowError, match="NPC"):
        game.respond(
            PLAYER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("status",))
        )
    assert state(game) == unchanged
    form = respond(
        game,
        PLAYER,
        "doctor_support_refused",
        decision=("tag",),
        tag="PRIVATE_SUPPORT_TAG: Won't stand with me",
    )
    assert form.fields[0].options == (("tag", "Give a Tag"),)
    final = state(game)
    tag = next(x for x in actor_tags(final, protector) if x.label.startswith("PRIVATE_SUPPORT_TAG"))
    assert tag.giver_entity == doctor.model_dump_json()
    assert len([x for x in actor_tags(final, protector) if x.id == tag.id]) == 1
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1
    assert final.sheets["2"].heat == before.sheets["2"].heat - 1
    assert final.sheets["3"] == before.sheets["3"] and final.order == before.order
    assert protector.entity not in final.sheets
    assert depth(final, doctor, protector) == depth(before, doctor, protector)
    record = next(
        x for x in rules.values(final, "doctor_protection", rules.Protection) if x.id == action
    )
    assert record.phase == "refused" and record.protector == protector
    tick(worker, gateway, 8)
    assert "PRIVATE_" not in str(gateway.messages)
    with ledger.engine.connect() as c:
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
