"""Actual NPC privacy belongs to their controller; Stalker gives one source-owned Tag."""

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
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_ankou import prove_tag
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_native_stalker_npc_owned_privacy_context_and_exact_spy_tag(ledger, tmp_path, monkeypatch):
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
    target = ActorRef(kind="npc", entity="actual-observed-npc")
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=target.entity,
            name="Original observed person",
            jobs=("guard",),
            controller=1,
            detail="Actual separately controlled person",
            cell=(0, 0),
            revealed=True,
        ),
    )
    transfer_npc(world, ADMIN, OTHER, target.entity)
    actor = current_ref(state(game), PLAYER.user_id)
    buy(controls, rules.STALKER)
    assert not rules.effective_intense(state(game), actor, target)

    async def record(viewer, identity, operation, **answers):
        opened = current(viewer.user_id)
        await opened.response.defer(ephemeral=True)
        await open_ankou(opened, controls, identity)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["operation"] = (operation,)
        selected = current(viewer.user_id)
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(1))
        form.values.update(answers)
        submitted = current(viewer.user_id)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    for privacy in ("no", "yes"):
        native(
            controls,
            "request_source",
            person=(target.token,),
            kind=("spy_context",),
            account="I actually observe this co-present person",
        )
        task = [x for x in rules.records(state(game), rules.Task) if x.kind == "spy_context"][-1]
        assert task.actor == target and task.target == actor and task.controller == OTHER.user_id
        before = state(game)
        with pytest.raises(WorkflowError):
            controls.choose_task(
                PLAYER,
                str(uuid4()),
                before.revision,
                task.id,
                "yes",
                "I cannot invent their private expectation",
            )
        assert state(game) == before
        asyncio.run(
            record(
                OTHER,
                task.id,
                "choose",
                choice=(privacy,),
                account="My actual NPC expects privacy"
                if privacy == "yes"
                else "My actual NPC does not expect privacy",
            )
        )
        encounters = [
            x for x in rules.records(state(game), rules.Encounter) if x.request == task.id
        ]
        if privacy == "no":
            assert not encounters
            assert not actor_tags(state(game), target)
        else:
            assert len(encounters) == 1
            encounter = encounters[0]
    assert encounter.actor == actor and encounter.target == target
    assert encounter.author == OTHER.user_id and encounter.thinks_private
    before_tag = state(game)
    with pytest.raises(WorkflowError):
        controls.give_source_tag(
            OTHER,
            str(uuid4()),
            before_tag.revision,
            encounter.id,
            "spy",
            "Not the actual Stalker giver",
        )
    assert state(game) == before_tag
    asyncio.run(
        record(
            PLAYER,
            encounter.id,
            "tag",
            label="PRIVATE_ACTUAL_SPY_TAG",
            account="My actual source-owned spying consequence",
        )
    )
    final = state(game)
    use = next(x for x in rules.records(final, rules.TagUse) if x.source == encounter.id)
    tag = next(x for x in actor_tags(final, target) if x.id == use.tag)
    assert tag.label == "PRIVATE_ACTUAL_SPY_TAG" and use.actor == actor and use.target == target
    with ledger.engine.connect() as c:
        assert prove_tag(game, c, final, target, tag.id) == use
    with pytest.raises(WorkflowError):
        controls.give_source_tag(
            PLAYER, str(uuid4()), final.revision, encounter.id, "spy", "Duplicate"
        )
    assert state(game) == final and game.dice.calls == 0
