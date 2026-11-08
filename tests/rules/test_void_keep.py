"""Mockingbird resists with a real owned Keep, retaining held chat through failed resistance."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_dive import threshold_source
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current
from test_void_service import five_no, respond

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_void_keep import open_keep
from girlframe.engine.m2 import PlayInput
from girlframe.services.m3_void import VoidService
from girlframe.services.onboarding import WorkflowError


def pending(store):
    game, worker, gateway, parent, work = threshold_source(store, girl="MOCKINGBIRD")
    assert VoidService(store).get(PLAYER, work)["stage"] == "resist_pending"
    return game, worker, gateway, parent, work


def keep(game, worker, gateway, parent, work, *, controlled=True, enough=True):
    game.dice.faces = (4, 4)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            source_work=work,
            parent=parent,
            heat=0,
            context="Actual resistance to the corrupt Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_keep",
        options=("in_control", "tough") if controlled else ("tough", "sexy"),
        denied=("sexy",) if controlled else ("in_control",),
    )
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=enough,
        text="The Handler's actual sufficient-result ruling for this resistance",
    )
    return child


def test_actual_nested_keep_control_and_handler_ruling_prevent_threshold_and_complete_parent(
    ledger,
):
    game, worker, gateway, parent, work = pending(ledger)
    child = keep(game, worker, gateway, parent, work)
    assert game.dice.calls == 2
    assert VoidService(ledger).get(PLAYER, work)["stage"] == "prevented"
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    tick(worker, gateway, 6)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


@pytest.mark.parametrize("controlled,enough", [(False, True), (True, False)])
def test_failed_keep_retains_owned_threshold_and_chat_until_actual_void_rebirth(
    ledger, controlled, enough
):
    game, worker, gateway, parent, work = pending(ledger)
    original = state(game).sheets["2"]
    child = keep(game, worker, gateway, parent, work, controlled=controlled, enough=enough)
    assert game.inspect(PLAYER, child)["state"] == "awaiting_choices"
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    assert next(x for x in game.choices(PLAYER) if x["kind"] == "void_keep_threshold")
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "held"
    service = VoidService(ledger)
    assert service.get(PLAYER, work)["stage"] == "enclosed"
    five_no(service, work)
    view = service.get(PLAYER, work)
    choice = view["rebirth_choice"] | dict(
        retained_identities=[original.identities[1].id],
        new_identities=["Actual new self"],
        account="Actual irreversible owner-chosen rebirth",
    )
    respond(service, work, "save_rebirth", dict(choice=choice, account="Actual owned choices"))
    respond(service, work, "rebirth", dict(choice=choice, account="Actual irreversible decision"))
    assert "2" not in state(game).sheets and state(game).harpy_states
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    tick(worker, gateway, 8)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        outgoing = t.m2["m2_outbox"]
        outcomes = list(
            c.scalars(
                sa.select(outgoing.c.id).where(
                    outgoing.c.campaign_id == ledger.campaign_id,
                    outgoing.c.action_id == child,
                    sa.func.json_extract(outgoing.c.body_json, "$.kind") == "outcome",
                )
            )
        )
    assert len(outcomes) == 1 and game.dice.calls == 2


def test_native_keep_starts_real_child_and_reopen_resumes_without_duplicate_roll(ledger):
    game, worker, gateway, parent, work = pending(ledger)

    async def run():
        owner = current(2, 82101)
        await owner.response.defer(ephemeral=True)
        await open_keep(owner, game, work)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(1, 82102))
        form.values.update(heat=("0",), account="Actual original owner's resistance")
        await form.confirm.callback(current(2, 82103))
        assert form.completed
        await open_keep(owner, game, work)

    asyncio.run(run())
    with ledger.engine.connect() as c:
        actions = t.m2["m2_actions"]
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(actions)
                .where(actions.c.campaign_id == ledger.campaign_id, actions.c.parent_id == parent)
            )
            == 1
        )
    assert game.dice.calls == 1


def test_standalone_physical_entry_failed_keep_holds_its_own_chat_without_an_invented_parent(
    ledger,
):
    from test_cockpit_service import command, placed
    from test_m2_game import Dice, Gateway

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.services.m3_void import source

    physical, game = placed(ledger)
    before, choice = command(physical)
    physical.operate(PLAYER, str(uuid4()), before["game_revision"], choice)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    with ledger.transaction() as c:
        canon = state(game)
        for asset in canon.sheets["2"].assets:
            if asset.family == "frame":
                asset.void = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_corruption", canon)
    before, choice = command(physical, "sit")
    result = physical.operate(PLAYER, str(uuid4()), before["game_revision"], choice)
    work = result["void_works"][0]
    game.dice = Dice((4, 4))
    worker, gateway = GameWorker(game), Gateway()
    child = keep(game, worker, gateway, None, work, controlled=False, enough=False)
    with ledger.engine.connect() as c:
        assert source(game, c, work)[1]["source_action"] is None
        assert game.action(c, child)["parent_id"] is None
        assert game.lock(c, 900)["state"] == "held"
    assert game.inspect(PLAYER, child)["state"] == "awaiting_choices"
    assert game.dice.calls == 1 and VoidService(ledger).get(PLAYER, work)["stage"] == "enclosed"


def test_removed_optional_keep_cannot_use_manual_mandatory_exception(ledger):
    from test_adjudication_service import forbid

    game, _, _, parent, work = pending(ledger)
    forbid(game, 2, "keep_your_head")
    before, count = state(game).model_dump_json(), game.dice.calls
    with pytest.raises(WorkflowError, match="optional Keep"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                source_work=work,
                parent=parent,
                heat=0,
                context="No source restores the removed optional roll",
                trigger_confirmed=True,
            ),
        )
    assert state(game).model_dump_json() == before and game.dice.calls == count
    assert not any(x["kind"] == "manual_adjudication" for x in game.choices(ADMIN))
