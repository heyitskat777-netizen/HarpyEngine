"""A real mandatory Dormant Dive survives an actual source-owned no-roll prohibition."""

import asyncio
from uuid import uuid4

import pytest
from test_adjudication_service import forbid
from test_battle_dormant import pay
from test_battle_pipeline import dormant_source, table
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_adjudication import open_adjudication
from girlframe.discord_adapter.m3_battle_dormant import open_dormant
from girlframe.engine.m2 import PlayInput
from girlframe.services.m3_adjudication import AdjudicationService
from girlframe.services.m3_battle_dormant import DormantService
from girlframe.services.onboarding import WorkflowError


def test_actual_forbidden_dormant_dive_uses_manual_receipt_and_real_downstream_choices(
    ledger, monkeypatch
):
    game, worker, gateway, root, work = dormant_source(ledger, monkeypatch, close=True)
    forbid(game, 2, "dive_deep")
    service = DormantService(ledger, game)
    assert pay(service, game, work)["phase"] == "dive"
    before = state(game).sheets["2"].heat

    async def native_source():
        caller = current(2, 99500)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_dormant(caller, service, work)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert {x.key for x in form.fields} == {"piloting", "account"}
        assert "manual no-roll" in form.instructions

    asyncio.run(native_source())
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            parent=root,
            source_work=work,
            heat=0,
            piloting=True,
            trigger_confirmed=True,
            context="Actual required Dormant Dive",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, child)["state"] == "awaiting_adjudication"
    assert game.dice.calls == 1 and state(game).sheets["2"].heat == before
    adjudication = AdjudicationService(ledger)
    request = next(x for x in game.choices(ADMIN) if x["kind"] == "manual_adjudication")
    data = adjudication.get(ADMIN, request["id"])
    with pytest.raises(WorkflowError):
        adjudication.submit(
            OTHER, str(uuid4()), request["id"], data["revision"], 12, "Not my question"
        )

    async def native_manual():
        caller = current(1, 99501)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_adjudication(caller, adjudication, request["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert {x.key for x in form.fields} == {"total", "reason"}
        assert not await form.interaction_check(current(3))
        form.values.update(total="8", reason="Actual human no-roll ruling of mandatory Dive")
        await form.confirm.callback(current(1, 99502))
        assert form.completed

    asyncio.run(native_manual())
    result = game.inspect(PLAYER, child)
    receipt = result["receipt"]
    assert receipt["faces"] is None and receipt["rng_source"] == "manual_adjudication"
    assert receipt["heat"] == 0 and game.dice.calls == 1
    assert receipt["adjudication"]["required"]["source_id"] == work
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("erase_identity_and_table_question",),
        text="Actual connection",
    )
    identity = next(x for x in state(game).sheets["2"].identities if not x.protected)
    answer(game, PLAYER, "dive_effect", fields={"identity": identity.id}, text="What did you see?")
    for human in (ADMIN, PLAYER, OTHER):
        answer(game, human, "dive_table_answer", text="Actual answer " + str(human.user_id))
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert service.get(PLAYER, work)["state"] == "resolved"
    assert game.inspect(PLAYER, root)["state"] != "complete"
    table(game)
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 1
    assert any(x.play == "dive_deep" for x in state(game).sheets["2"].blocked_plays)


def test_converted_original_inherited_forbidden_dive_keeps_real_source_and_uses_no_rng(
    ledger, monkeypatch
):
    from test_void_service import five_no, respond

    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.services.m3_actor_plays import ActorPlayService
    from girlframe.services.m3_void import VoidService

    game, worker, gateway, root, work = dormant_source(
        ledger, monkeypatch, close=True, prevoid_frame=True, girl="ALPHA"
    )
    forbid(game, 2, "dive_deep")
    service = DormantService(ledger, game)
    data = service.get(PLAYER, work)
    selected = next(x for x in data["assets"] if x["family"] == "frame")
    assert (
        service.alter(
            PLAYER,
            str(uuid4()),
            work,
            data["revision"],
            data["game_revision"],
            selected["id"],
            "Actual final Frame Void alteration",
            piloting=True,
        )["phase"]
        == "thresholds"
    )
    threshold = service.get(PLAYER, work)["body"]["thresholds"][0]
    void = VoidService(ledger)
    five_no(void, threshold)
    choice = void.get(PLAYER, threshold)["rebirth_choice"] | dict(
        new_identities=["Actual reborn self"], account="Actual irreversible rebirth"
    )
    respond(void, threshold, "rebirth", dict(choice=choice, account="Actual original rebirth"))
    current = service.get(PLAYER, work)
    service.resume_converted_role(PLAYER, str(uuid4()), work, current["revision"])
    actual = ActorRef.model_validate(current["actor"])
    actors = ActorPlayService(game)
    source = actors.preview(PLAYER, 900, actual)
    before = state(game).harpy_states[-1].heat
    child = actors.begin(
        PLAYER,
        str(uuid4()),
        900,
        actual,
        source["actor"]["source_sha256"],
        None,
        source["cast_revision"],
        PlayInput(
            play="dive_deep",
            heat=0,
            parent=root,
            source_work=work,
            context="Actual transformed Harpy forced connection",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, child)["state"] == "awaiting_adjudication"
    assert game.dice.calls == 1 and state(game).harpy_states[-1].heat == before
    adjudication = AdjudicationService(ledger)
    request = next(x for x in game.choices(ADMIN) if x["kind"] == "manual_adjudication")
    data = adjudication.get(ADMIN, request["id"])
    receipt = adjudication.submit(
        ADMIN,
        str(uuid4()),
        request["id"],
        data["revision"],
        8,
        "Actual original prohibition carries through rebirth; "
        "actual mandatory source resolved manually",
    )["receipt"]
    assert (
        receipt["faces"] is None
        and receipt["adjudication"]["required"]["actor"] == current["actor"]
    )
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("erase_identity_and_table_question",),
        text="Actual source connection",
    )
    ordinary = next(x for x in state(game).harpy_states[-1].identities if not x.protected)
    answer(game, PLAYER, "dive_effect", fields={"identity": ordinary.id}, text="What remains?")
    for human in (ADMIN, PLAYER, OTHER):
        answer(game, human, "dive_table_answer", text="My actual answer " + str(human.user_id))
    assert game.inspect(PLAYER, child)["state"] == "complete"
    table(game)
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 1
    assert any(x.play == "dive_deep" for x in state(game).harpy_states[-1].blocked_plays)
