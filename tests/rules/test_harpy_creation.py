"""An original new Harpy has owned printed Assets and factual runtime review."""

import asyncio

import pytest
from test_cast_service import change
from test_harpy_actor_plays import begin
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_ui import current
from test_world_service import ready

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m3_harpy_creation import FRAME_ASSETS, GIRL_ASSETS, RULE, Draft, offers
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
from girlframe.engine.m3_void_state import HarpyIdentity
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_harpy_creation import HarpyCreationService
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("accept", (True, False))
def test_actual_harpy_creation_uses_native_owned_invitation_and_original_assets(ledger, accept):
    world, game = ready(ledger)
    access = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": access.model_copy(update={"subsystems": access.subsystems | {"plays"}})
        }
    )
    service = HarpyCreationService(game)
    with pytest.raises(WorkflowError, match="implementation and review"):
        service.menu(ADMIN)
    access = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": access.model_copy(
                update={"activity_specialist_rules": access.activity_specialist_rules | {RULE}}
            )
        }
    )
    cast = CastService(ActorService(world.missions))
    original = state(game)
    with pytest.raises(WorkflowError):
        service.invite(PLAYER, "wrong-issuer", original.revision, PLAYER.user_id, (0, 0))
    with pytest.raises(WorkflowError, match="actual map square"):
        service.invite(ADMIN, "invalid-square", original.revision, PLAYER.user_id, (100, 100))

    async def invite():
        request = current(ADMIN.user_id, 71100)
        request.channel_id = 900
        await request.response.defer(ephemeral=True)
        await open_cast(request, cast)
        picker = request.edit_original_response.call_args.kwargs["view"]
        choice = current(ADMIN.user_id, 71101)
        choice.channel_id = 900
        await choice.response.defer(ephemeral=True)
        await picker.open_item(choice, "invite-harpy")
        form = choice.edit_original_response.call_args.kwargs["view"]
        form.values.update(controller=(str(PLAYER.user_id),), cell="0,0")
        submitted = current(ADMIN.user_id, 71102)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.followup.send.call_args

    asyncio.run(invite())
    receipt = service.invite(ADMIN, "71102", original.revision, PLAYER.user_id, (0, 0))
    (offer,) = offers(state(game))
    assert offer.actor.entity == receipt["id"] and state(game).world.pilots == original.world.pilots
    inbox = InboxService(ledger)
    assert not any(x.task == "m3_harpy_creation" for x in inbox.items(OTHER))
    with pytest.raises(WorkflowError, match="original invited controller"):
        service.get(OTHER, receipt["id"])
    ledger.engine.dispose()
    data = service.get(PLAYER, receipt["id"])
    with pytest.raises(WorkflowError, match="STALE_HARPY_CREATION"):
        service.respond(PLAYER, "stale", receipt["id"], data["revision"] - 1, None)
    ledger.safety(PLAYER, "pause-creation", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.respond(PLAYER, "paused", receipt["id"], data["revision"], None)
    ledger.safety(PLAYER, "resume-creation", ledger.status(PLAYER)["revision"], pause=False)

    draft = Draft(
        name="Indigo",
        girl=tuple(
            AssetChoice(name=x, description="Distinct description " + str(i))
            for i, x in enumerate(GIRL_ASSETS[:3])
        ),
        frame=tuple(
            AssetChoice(name=x, description="Distinct description " + str(i))
            for i, x in enumerate(FRAME_ASSETS[:4], 3)
        ),
    )
    with pytest.raises(ValueError, match="distinct starting Assets"):
        Draft.model_validate(draft.model_dump() | dict(girl=(draft.girl[0],) * 3))

    async def respond():
        request = current(PLAYER.user_id, 71110)
        request.channel_id = 900
        await request.response.defer(ephemeral=True)
        entry = next(x for x in inbox.items(PLAYER) if x.task == "m3_harpy_creation")
        await InboxView(inbox, PLAYER.user_id).route(request, entry)
        form = request.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(OTHER.user_id))
        form.values["choice"] = ("accept" if accept else "decline",)
        if accept:
            form.values.update(girl=GIRL_ASSETS[:3], frame=FRAME_ASSETS[:4])
        choose = current(PLAYER.user_id, 71111)
        await choose.response.defer(ephemeral=True)
        await form.confirm.callback(choose)
        assert form.completed, choose.followup.send.call_args
        if accept:
            details = choose.edit_original_response.call_args.kwargs["view"]
            details.values.update(
                {"name": draft.name}
                | {str(i): x.description for i, x in enumerate((*draft.girl, *draft.frame))}
            )
            final = current(PLAYER.user_id, 71112)
            await details.confirm.callback(final)
            assert details.completed, final.followup.send.call_args

    revision = state(game).revision
    asyncio.run(respond())
    result = service.respond(
        PLAYER,
        "71112" if accept else "71111",
        offer.actor.entity,
        revision,
        draft if accept else None,
    )
    current_state = state(game)
    assert current_state.sheets == original.sheets
    assert not any(x.task == "m3_harpy_creation" for x in inbox.items(PLAYER))
    if not accept:
        assert result["phase"] == "declined" and current_state.world.pilots == original.world.pilots
        return
    assert result["phase"] == "accepted"
    saved = next(x for x in current_state.world.pilots if x.id == offer.actor.entity)
    assert [x.family for x in saved.assets] == ["girl"] * 3 + ["frame"] * 4
    assert [x.name for x in saved.assets] == list(GIRL_ASSETS[:3] + FRAME_ASSETS[:4])
    assert saved.controller == PLAYER.user_id and not saved.revealed
    assert offer.actor.entity not in str(world.get(OTHER)["world"])

    runtime = HarpyDefeatService(ledger, game)
    request = runtime.propose_runtime(
        PLAYER,
        "harpy-facts",
        current_state.revision,
        NativeHarpyFacts(
            actor=offer.actor,
            linked=True,
            girl_cell=(0, 0),
            frame_cell=(0, 0),
            heat=0,
            frame_shutdown=False,
            body_incapacitated=False,
            custody="free",
            identities=(HarpyIdentity(id="original-free", name="Free"),),
            tags=(),
            facts_confirmed=True,
            account="The original owner's actual independent runtime.",
        ),
    )
    runtime.review_setup(
        ADMIN,
        "verified-harpy-facts",
        request["id"],
        state(game).revision,
        True,
        "The actual human GM verifies the original runtime.",
    )
    change(cast, PLAYER, "join", offer.actor)
    game.dice.faces = (2, 3)
    action = begin(ActorPlayService(game), offer.actor)
    tick(GameWorker(game), Gateway(), 3)
    for viewer in (ADMIN, PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(game, PLAYER, "actor_keep", options=("beautiful",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual human GM rules.")
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
