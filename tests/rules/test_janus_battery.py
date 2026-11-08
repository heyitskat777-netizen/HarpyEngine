"""Actual reviewed contact, shared raw receipt and owned Living Battery effects."""

from uuid import uuid4

import pytest
from test_frame_control import exposed_core
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput
from girlframe.services.m3_frame_control import FrameControlService
from girlframe.services.onboarding import WorkflowError


def connected(store, tmp_path, monkeypatch, faces=(2, 2)):
    game, caster, core = exposed_core(store, tmp_path, monkeypatch, exposed=False)
    contact = FrameControlService(game)
    identity = contact.propose(
        PLAYER,
        str(uuid4()),
        900,
        caster,
        core,
        "Actual neural jack inserted through the reviewed cockpit spinal access",
    )["id"]
    contact.decide(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "Actual original jack is connected to this Core's actual spinal cord",
    )
    game.dice.faces = faces
    return game, GameWorker(game), Gateway(), core, identity


def start(game, core, key=None):
    return game.begin(
        PLAYER,
        key or str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="living_battery",
            heat=0,
            target_actor=core,
            trigger_confirmed=True,
            context="Use this actual reviewed neural contact",
        ),
    )["action_id"]


def rolled(store, tmp_path, monkeypatch, faces=(2, 2)):
    game, worker, gateway, core, contact = connected(store, tmp_path, monkeypatch, faces)
    identity = start(game, core)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, identity)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), identity)
    pass_tags(game)
    return game, worker, gateway, core, contact, identity


def test_actual_tags_modifier_mid_exact_choices_and_true_unplug_expiry(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, core, contact, identity = rolled(ledger, tmp_path, monkeypatch)
    actual = state(game)
    receipt = game.inspect(PLAYER, identity)["receipt"]
    assert receipt["pre_total"] == 8 and receipt["heat"] == 0
    assert receipt["pre_modifiers"] == [{"source": "battery_tags", "amount": 4}]
    before = actual.sheets["2"].model_copy(deep=True)
    answer(game, PLAYER, "janus_select", options=("cognition", "offset"))
    actual = state(game)
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert len([x for x in actual.sheets["2"].assets if x.battery_asset]) == 2
    assert actual.sheets["2"].heat == before.heat
    assert actual.janus_cores[-1].girl_assets == state(game).janus_cores[-1].girl_assets
    tick(worker, gateway, 4)
    FrameControlService(game).unplug(
        PLAYER,
        str(uuid4()),
        contact,
        state(game).revision,
        "Actual original Pilot physically removes the neural jack",
    )
    assert not any(x.battery_asset for x in state(game).sheets["2"].assets)
    assert state(game).battery_links[-1].phase == "unplugged" and game.dice.calls == 1


def test_actual_private_brain_question_owned_response_and_no_handler_leak(
    ledger, tmp_path, monkeypatch
):
    game, _, _, core, _, identity = rolled(ledger, tmp_path, monkeypatch)
    answer(
        game,
        PLAYER,
        "janus_select",
        options=("heat", "question"),
        number=3,
        text="PRIVATE_ACTUAL_NEURAL_QUESTION",
    )
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    assert not game.choices(ADMIN)
    answer(game, OTHER, "janus_answer", text="PRIVATE_ACTUAL_OTHER_MIND_ANSWER")
    assert (
        game.inspect(PLAYER, identity)["result"]["brain_answer"]
        == "PRIVATE_ACTUAL_OTHER_MIND_ANSWER"
    )
    assert "brain_answer" not in game.inspect(ADMIN, identity)["result"]
    assert game.inspect(PLAYER, identity)["state"] == "complete"


def test_actual_low_erases_one_tag_and_chooses_one_without_reroll(ledger, tmp_path, monkeypatch):
    game, _, _, core, _, identity = rolled(ledger, tmp_path, monkeypatch, faces=(1, 1))
    tag = state(game).janus_cores[-1].baseline_tags["drugged"]
    answer(game, PLAYER, "janus_erase", options=(tag,))
    assert all(x.id != tag for x in state(game).janus_cores[-1].tags)
    answer(game, PLAYER, "janus_select", options=("heat",), number=4)
    assert state(game).sheets["2"].heat == 4 and game.dice.calls == 1
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    with pytest.raises(WorkflowError):
        start(game, core)


def test_actual_high_exact_four_and_native_owned_select_and_answer(ledger, tmp_path, monkeypatch):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_janus_play import open_battery_choice

    game, _, _, core, _, identity = rolled(ledger, tmp_path, monkeypatch, faces=(6, 6))
    before = state(game).sheets["2"].heat
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "janus_select")
    with pytest.raises(WorkflowError):
        from girlframe.engine.m2 import ChoiceAnswer

        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("heat",), number=2),
        )
    assert state(game).sheets["2"].heat == before

    async def run():
        interaction = current(2, 97501)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_battery_choice(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(
            choices=("heat", "cognition", "offset", "question"),
            heat=("2",),
            question="PRIVATE_NATIVE_BRAIN_QUESTION",
        )
        await form.confirm.callback(current(2, 97502))
        assert form.completed
        row2 = next(x for x in game.choices(OTHER) if x["kind"] == "janus_answer")
        other = current(3, 97503)
        await other.response.defer(ephemeral=True)
        await open_battery_choice(other, game, row2["id"])
        actual = other.edit_original_response.call_args.kwargs["view"]
        assert isinstance(actual, NativeForm)
        actual.values.update(answer="PRIVATE_NATIVE_ACTUAL_CORE_ANSWER")
        await actual.confirm.callback(current(3, 97504))
        assert actual.completed

    asyncio.run(run())
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    assert state(game).sheets["2"].heat == before + 2


def test_true_private_mind_message_own_source_replay_native_transition_and_unplug(
    ledger, tmp_path, monkeypatch
):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_janus_play import open_brain_link
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.services.inbox import InboxService
    from girlframe.services.m3_janus_play import BatteryService

    game, worker, gateway, core, contact, identity = rolled(ledger, tmp_path, monkeypatch)
    answer(
        game,
        PLAYER,
        "janus_select",
        options=("question", "heat"),
        number=1,
        text="Private question",
    )
    answer(game, OTHER, "janus_answer", text="Actual response")
    value = state(game).battery_links[-1]
    service = BatteryService(game)
    original = state(game)
    with pytest.raises(WorkflowError):
        service.get(ADMIN, value.id)
    result = service.send(
        OTHER, "actual-private-message", value.id, original.revision, core, "PRIVATE_CORE_MIND_ONLY"
    )
    assert (
        service.send(
            OTHER,
            "actual-private-message",
            value.id,
            original.revision,
            core,
            "PRIVATE_CORE_MIND_ONLY",
        )
        == result
    )
    assert len(state(game).battery_links[-1].messages) == 1
    assert any(x.task == "m3_janus_mind" for x in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError):
        service.send(
            OTHER,
            str(uuid4()),
            value.id,
            state(game).revision,
            current_ref(state(game), 3),
            "Cannot borrow my unrelated PC as the Core mind",
        )

    async def run():
        interaction = current(2, 97511)
        await interaction.response.defer(ephemeral=True)
        await open_brain_link(interaction, game, value.id)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(
            speaker=(current_ref(state(game), 2).token,), message="PRIVATE_NATIVE_REPLY"
        )
        response = current(2, 97512)
        await form.confirm.callback(response)
        nextform = response.edit_original_response.call_args.kwargs["view"]
        assert isinstance(nextform, NativeForm) and nextform is not form
        assert "PRIVATE_NATIVE_REPLY" in nextform.text()

    asyncio.run(run())
    assert len(state(game).battery_links[-1].messages) == 2
    tick(worker, gateway, 5)
    FrameControlService(game).unplug(
        PLAYER,
        str(uuid4()),
        contact,
        state(game).revision,
        "Actual physical unplug terminates brain channel",
    )
    assert not service.get(OTHER, value.id)["can_send"]
    with pytest.raises(WorkflowError):
        service.send(
            OTHER, str(uuid4()), value.id, state(game).revision, core, "No post-unplug message"
        )


def test_actual_effect_transaction_rollback_stale_response_and_raw_receipt_replay(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m2 import ChoiceAnswer

    game, _, _, core, _, identity = rolled(ledger, tmp_path, monkeypatch)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "janus_select")
    before = state(game).model_dump_json()
    actual = game.event

    def fail(*args, **kwargs):
        if args[3] == "m3.choice_resolved":
            raise RuntimeError("Synthetic final audit failure")
        return actual(*args, **kwargs)

    monkeypatch.setattr(game, "event", fail)
    value = ChoiceAnswer(options=("heat", "cognition"), number=2)
    with pytest.raises(RuntimeError):
        game.respond(PLAYER, "actual-failed-battery-effect", row["id"], row["revision"], value)
    assert state(game).model_dump_json() == before
    monkeypatch.setattr(game, "event", actual)
    result = game.respond(PLAYER, "actual-failed-battery-effect", row["id"], row["revision"], value)
    assert (
        game.respond(PLAYER, "actual-failed-battery-effect", row["id"], row["revision"], value)
        == result
    )
    with pytest.raises(WorkflowError):
        game.respond(PLAYER, str(uuid4()), row["id"], row["revision"], value)
    assert game.roll(PLAYER, "replay-original-battery-roll", identity)["receipt"]["pre_total"] == 8
    assert game.dice.calls == 1 and len(state(game).battery_links) == 1
    game.rebuild()
    assert len(state(game).battery_links) == 1
