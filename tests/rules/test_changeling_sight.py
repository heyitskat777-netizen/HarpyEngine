"""A real earned String sees through the original eyes in their bound legacy scene."""

import asyncio
from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_changeling import define, ready, roll
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_changeling import open_changeling
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_changeling import ChangelingService, prove_fingers, prove_node
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def test_native_earned_sight_uses_actual_remote_legacy_scene_and_ends_at_rebind(
    ledger, tmp_path, monkeypatch
):
    # Prior bodies/world/resources in ready are synthetic. Speech, roll, Bond,
    # String, cast withdrawal, new scene and all sight effects use real services.
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    action = roll(game, worker, gateway, source=define(game, controls))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    node = next(x for x in rules.records(state(game), rules.String) if x.origin == "deepen")
    assert node.actor == actor and node.subject.actor == target and not node.spent_event
    receipt, rolls = game.inspect(PLAYER, action)["receipt"], game.dice.calls
    cast_change(CastService(ActorService(MissionService(ledger))), OTHER, "withdraw", target)
    remote = game.bind_scene(ADMIN, str(uuid4()), 901)["scene"]
    game.join_scene(OTHER, str(uuid4()), 901)
    assert not any(x.id == remote for x in state(game).scene_casts)
    before = state(game).model_dump_json()
    resources = state(game).sheets["2"].model_dump_json()
    # A known channel or the caster's scene is not authority for the eyes' scene.
    with pytest.raises(WorkflowError, match="eyes' real current scene"):
        controls.fingers(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            900,
            node.id,
            "sight",
            "I must use the actual eyes' scene",
            subject_scene=next(x.id for x in state(game).scene_casts if x.channel == 900),
        )
    assert state(game).model_dump_json() == before

    async def initiate():
        own = current(2, 993101)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_changeling(own, controls)
        menu = own.edit_original_response.call_args.kwargs["view"]
        menu.values["entry"] = ("fingers",)
        response = current(2, 993102)
        response.channel_id = 900
        await menu.confirm.callback(response)
        form = response.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 993103))
        form.values.update(
            node=(node.id,),
            kind=("sight",),
            account="I spend my earned String to see through her eyes in her actual scene",
        )
        confirm = current(2, 993104)
        confirm.channel_id = 900
        await form.confirm.callback(confirm)
        assert form.completed

    asyncio.run(initiate())
    use = next(x for x in rules.records(state(game), rules.Fingers) if x.node == node.id)
    view = rules.record(state(game), rules.EyeView, use.id)
    assert use.cast.channel == 900 and view.cast.channel == 901 and view.cast.id == remote
    assert view.subject == node.subject and {x.actor for x in view.cast.roles} == {target}
    assert all(x.source_event for x in view.cast.roles)
    assert view.cast.facilitator is None and view.cast.facilitator_source is None
    assert use.cast.facilitator == 1  # Only the caster's source needs its original Handler.
    with ledger.engine.connect() as c:
        assert game.scene(c, 901)["participants"] == [3]
    assert not any(x.id == remote for x in state(game).scene_casts)
    with ledger.engine.connect() as c:
        assert prove_node(game, c, state(game), node.id).spent_by == use.id
        assert rules.record(_history(c, game, view.event), rules.EyeView, use.id) == view
    pending = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        controls.observe_eyes(PLAYER, str(uuid4()), state(game).revision, use.id, "Invented sight")
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, use.id)
    assert state(game).model_dump_json() == pending

    async def answer_and_observe():
        own = current(3, 993105)
        await own.response.defer(ephemeral=True)
        await open_changeling(own, controls, use.id)
        counter = own.edit_original_response.call_args.kwargs["view"]
        counter.values["kind"] = ("pass",)
        await counter.confirm.callback(current(3, 993106))
        assert counter.completed
        for offset, text in enumerate(("PRIVATE_EYES: I see a red door", "The red door opens")):
            observer = current(3, 993110 + offset * 2)
            observer.channel_id = 901
            await observer.response.defer(ephemeral=True)
            await open_changeling(observer, ChangelingService(game), use.id)
            form = observer.edit_original_response.call_args.kwargs["view"]
            assert [x.key for x in form.fields] == ["observation"]
            form.values["observation"] = text
            await form.confirm.callback(current(3, 993111 + offset * 2))
            assert form.completed
        reopened = current(2, 993120)
        await reopened.response.defer(ephemeral=True)
        await open_changeling(reopened, ChangelingService(game), use.id)
        history = reopened.edit_original_response.call_args.kwargs["view"]
        text = "".join(page.content for page in history.pages)
        assert r"PRIVATE\_EYES: I see a red door" in text and "The red door opens" in text
        assert not await history.interaction_check(current(1, 993121))

    asyncio.run(answer_and_observe())
    reopened = GameService(ledger, dice=game.dice)
    saved = state(reopened)
    observations = rules.records(saved, rules.EyeObservation)
    assert len(observations) == 2
    assert all(
        x.scene == remote and x.subject == node.subject and x.controller == 3 for x in observations
    )
    with ledger.engine.connect() as c:
        assert prove_fingers(reopened, c, saved, use.id).completed_event
    assert reopened.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == rolls
    assert saved.sheets["2"].model_dump_json() == resources
    with pytest.raises(WorkflowError):
        controls.fingers(PLAYER, str(uuid4()), saved.revision, 900, node.id, "sight", "Again")
    assert state(game).model_dump_json() == saved.model_dump_json()

    # Closing and reusing the same channel cannot extend an old scene's sight.
    game.close_scene(ADMIN, str(uuid4()), 901)
    new_scene = game.bind_scene(ADMIN, str(uuid4()), 901)["scene"]
    assert new_scene != remote
    game.join_scene(OTHER, str(uuid4()), 901)
    final = state(game).model_dump_json()
    shown = ChangelingService(reopened).view(OTHER, use.id)
    assert not shown["observe"] and not shown["effect"]["active"]
    with pytest.raises(WorkflowError, match="original eyes"):
        controls.observe_eyes(OTHER, str(uuid4()), state(game).revision, use.id, "A later scene")
    assert state(game).model_dump_json() == final
    assert rules.records(state(game), rules.EyeObservation) == observations
    assert "PRIVATE_EYES" not in str(gateway.messages)
