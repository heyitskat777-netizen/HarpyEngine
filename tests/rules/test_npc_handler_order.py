"""The original NPC Handler can send a Girl through her owned Order response."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current
from test_physical_operations import place
from test_privacy_game_delivery import PrivateGateway
from test_world_service import ready

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_npc_orders import NPC_HANDLER, NpcOrderService
from girlframe.services.onboarding import WorkflowError


def test_local_npc_handler_order_reaches_only_original_inbox_and_allows_disobey(ledger):
    world, game = ready(ledger)
    npc = ActorRef(kind="npc", entity="actual-ordinary-handler")
    world.npc(
        ADMIN,
        "make-ordinary-handler",
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Duty Liaison",
            jobs=("handler",),
            detail="The liaison is in this square.",
            cell=(0, 0),
            controller=ADMIN.user_id,
        ),
    )
    with ledger.transaction() as c:
        canon = place(state(game), PLAYER.user_id, mode="outside_frame")
        game.event(c, ADMIN.user_id, "npc-handler-co-presence", "synthetic.position", canon)
    cast = CastService(ActorService(world.missions))
    change(cast, ADMIN, "join", npc)
    service = NpcOrderService(game)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    subsystems=policy.subsystems | {"plays"},
                    activity_specialist_rules=policy.activity_specialist_rules | {NPC_HANDLER},
                )
            )
        )
    )

    async def native_order():
        click = current(ADMIN.user_id, 90430)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_cast(click, cast)
        menu = click.edit_original_response.call_args.kwargs["view"]
        token = next(key for key, _ in menu.options if key.startswith("npc-handler-order:"))
        opening = current(ADMIN.user_id, 90431)
        await opening.response.defer(ephemeral=True)
        await menu.open_item(opening, token)
        form = opening.edit_original_response.call_args.kwargs["view"]
        form.values.update(girl=("2",), instruction="PRIVATE_ORDER: check the archive door.")
        confirmation = current(ADMIN.user_id, 90432)
        await form.confirm.callback(confirmation)
        assert form.completed, confirmation.edit_original_response.call_args_list

    original = state(game)
    assert not service.handler_recipients(PLAYER, 900, npc)["targets"]
    asyncio.run(native_order())
    saved = service.issue(
        ADMIN,
        "90432",
        900,
        npc,
        PLAYER.user_id,
        original.revision,
        "PRIVATE_ORDER: check the archive door.",
        origin_kind="npc_handler",
    )
    worker, gateway = GameWorker(game), PrivateGateway()
    tick(worker, gateway, 3)
    assert not any(x.identity == saved["action_id"] for x in InboxService(ledger).items(OTHER))
    assert any(x["kind"] == "order_response" for x in game.choices(PLAYER))
    with pytest.raises(WorkflowError):
        game.inspect(OTHER, saved["action_id"])
    assert state(game).placements == original.placements
    answer(game, PLAYER, "order_response", options=("disobey",))
    child = game.begin(
        PLAYER,
        "refuse-actual-ordinary-handler",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="disobey_orders",
            parent=saved["action_id"],
            order_id=saved["order_id"],
            heat=0,
            context="I refuse the liaison’s orders.",
            trigger_confirmed=True,
        ),
    )
    assert child["action_id"] and game.dice.calls == 0
    with game.store.engine.connect() as c:
        pending = game.action(c, child["action_id"])
        assert pending["data"]["private_audience"] == [1, 2]
    tick(worker, gateway, 3)
    for listener in (ADMIN, PLAYER):
        answer(game, listener, "tag_window", options=("pass",))
    answer(game, PLAYER, "actor_disobey", options=("tag_heat",), number=1, text="Defiant")
    answer(game, ADMIN, "handler_disobey", flag=False)
    tick(worker, gateway, 3)
    result = game.inspect(PLAYER, child["action_id"])
    assert result["state"] == "complete" and result["result"]["can_disobey"]
    assert game.dice.calls == 1 and not state(game).alpha_broken
    assert gateway.private and {recipient for recipient, _ in gateway.private} == {1, 2}
