"""Recursive Budget source → private real losses → genuine mandatory endpoints."""

import asyncio
from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_physical_operations import place
from test_strain import facts
from test_strain_service import ready
from test_void_service import respond
from test_world import gorgon, initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_budget_removal import open_removal
from girlframe.engine import m3_budget_removal as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_world_state import Asset, CorePlan
from girlframe.services.inbox import InboxService
from girlframe.services.m3_budget_removal import RemovalService, history, prove_loss_source
from girlframe.services.m3_void import VoidService
from girlframe.services.onboarding import WorkflowError


def source(store, *, void=False):
    strain, game = ready(store, frame="THE ENFORCER", face=6)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays", "world"}}
            )
        }
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2, mode="outside_frame"), 3)
        for uid in ("2", "3"):
            sheet = canon.sheets[uid]
            sheet.identities[0].marked = True
            frames = [x for x in sheet.assets if x.family == "frame"]
            girls = [x for x in sheet.assets if x.family == "girl"]
            for asset in frames[1:]:
                asset.damaged = True
                asset.void = void and uid == "2"
            if uid == "2":
                for asset in girls[1:]:
                    asset.damaged = not void
        game.event(c, 1, "actual-maintenance-start", "synthetic.state", canon)
    strain.configure(
        ADMIN, "scenario", state(game).revision, "disaster_management", frozenset({"budget"})
    )
    period = strain.periods.begin(ADMIN, "begin")["id"]
    with_void = sum(any(x.void for x in sheet.assets) for sheet in state(game).sheets.values())
    strain.prepare(
        ADMIN,
        "prepare",
        period,
        1,
        state(game).revision,
        facts(
            at_least_half_have_void=2 * with_void >= len(state(game).order),
            no_girl_void=with_void == 0,
            frame_full_or_all_frames_some_repairs=True,
        ),
    )
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "budget" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)
    strain.choose(
        ADMIN,
        "actual-budget-removal-source",
        request.id,
        1,
        state(game).revision,
        4,
        endgame=True,
    )
    return RemovalService(store), game, strain, request.id + ":effect", period


def pair(canon, uid):
    sheet = canon.sheets[str(uid)]
    return tuple(
        next(x for x in sheet.assets if x.family == family) for family in ("girl", "frame")
    )


def native_loss(service, game, work, uid, *, battle, opponent=None):
    selected = pair(state(game), uid)
    actor = current_ref(state(game), uid)
    before = state(game)

    async def run():
        review = current(1, 12000 + uid)
        await review.response.defer(ephemeral=True)
        await open_removal(review, service, work, actor=actor)
        form = review.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and state(game) == before
        form.values.update(
            battle=("yes" if battle else "no",),
            opponent=(opponent.token if opponent else "none",),
            account="Actual known placement, battle and opponent facts",
            confirm=("yes",),
        )
        await form.confirm.callback(current(1, 12100 + uid))
        assert form.completed
        expected = state(game).revision
        owner = current(uid, 12200 + uid)
        await owner.response.defer(ephemeral=True)
        await open_removal(owner, service, work)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(1, 12300 + uid))
        form.values.update(
            girl=(selected[0].id,),
            frame=(selected[1].id,),
            account="PRIVATE_REMOVED_PAIR_" + str(uid),
            confirm=("yes",),
        )
        await form.confirm.callback(current(uid, 12400 + uid))
        assert form.completed
        # A duplicate delivery reuses the command, without another deletion.
        saved = state(game)
        await form.confirm.callback(current(uid, 12400 + uid))
        assert state(game) == saved
        service.remove(
            PLAYER if uid == 2 else OTHER,
            str(12400 + uid),
            work,
            expected,
            selected[0].id,
            selected[1].id,
            "PRIVATE_REMOVED_PAIR_" + str(uid),
        )
        assert state(game) == saved

    asyncio.run(run())
    return next(
        x for x in rules.losses(state(game)) if x.work == work and x.actor == actor
    ), selected


def private_record(service, game, work, loss, selected, *, completed=False):
    viewer = PLAYER if loss.actor.entity == "2" else OTHER
    owned = service.view(viewer, work)
    assert owned["record"]["girl_asset"] == selected[0].model_dump(mode="json")
    assert owned["record"]["frame_asset"] == selected[1].model_dump(mode="json")
    assert owned["record"]["account"] == "PRIVATE_REMOVED_PAIR_" + loss.actor.entity
    handler = service.view(ADMIN, work, loss.actor)
    assert "record" not in handler and not handler["assets"]
    with pytest.raises(WorkflowError):
        service.view(OTHER if viewer == PLAYER else PLAYER, work, loss.actor)
    own_task = next(x for x in service.tasks(viewer) if x["id"] == work)
    if completed:
        assert not own_task["pending"]

    async def reopen():
        owner = current(int(loss.actor.entity), 12500 + int(loss.actor.entity))
        await owner.response.defer(ephemeral=True)
        await open_removal(owner, service, work)
        content = str(owner.edit_original_response.call_args.kwargs)
        assert selected[0].name in content and selected[1].name in content
        assert "PRIVATE_REMOVED_PAIR_" + loss.actor.entity in content

    asyncio.run(reopen())
    with service.store.engine.connect() as c:
        original = history(game, c, loss.event)
        assert prove_loss_source(game, c, original, loss.event, loss.id, loss.actor)[
            "piloting"
        ] == (loss.actor.entity == "3")
        forged = original.model_copy(deep=True)
        forged.sheets[loss.actor.entity].heat += 1
        with pytest.raises(WorkflowError):
            prove_loss_source(game, c, forged, loss.event, loss.id, loss.actor)


def test_real_two_owner_native_removal_helpless_defeat_endpoint_and_private_saved_records(ledger):
    service, game, strain, work, _ = source(ledger)
    before = state(game)
    assert strain.dice.calls == 4 and game.dice.calls == 0
    assert (
        next(x for x in InboxService(ledger).items(ADMIN) if x.identity == work).task
        == "m3_budget_removal"
    )
    with pytest.raises(WorkflowError, match="Every original Girl"):
        service.finish(ADMIN, "no-false-source-completion", work, before.revision)
    foe = current_ref(before, 3)
    first, first_pair = native_loss(service, game, work, 2, battle=True, opponent=foe)
    assert first.last_girl and not first.children
    assert is_helpless(state(game), first.actor, foe)
    assert not is_helpless(state(game), first.actor, current_ref(state(game), 1))
    assert not state(game).sheets["2"].frame_scrapped
    private_record(service, game, work, first, first_pair, completed=True)
    second, second_pair = native_loss(service, game, work, 3, battle=True, opponent=first.actor)
    assert len(second.children) == 1
    child = service.view(OTHER, work)["children"][0]
    assert child["kind"] == "defeat" and child["state"] == "pending"
    with pytest.raises(WorkflowError, match="mandatory"):
        service.finish(ADMIN, "child-must-really-finish", work, state(game).revision)
    undamaged = sum(x.family == "girl" and not x.damaged for x in state(game).sheets["3"].assets)
    game.dice = Dice((3, 5 - undamaged))
    action = game.begin(
        OTHER,
        "actual-source-defeat",
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="defeat",
            heat=0,
            source_work=child["id"],
            context="The actual battle loss of my final usable Frame Asset",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(OTHER, action)["receipt"]
    assert receipt["pre_total"] == 8
    assert receipt["modifier_source"] == "Undamaged Girl Assets" and game.dice.calls == 1
    answer(
        game,
        OTHER,
        "defeat_select",
        options=("escape_cockpit_choose_location",),
        text="I escape my actual disabled Frame at its battlefield location",
    )
    assert game.inspect(OTHER, action)["state"] == "complete"
    assert service.view(OTHER, work)["children"][0]["state"] == "resolved"
    with pytest.raises(WorkflowError, match="restore its chat"):
        service.finish(ADMIN, "actual-chat-lock-preserved", work, state(game).revision)
    tick(worker, gateway, 3)
    for uid in ("2", "3"):
        assert state(game).sheets[uid].identities == before.sheets[uid].identities
        removed = {x.id for x in (first_pair if uid == "2" else second_pair)}
        assert state(game).sheets[uid].assets == [
            x for x in before.sheets[uid].assets if x.id not in removed
        ]
        assert state(game).sheets[uid].permissions == before.sheets[uid].permissions
    assert (
        service.finish(ADMIN, "actual-budget-source-complete", work, state(game).revision)["state"]
        == "resolved"
    )
    private_record(service, game, work, second, second_pair, completed=True)
    assert len(rules.losses(state(game))) == 2
    saved = state(game).model_dump_json()
    assert game.rebuild() > 0 and state(game).model_dump_json() == saved
    assert (
        RemovalService(ledger).view(PLAYER, work)["record"]["account"] == "PRIVATE_REMOVED_PAIR_2"
    )


def test_real_full_void_removal_abandoned_frame_endpoint_and_nonbattle_no_false_defeat(ledger):
    service, game, _, work, _ = source(ledger, void=True)
    first, first_pair = native_loss(service, game, work, 2, battle=False)
    assert not first.last_girl and len(first.children) == 1
    child = service.view(PLAYER, work)["children"][0]
    assert child["kind"] == "void_threshold"
    second, second_pair = native_loss(service, game, work, 3, battle=False)
    assert not second.children and not state(game).sheets["3"].frame_scrapped
    assert not is_helpless(state(game), first.actor, second.actor)
    with pytest.raises(WorkflowError, match="mandatory"):
        service.finish(ADMIN, "no-silent-void-work", work, state(game).revision)
    void = VoidService(ledger)
    assert void.get(PLAYER, child["id"])["stage"] == "abandoned"
    assets = tuple(
        Asset(
            id=x.id,
            name=x.name,
            description=x.description,
            family="gorgon",
            damaged=x.damaged,
            void=x.void,
        )
        for x in state(game).sheets["2"].assets
        if x.family == "frame"
    )
    actual_gorgon = gorgon(
        identity="real-abandoned-budget-frame",
        assets=assets,
        core_plan=CorePlan(assets=(assets[0].id,), weakness="Its genuine exposed core"),
    )
    respond(
        void,
        child["id"],
        "abandoned",
        dict(
            gorgon=actual_gorgon.model_dump(mode="json"),
            account="Actual original outside Girl and Frame conversion",
        ),
        viewer=ADMIN,
    )
    assert state(game).sheets["2"].frame_scrapped
    assert {x.id for x in state(game).world.gorgons[-1].assets} == {x.id for x in assets}
    assert service.view(PLAYER, work)["children"][0]["state"] == "resolved"
    assert (
        service.finish(ADMIN, "actual-void-endpoint-source-complete", work, state(game).revision)[
            "state"
        ]
        == "resolved"
    )
    private_record(service, game, work, first, first_pair, completed=True)
    private_record(service, game, work, second, second_pair, completed=True)
    assert len(rules.losses(state(game))) == 2 and game.dice.calls == 0
