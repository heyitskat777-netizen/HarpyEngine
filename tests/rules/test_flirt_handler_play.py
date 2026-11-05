"""M3 high Flirt grants the real Handler Play; frozen M2 keeps its explicit Brief subset."""

import asyncio
from uuid import uuid4

import pytest
from test_handler_plays import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.services.inbox import InboxService
from girlframe.services.onboarding import WorkflowError


def flirt(store):
    service, game = ready(store)
    game.dice.faces = (6, 6)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            target=3,
            heat=0,
            context="Actual noticed interaction",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_flirt",
        options=("name",),
        fields={"extra": "handler"},
        text="Actual high-tier complication",
    )
    answer(game, OTHER, "target_flirt", text="The actual original participant's answer")
    return service, game, worker, gateway, action


def test_actual_m3_flirt_holds_source_for_full_owned_handler_effect_not_generic_brief(ledger):
    service, game, worker, gateway, action = flirt(ledger)
    canon = state(game)
    grant = canon.handler_plays[-1]
    assert grant.source == "required" and grant.clause == "flirt.high.handler"
    assert grant.chooser_actor is None and grant.chooser_controller == ADMIN.user_id
    assert set(grant.targets) == {current_ref(canon, 2), current_ref(canon, 3)}
    assert game.inspect(PLAYER, action)["state"] != "complete"
    request = next(x for x in game.choices(ADMIN) if x["kind"] == "handler_brief")
    with pytest.raises(WorkflowError, match="actual source-owned Handler Play"):
        answer(game, ADMIN, "handler_brief", options=("brief",), text="A text bypass")
    assert (
        next(x for x in game.choices(ADMIN) if x["kind"] == "handler_brief")["id"] == request["id"]
    )
    assert next(x for x in InboxService(ledger).items(ADMIN) if x.identity == grant.id).incoming

    async def run():
        owner = current(1, 99101)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, request["id"])
        menu = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(menu, Picker)
        assert {"brief", "mess", "expectation"} <= dict(menu.options).keys()
        assert not await menu.interaction_check(current(2))

    asyncio.run(run())
    original = state(game)
    view = service.get(ADMIN, grant.id)
    service.submit(
        ADMIN,
        "actual-high-flirt-handler-status",
        grant.id,
        view["game_revision"],
        "mess",
        Effect(
            kind="status",
            target=current_ref(original, 2),
            status=-1,
            account="Actual GM's source-bound response",
        ),
    )
    assert state(game).order != original.order
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    with ledger.engine.connect() as c:
        result = game.action(c, action)["data"]
        assert game.lock(c, 900)["state"] == "held"
    assert result["result"]["handler_play"] == "status"
    assert result["receipt"]["faces"] == [6, 6]
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
