"""A real NPC's own controller supplies Stalker company, never inferred co-presence."""

import asyncio
from uuid import uuid4

import pytest
from test_ankou import buy, current, native, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_world_service import transfer_npc

from girlframe.discord_adapter.m3_ankou import open_ankou
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_ankou import request_source, stalker_view
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_native_stalker_npc_companionship_requires_actual_source_and_owned_fresh_fact(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    world = WorldService(MissionService(ledger))
    target = ActorRef(kind="npc", entity="actual-stalker-obsession")
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=target.entity,
            name="Actual original Obsession",
            jobs=("guard",),
            controller=1,
            detail="Actual independent original person",
            cell=(0, 0),
            revealed=True,
        ),
    )
    transfer_npc(world, ADMIN, OTHER, target.entity)
    actor, companion = current_ref(state(game), 2), current_ref(state(game), 3)
    buy(controls, rules.STALKER)
    before = state(game)
    with pytest.raises(WorkflowError, match="Intense"):
        request_source(
            game,
            PLAYER,
            str(uuid4()),
            before.revision,
            900,
            target,
            "company",
            "No actual qualifying connection yet",
        )
    assert state(game) == before
    buy(controls, rules.OBSESSIVE)
    controls.choose_obsession(
        PLAYER, str(uuid4()), state(game).revision, target, "My actual one-sided Obsession"
    )
    assert rules.effective_intense(state(game), actor, target)
    assert not rules.effective_intense(state(game), target, actor)

    def view():
        with ledger.engine.connect() as c:
            return stalker_view(game, c, state(game), actor, target)

    unknown = view()
    assert unknown["cell"] == (0, 0) and not unknown["company_known"]
    assert unknown["company"] is None

    async def own_answer(task, companions):
        opened = current(OTHER.user_id)
        await opened.response.defer(ephemeral=True)
        await open_ankou(opened, controls, task.id)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["operation"] = ("choose",)
        selected = current(OTHER.user_id)
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(PLAYER.user_id))
        form.values.update(
            companions=companions, account="My actual NPC's original current company"
        )
        submitted = current(OTHER.user_id)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    for selection in (("none",), (companion.token,)):
        native(
            controls,
            "request_source",
            person=(target.token,),
            kind=("company",),
            account="I use my actual qualifying Stalker connection",
        )
        task = [x for x in rules.records(state(game), rules.Task) if x.kind == "company"][-1]
        assert task.actor == target and task.target == actor and task.controller == OTHER.user_id
        snapshot = state(game)
        request_view = controls.view(PLAYER, task.id)
        assert request_view["source"]["options"] == [] and "company_options" not in request_view
        with pytest.raises(WorkflowError):
            controls.choose_task(
                PLAYER,
                str(uuid4()),
                snapshot.revision,
                task.id,
                "none",
                "Cannot author the NPC's own factual answer",
            )
        assert state(game) == snapshot
        asyncio.run(own_answer(task, selection))
        known = view()
        assert known["company_known"] and known["cell"] == unknown["cell"]
        if selection == ("none",):
            assert known["company"] == []  # Explicit factual alone, not unknown.
        else:
            assert [x["ref"] for x in known["company"]] == [companion.model_dump(mode="json")]
    final = state(game)
    source = [x for x in rules.records(final, rules.Company) if x.request == task.id][-1]
    assert source.actor == target and source.companions == (companion,)
    assert source.author == OTHER.user_id and source.positions[target.token]
    with pytest.raises(WorkflowError):
        controls.choose_task(OTHER, str(uuid4()), final.revision, task.id, "none", "No overwrite")
    assert state(game) == final and game.dice.calls == 0
    MovementService(game).move(
        OTHER,
        str(uuid4()),
        final.revision,
        900,
        companion,
        (1, 0),
        account="My actual companion leaves their original company",
    )
    stale = view()
    assert not stale["company_known"] and stale["company"] is None
    assert stale["cell"] == (0, 0)  # Never revive the older superseded 'alone' answer.
    native(
        controls,
        "request_source",
        person=(target.token,),
        kind=("company",),
        account="Request a genuine new answer after circumstances change",
    )
    pending = [x for x in rules.records(state(game), rules.Task) if x.kind == "company"][-1]
    transfer_npc(world, OTHER, ADMIN, target.entity)
    transferred = state(game)
    with pytest.raises(WorkflowError):
        controls.view(OTHER, pending.id)
    for viewer in (OTHER, ADMIN):
        with pytest.raises(WorkflowError):
            controls.choose_task(
                viewer,
                str(uuid4()),
                transferred.revision,
                pending.id,
                "none",
                "An old request cannot transfer another person's authority",
            )
        assert state(game) == transferred
    assert view()["company"] is None and game.dice.calls == 0
