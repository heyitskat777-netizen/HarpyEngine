"""A real completed group source transfers an AM only to an actual actor/partner pair."""

import asyncio
from uuid import uuid4

import pytest
import test_mission_service as mission_fixture
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR, setup_three, third_presence
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_physical_operations import place
from test_red_queen import current, initialize
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_red_queen import open_red_queen
from girlframe.engine import m3_mockingbird as mockingbird
from girlframe.engine import m3_red_queen as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_mockingbird_plays import MockingbirdService
from girlframe.services.m3_red_queen import RedQueenService, transfer_options
from girlframe.services.m3_red_queen_transfer import transfer_source
from girlframe.services.onboarding import WorkflowError


def test_native_court_transfer_after_actual_group_sex_to_nonprimary_original_partner(
    ledger, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        mission_fixture,
        "setup_game",
        lambda store, **kwargs: setup_three(store, girl="MOCKINGBIRD", frame=rules.FRAME),
    )
    _, game = mission_fixture.service(ledger, girl="MOCKINGBIRD", frame=rules.FRAME)
    worker, gateway, court = GameWorker(game), Gateway(), RedQueenService(game)
    original_actor = gateway.actor

    async def actual_actor(identity):
        return FOUR if identity == 4 else await original_actor(identity)

    gateway.actor = actual_actor
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2, mode="outside_frame"), 3, mode="outside_frame")
        game.event(c, 1, str(uuid4()), "synthetic.original_court_body_positions", canon)
    assert 4 in state(game).order and state(game).sheets["4"].character_id

    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.COURT, rules.TRANSFER, rules.CONSULT, *rules.REQUISITIONS, mockingbird.SEX),
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    third_presence(ledger, game)
    initialize(court)
    actor, first, second = (current_ref(state(game), uid) for uid in (2, 3, 4))
    chosen_am = next(x for x in rules.records(state(game), rules.CourtAM) if x.bearer == actor)
    service = MockingbirdService(game)
    trigger = service.propose(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        "mockingbird_sex",
        (first, second),
        "PRIVATE_GROUP Actual voluntary group intimacy with both original partners",
        primary=first,
    )["id"]
    service.attest(OTHER, str(uuid4()), trigger, first, True)
    service.attest(FOUR, str(uuid4()), trigger, second, True)
    game.dice.faces = (4, 4)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="mockingbird_sex",
            source_work=trigger,
            heat=0,
            trigger_confirmed=True,
            context="PRIVATE_GROUP Actual accepted group source",
        ),
    )["action_id"]
    before_pending = state(game)
    with pytest.raises(WorkflowError, match="Complete"):
        court.transfer(
            PLAYER, str(uuid4()), before_pending.revision, chosen_am.id, second, action, "sex"
        )
    assert state(game) == before_pending
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["receipt"] is None:
        game.roll(PLAYER, str(uuid4()), action)
    for viewer in (PLAYER, OTHER, FOUR, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(
        game,
        PLAYER,
        "mockingbird_sex_select",
        options=("starry",),
        fields={"capability": "deception"},
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 6)
    before = state(game)
    with ledger.engine.connect() as c:
        assert any(
            x["id"] == action for x in transfer_options(game, c, before, actor, second, "sex")
        )
        with pytest.raises(WorkflowError, match="Co-partners"):
            transfer_source(game, c, before, first, second, action, "sex")
    with pytest.raises(WorkflowError):
        court.transfer(OTHER, str(uuid4()), before.revision, chosen_am.id, second, action, "sex")
    assert state(game) == before

    async def native_transfer():
        initial = current(2, int(uuid4().int % 1000000000))
        await initial.response.defer(ephemeral=True)
        await open_red_queen(initial, court)
        menu = initial.edit_original_response.call_args.kwargs["view"]
        menu.values["operation"] = ("transfer",)
        opened = current(2, int(uuid4().int % 1000000000))
        await menu.confirm.callback(opened)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            am=(chosen_am.id,),
            target=(second.token,),
            kind=("sex",),
            account="Actual completed group source",
        )
        select = current(2, int(uuid4().int % 1000000000))
        await form.confirm.callback(select)
        sources = select.edit_original_response.call_args.kwargs["view"]
        assert not await sources.interaction_check(current(3))
        sources.values["source"] = (action,)
        submit = current(2, int(uuid4().int % 1000000000))
        await sources.confirm.callback(submit)
        assert sources.completed, submit.edit_original_response.call_args_list

    asyncio.run(native_transfer())
    after = state(game)
    changed = next(x for x in rules.records(after, rules.CourtAM) if x.id == chosen_am.id)
    assert changed.bearer == second
    assert after.sheets == before.sheets and after.mockingbird == before.mockingbird
    assert game.dice.calls == 1
    another = next(x for x in rules.records(after, rules.CourtAM) if x.bearer == actor)
    with pytest.raises(WorkflowError, match="already transferred"):
        court.transfer(PLAYER, str(uuid4()), after.revision, another.id, second, action, "sex")
    assert state(game) == after
    assert "PRIVATE_GROUP" not in str(gateway.messages)
