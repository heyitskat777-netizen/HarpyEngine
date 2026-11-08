"""Distinct printed normal tiers for the bounded actual identity-maintenance use."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_am_scrutinized import rolled as scrutiny_rolled
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.engine import m3_am as am
from girlframe.engine import m3_am_code as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_am_code import CodeService
from girlframe.services.onboarding import WorkflowError


def rolled(
    store,
    tmp_path,
    monkeypatch,
    faces,
    *,
    marked=False,
    source_inbox=False,
    choose_identity=True,
):
    game, _, npc, discovery, _, _, worker, gateway = scrutiny_rolled(
        store, tmp_path, monkeypatch, (4, 5)
    )
    answer(
        game,
        PLAYER,
        "am_select",
        options=("secret",),
        text="Please keep this actual adjustment secret",
    )
    tick(worker, gateway, 5)
    approved(store, game, tmp_path, monkeypatch, extra=(am.RULE, rules.RULE))
    service = CodeService(game)
    identity = service.propose(
        PLAYER,
        str(uuid4()),
        discovery,
        state(game).revision,
        "I request actual identity-only circuit maintenance with this already-knowing operator",
    )["id"]
    if source_inbox:
        from girlframe.discord_adapter.inbox import InboxView
        from girlframe.services.inbox import InboxService

        async def confirm_source():
            inbox = InboxService(store)
            task = next(x for x in inbox.items(ADMIN) if x.identity == identity)
            assert task.task == "m3_am_code_source"
            assert not any(x.identity == identity for x in inbox.items(PLAYER))
            interaction = current(1, 904020)
            interaction.channel_id = 999
            await interaction.response.defer(ephemeral=True)
            await InboxView(inbox, 1).route(interaction, task)
            form = interaction.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm) and "<#900>" in form.instructions
            form.values["source"] = ("confirm:" + identity,)
            selected = current(1, 904021)
            await form.confirm.callback(selected)
            access = selected.edit_original_response.call_args.kwargs["view"]
            assert isinstance(access, NativeForm) and "spoken-statement" in access.instructions
            access.values["account"] = (
                "Actual circuit access; low is a real spoken-statement Order only"
            )
            await access.confirm.callback(current(1, 904022))
            assert access.completed

        asyncio.run(confirm_source())
        source = {"action_id": rules.session(state(game), identity).root}
    else:
        source = service.confirm(
            ADMIN,
            str(uuid4()),
            identity,
            state(game).revision,
            "My actual NPC has real physical circuit access in this same place; "
            "identity-only maintenance",
        )
    tick(worker, gateway, 3)
    assert game.dice.calls == 1
    before = state(game)
    selected = rules.choices(before, current_ref(before, 2))[0]
    prep = dict(gain=1, identity=selected.id, heat=1) if marked else dict(heat=0)
    game.dice.faces = faces
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            parent=source["action_id"],
            source_work=identity,
            target_actor=npc,
            context="Actual already-confirmed identity circuit maintenance",
            trigger_confirmed=True,
            **prep,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    if choose_identity and any(x["kind"] == "am_code_options" for x in game.choices(ADMIN)):
        answer(game, ADMIN, "am_code_options", options=("identities",))
    return game, identity, source["action_id"], action, worker, gateway, selected


def test_mid_actual_operator_native_rewrite_retains_mark_slot_body_hardware_and_finishes(
    ledger, tmp_path, monkeypatch
):
    game, identity, root, action, worker, gateway, selected = rolled(
        ledger, tmp_path, monkeypatch, (4, 5), marked=True
    )
    before = state(game)
    original = current_ref(before, 2)
    source_sheet = before.sheets["2"]
    placement = next(x for x in before.placements if x.actor == original)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "am_code_edit")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("edit",), fields={selected.id: "Forged"}, text="Not my operator"),
        )

    async def rewrite():
        operator = current(1, 904001)
        await operator.response.defer(ephemeral=True)
        await open_choice(operator, game, row["id"])
        form = operator.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values["identities"] = (selected.id,)
        picked = current(1, 904002)
        await form.confirm.callback(picked)
        actual = picked.edit_original_response.call_args.kwargs["view"]
        assert isinstance(actual, NativeForm)
        actual.values.update(
            identity_0="Self-directed",
            account="The actual NPC rewrites this original non-Limited Identity",
        )
        await actual.confirm.callback(current(1, 904003))
        assert actual.completed

    asyncio.run(rewrite())
    actual = state(game)
    value = rules.session(actual, identity)
    new = next(x for x in actual.sheets["2"].identities if x.id == value.replacements[selected.id])
    assert (
        new.id != selected.id
        and new.name == "Self-directed"
        and new.slot == selected.slot
        and new.marked
    )
    assert actual.sheets["2"].assets == source_sheet.assets
    assert actual.sheets["2"].frame_runtime == source_sheet.frame_runtime
    assert next(x for x in actual.placements if x.actor == original) == placement
    assert (
        actual.sheets["2"].character_id == source_sheet.character_id and not actual.career_archives
    )
    assert (
        game.inspect(PLAYER, action)["state"] == "complete"
        and game.inspect(PLAYER, root)["state"] == "complete"
    )
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert game.dice.calls == 2


def test_high_already_knowing_operator_causes_status_loss_and_real_selected_no_rewrite(
    ledger, tmp_path, monkeypatch
):
    game, identity, root, action, _, _, _ = rolled(ledger, tmp_path, monkeypatch, (6, 6))
    # Fixture begins with owner2 above owner3; the printed high result now makes her Dog.
    assert state(game).order[-1] == 2
    before = state(game).sheets["2"].model_dump_json()
    answer(
        game,
        ADMIN,
        "am_code_edit",
        options=("edit",),
        text="The operator chooses no replacement this time",
    )
    assert state(game).sheets["2"].model_dump_json() == before
    assert rules.session(state(game), identity).phase == "complete"
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 2


def test_low_real_npc_order_has_no_disobey_and_waits_original_owned_actual_fulfillment(
    ledger, tmp_path, monkeypatch
):
    game, identity, root, action, worker, gateway, _ = rolled(ledger, tmp_path, monkeypatch, (1, 1))
    spoken = "My actual callsign is " + state(game).sheets["2"].callsign
    answer(game, ADMIN, "am_code_order", text=spoken)
    value = rules.session(state(game), identity)
    assert (
        value.order
        and not value.performance
        and game.inspect(PLAYER, action)["state"] != "complete"
    )
    pending = next(x for x in game.choices(PLAYER) if x["kind"] == "am_code_obey")
    with pytest.raises(WorkflowError, match="Disobey"):
        game.respond(
            PLAYER,
            str(uuid4()),
            pending["id"],
            pending["revision"],
            ChoiceAnswer(options=("disobey",), text="I refuse"),
        )
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="disobey_orders",
                parent=action,
                order_id=value.order,
                heat=0,
                context="Cannot manufacture a separate refusal route",
                trigger_confirmed=True,
            ),
        )
    assert game.dice.calls == 2

    async def obey():
        owner = current(2, 904010)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, pending["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert "disobey" not in dict(form.fields[0].options)
        form.values.update(
            behavior=("gritted_teeth",),
            account=spoken,
        )
        await form.confirm.callback(current(2, 904011))
        assert form.completed

    asyncio.run(obey())
    actual = state(game)
    assert (
        rules.session(actual, identity).performance
        and game.inspect(PLAYER, root)["state"] == "complete"
    )
    with ledger.engine.connect() as c:
        orders = t.m2["m2_orders"]
        assert (
            c.scalar(
                sa.select(orders.c.state).where(
                    orders.c.campaign_id == ledger.campaign_id, orders.c.id == value.order
                )
            )
            == "followed"
        )
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert game.dice.calls == 2
