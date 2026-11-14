"""The printed mid Body of Clay appearance-copy alternative is an owned native choice."""

import asyncio
from uuid import uuid4

import pytest
from test_changeling import buy, ready, roll
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_changeling import open_changeling
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_changeling import ChangelingService, prove_acquisition
from girlframe.services.m3_changeling_body import current_appearance
from girlframe.services.onboarding import WorkflowError


def test_native_mid_clay_copies_disclosed_appearance_without_dummy_facets(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    # The shared fixture declares synthetic prior bodies/world/resources. Paid
    # acquisition, appearance disclosure, receipt and resulting changes are real.
    permissions = state(game).sheets["2"].permissions
    buy(game, controls, rules.CLAY)
    held = rules.held(state(game), actor, rules.CLAY)
    assert held and state(game).sheets["2"].permissions == permissions - 2
    with ledger.engine.connect() as c:
        prove_acquisition(game, c, state(game), held)
    appearance = {
        "features": "A narrow face with copper curls",
        "age": "An adult in their thirties",
        "body": "A tall broad-shouldered build",
        "sex": "The original person's described adult sex characteristics",
        "voice": "A soft low voice with a clipped cadence",
    }
    recorded = controls.appearance(
        OTHER, str(uuid4()), state(game).revision, 900, target, appearance
    )["id"]
    disclosed = controls.disclose_appearance(
        OTHER, str(uuid4()), state(game).revision, 900, recorded, actor
    )["id"]
    source_disclosure = rules.record(state(game), rules.AppearanceDisclosure, disclosed)
    before_roll = state(game)
    action = roll(game, worker, gateway, play="changeling_body_of_clay")
    decision = next(x for x in game.choices(PLAYER) if x["kind"] == "changeling_clay_owner")
    detail = game.decision(PLAYER, decision["id"])["detail"]
    assert detail["minimum"] == detail["maximum"] == 2
    assert [x["id"] for x in detail["copies"]] == [disclosed]
    receipt = game.inspect(PLAYER, action)["receipt"]
    rolls = game.dice.calls
    source = rules.session(state(game), action)
    assert source.total == 8 and source.frame == rules.frame(state(game), actor)
    assert source.brain.actor == actor and source.owner_change_event is None
    assert state(game).sheets["2"].heat == before_roll.sheets["2"].heat - 1
    pending = state(game).model_dump_json()

    async def choose_copy():
        own = current(2, 992101)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, decision["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        facets = next(x for x in form.fields if x.key == "facets")
        assert facets.minimum == 0 and facets.maximum == 2 and not facets.required
        assert not await form.interaction_check(current(3, 992102))
        form.values["account"] = "I choose the actual disclosed appearance instead of two facets"
        # Neither route must not become an empty or auto-selected body change.
        await form.confirm.callback(current(2, 992103))
        assert not form.completed and state(game).model_dump_json() == pending
        # Do not silently discard a player's simultaneously selected changes.
        form.values.update(facets=("features", "voice"), copy=(disclosed,))
        await form.confirm.callback(current(2, 992104))
        assert not form.completed and state(game).model_dump_json() == pending
        del form.values["facets"]
        await form.confirm.callback(current(2, 992105))
        assert form.completed
        completed = state(game).model_dump_json()
        await form.confirm.callback(current(2, 992106))
        assert state(game).model_dump_json() == completed

    asyncio.run(choose_copy())
    changed = rules.session(state(game), action)
    patch = rules.record(state(game), rules.FacetChange, changed.owner_change_event)
    assert patch.values == appearance and patch.copied_from == target
    assert patch.copied_source == source_disclosure.event
    assert patch.actor == actor and patch.brain == source.brain and patch.frame == source.frame
    assert patch.author == actor and patch.controller == 2
    assert current_appearance(state(game), actor, source.brain.vessel) == appearance
    assert state(game).sheets["2"].girl == before_roll.sheets["2"].girl
    assert state(game).sheets["2"].assets == before_roll.sheets["2"].assets
    assert state(game).sheets["3"].model_dump_json() == before_roll.sheets["3"].model_dump_json()
    assert changed.taste_event is None and game.inspect(PLAYER, action)["state"] != "complete"

    async def handler_taste():
        request = next(x for x in game.choices(ADMIN) if x["kind"] == "changeling_taste")
        handler = current(1, 992107)
        await handler.response.defer(ephemeral=True)
        await open_choice(handler, game, request["id"])
        form = handler.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2, 992108))
        form.values.update(taste=("yes",), account="This actual appearance is more to my tastes")
        await form.confirm.callback(current(1, 992109))
        assert form.completed

    asyncio.run(handler_taste())
    reopened = GameService(game.store, dice=game.dice)
    saved = state(reopened)
    final = rules.session(saved, action)
    assert final.completed_event and final.taste_event and final.handler_change_event is None
    assert saved.order == (2, 3)
    assert reopened.inspect(PLAYER, action)["state"] == "complete"
    assert reopened.inspect(PLAYER, action)["receipt"] == receipt
    assert game.dice.calls == rolls == 1
    assert rules.held(saved, actor, rules.CLAY) == held
    assert saved.sheets["2"].permissions == permissions - 2
    assert current_appearance(saved, actor, final.brain.vessel) == appearance
    with pytest.raises(WorkflowError):
        ChangelingService(reopened).view(OTHER, action)

    async def history():
        own = current(2, 992110)
        await own.response.defer(ephemeral=True)
        await open_changeling(own, ChangelingService(reopened), action)
        view = own.edit_original_response.call_args.kwargs["view"]
        text = "".join(x.content for x in view.pages)
        assert "Completed" in text and all(value in text for value in appearance.values())
        assert not await view.interaction_check(current(3, 992111))

    asyncio.run(history())
