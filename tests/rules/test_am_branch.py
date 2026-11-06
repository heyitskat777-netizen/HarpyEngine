"""Printed branch NPC actually acts, then becomes the owner's real new Girl."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
import test_creation_review
import test_m2_game
from test_am_scrutinized import rolled as scrutiny_rolled
from test_enforcement_initiative import cast_target
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current
from test_physical_operations import place

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_am_body import open_prepare
from girlframe.discord_adapter.m3_am_branch import open_branch
from girlframe.discord_adapter.m3_am_code import open_choice
from girlframe.engine import m3_am as am
from girlframe.engine import m3_am_body as bodies
from girlframe.engine import m3_am_branch as rules
from girlframe.engine import m3_am_code as code
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_am_body import BodyService
from girlframe.services.m3_am_branch import BranchService, prove
from girlframe.services.m3_am_code import CodeService
from girlframe.services.m3_npc_guard import GuardService
from girlframe.services.onboarding import WorkflowError

CANARY = "PRIVATE_ORIGINAL_OOC_NOT_A_BRANCH_MEMORY"


def test_actual_branch_npc_counter_then_owned_takeover_and_current_girl_play(
    ledger, tmp_path, monkeypatch
):
    selected = test_m2_game.selected
    actual_seed = test_creation_review.seed

    def seed_alpha(store, viewer=PLAYER):
        if viewer == OTHER:
            from girlframe.engine.drafts import DraftInput

            store.join(viewer, "join-3")
            store.save_draft(
                viewer,
                "draft-3",
                0,
                DraftInput(
                    callsign="Actual Alpha", girl_playbook="ALPHA", frame_playbook="JANUS-B"
                ),
            )
        else:
            actual_seed(store, viewer)

    monkeypatch.setattr(test_creation_review, "seed", seed_alpha)
    monkeypatch.setattr(test_m2_game, "selected", lambda *_: selected("ALPHA", "JANUS-B"))
    game, _, operator, discovery, _, _, worker, gateway = scrutiny_rolled(
        ledger, tmp_path, monkeypatch, (1, 1)
    )
    original = current_ref(state(game), 2)
    limited = am.identities(state(game), original)[0]
    answer(
        game,
        ADMIN,
        "am_limiter",
        options=(limited.id,),
        fields={"freedom": "refuse"},
        text="The actual original discoverer installs the printed Limiter",
    )
    tick(worker, gateway, 5)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(am.RULE, code.RULE, "girl.alpha.brutalize", "npc.npc.guard"),
    )
    service = CodeService(game)
    maintenance = service.propose(
        PLAYER,
        str(uuid4()),
        discovery,
        state(game).revision,
        "Actual same original operator prepares real circuits branching",
    )["id"]
    root = service.confirm(
        ADMIN,
        str(uuid4()),
        maintenance,
        state(game).revision,
        "Actual same-location physical circuit access",
    )["action_id"]
    tick(worker, gateway, 3)
    game.dice.faces = (4, 5)
    canon = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        canon.sheets["2"].revision,
        PlayInput(
            play=code.PLAY,
            parent=root,
            source_work=maintenance,
            target_actor=operator,
            heat=0,
            trigger_confirmed=True,
            context="The actual original NPC performs circuit maintenance",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    # Real selected memory erasure happens before birth in the same two-option Play.
    answer(game, ADMIN, "am_code_options", options=("identities", "branch"))
    answer(
        game,
        ADMIN,
        "am_code_edit",
        options=("edit",),
        fields={"memory_scope": "selected", "memories": "Old fictional door code"},
        text="Actual operator erases only this fictional memory",
    )
    with ledger.transaction() as c:
        actual = place(state(game), 3, mode="outside_frame")
        actual.facts.append(dict(kind="synthetic_private_memory", body=CANARY))
        game.event(c, 1, str(uuid4()), "synthetic.actual_branch_scene_and_private_record", actual)
    before = state(game)
    old_sheet = before.sheets["2"].model_copy(deep=True)
    old_pose = next(x for x in before.placements if x.actor == original)
    calls = game.dice.calls

    async def actual_birth():
        own = current(1, 972001)
        await own.response.defer(ephemeral=True)
        await open_prepare(own, BodyService(game), maintenance)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            vessel="actual-branch-processor-body",
            label="Independent AM branch",
            source="Actual supplied local puppet with independently sufficient processor",
            processing=("yes",),
            unoccupied=("yes",),
            medical=("fit",),
            mind_assets=(),
            assets=(
                "Branch arm | Actually installed actuator | intact | clear\n"
                "Branch skin | Supplied covering | intact | clear"
            ),
        )
        confirm = current(1, 972002)
        await form.confirm.callback(confirm)
        assert form.completed, str(confirm.edit_original_response.call_args)
        row = next(x for x in game.choices(ADMIN) if x["kind"] == "am_code_branch")
        own = current(1, 972003)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, row["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        preparation = bodies.preparations(state(game))[0]
        form.values.update(
            body=(preparation.id,), account="Actual independent NPC branch in prepared processor"
        )
        confirm = current(1, 972004)
        await form.confirm.callback(confirm)
        assert form.completed, str(confirm.edit_original_response.call_args)
        response = ChoiceAnswer(
            options=(preparation.id,), text="Actual independent NPC branch in prepared processor"
        )
        assert game.respond(ADMIN, "972004", row["id"], row["revision"], response)

    asyncio.run(actual_birth())
    tick(worker, gateway, 5)
    born = state(game)
    (value,) = rules.branches(born)
    assert code.session(born, maintenance).branch == value.id
    assert born.sheets["2"] == old_sheet and game.dice.calls == calls
    assert (
        game.inspect(PLAYER, root)["state"] == game.inspect(PLAYER, action)["state"] == "complete"
    )
    assert not rules.is_branch(born, original) and value.npc != original
    assert resolve(born, value.npc, ()).controller == 1
    assert not am.human_target(born, value.npc)
    assert not am.free(born, value.npc, "refuse")
    from girlframe.engine.m3_am_memory import can_recall

    assert not can_recall(
        born, value.npc, "Old fictional door code", learned_revision=before.revision - 2
    )
    assert CANARY not in value.model_dump_json()
    assert born.actor_bonds == before.actor_bonds and born.bonds == before.bonds
    branch = BranchService(game)
    with pytest.raises(WorkflowError):
        branch.view(OTHER, value.id)
    with ledger.engine.connect() as c:
        assert prove(game, c, born, value.id) == value
        forged = born.model_copy(deep=True)
        forged.facts = [x for x in forged.facts if x.get("id") not in value.limiter_ids]
        with pytest.raises(WorkflowError, match="inherited original Limiter"):
            prove(game, c, forged, value.id)
        forged = born.model_copy(deep=True)
        bodies.put(
            forged, "am_branch", value.id, value.model_copy(update=dict(vessel="fake-hardware"))
        )
        with pytest.raises(WorkflowError, match="birth snapshot"):
            prove(game, c, forged, value.id)
    cast_target(game, value.npc)
    guard = GuardService(game)
    guard.assess(
        ADMIN,
        str(uuid4()),
        900,
        value.npc,
        current_ref(state(game), 3),
        state(game).revision,
        True,
        "Actual independent branch Guard has no weapon",
    )
    game.dice.faces = (1, 1)
    npc_action = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="brutalize",
            target_actor=value.npc,
            heat=0,
            trigger_confirmed=True,
            context="Actual Alpha confronts independent branch Guard",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, ADMIN, "alpha_low", options=("counter_broken",))
    counter = next(x for x in game.choices(ADMIN) if x["kind"] == "alpha_counter_play")
    with pytest.raises(WorkflowError):
        guard.counter(PLAYER, npc_action, counter["id"])
    counter_data = guard.counter(ADMIN, npc_action, counter["id"])
    guard.perform_counter(
        ADMIN,
        str(uuid4()),
        npc_action,
        counter["id"],
        counter_data["revision"],
        "interpose",
        "Actual independent branch blocks the Alpha's path",
    )
    answer(game, OTHER, "alpha_npc_mercy", options=("spare",))
    assert game.inspect(OTHER, npc_action)["state"] == "complete"
    tick(worker, gateway, 5)

    async def activate():
        handler = current(1, 972005)
        await handler.response.defer(ephemeral=True)
        await open_branch(handler, branch, value.id)
        form = handler.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            position=("0",),
            account="Same available colocated original Enforcer assigned to this branch",
        )
        confirm = current(1, 972006)
        await form.confirm.callback(confirm)
        assert form.completed, str(confirm.edit_original_response.call_args)
        owner = current(2, 972007)
        await owner.response.defer(ephemeral=True)
        await open_branch(owner, branch, value.id)
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(takeover=("yes",))
        confirm = current(2, 972008)
        await form.confirm.callback(confirm)
        assert form.completed, str(confirm.edit_original_response.call_args)

    asyncio.run(activate())
    active = state(game)
    completed = rules.get(active, value.id)
    new_actor = current_ref(active, 2)
    assert new_actor == completed.resulting_actor and new_actor != original
    archive = next(x for x in active.career_archives if x.id == completed.archive)
    assert archive.actor == original and archive.ending == "am_branch_terminated"
    assert not any(x.id == value.npc.entity for x in active.world.npcs)
    assert active.sheets["2"].identities == list(value.identities)
    assert active.sheets["2"].heat == active.sheets["2"].permissions == 0
    assert am.limiters(active, new_actor) and not am.free(active, new_actor, "refuse")
    assert not can_recall(
        active, new_actor, "Old fictional door code", learned_revision=before.revision - 2
    )
    assert [x for x in active.sheets["2"].assets if x.family == "frame"] == [
        x for x in old_sheet.assets if x.family == "frame"
    ]
    assert next(x for x in bodies.bodies(active) if x.vessel == old_pose.vessel_id).occupant is None
    assert rules.current_body(active, new_actor).vessel == value.vessel
    with pytest.raises(ValueError):
        resolve(active, original, ())
    with pytest.raises(ValueError):
        resolve(active, value.npc, ())
    with ledger.engine.connect() as c:
        assert prove(game, c, active, value.id) == completed
        assert resolve(active, new_actor, profiles(c, ledger.campaign_id)).controller == 2
        profile = (
            c.execute(sa.select(t.characters).where(t.characters.c.user_id == "2")).mappings().one()
        )
        assert json.loads(profile["public_json"])["callsign"] == active.sheets["2"].callsign
    assert branch.takeover(PLAYER, "972008", value.id, active.revision - 1)
    with pytest.raises(WorkflowError):
        branch.takeover(PLAYER, str(uuid4()), value.id, active.revision)
    from girlframe.services.m3_actors import ActorService

    async def reopen_saved_branch():
        from girlframe.discord_adapter.inbox import InboxView
        from girlframe.services.inbox import InboxService

        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(PLAYER) if x.task == "m3_am_branch" and x.identity == value.id
        )
        assert not item.incoming
        owner = current(2, 972009)
        owner.channel_id = 902
        await owner.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(owner, item)
        assert "original mind remains terminated" in str(owner.edit_original_response.call_args)
        assert CANARY not in str(owner.edit_original_response.call_args)

    asyncio.run(reopen_saved_branch())
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    casts = CastService(ActorService(MissionService(ledger)))
    cast = casts.view(ADMIN, 900)
    casts.change(
        ADMIN, str(uuid4()), 900, cast["game_revision"], cast["cast_revision"], "withdraw", operator
    )
    from girlframe.engine.m3_alpha import conditions

    assert conditions(state(game), current_ref(state(game), 3), new_actor)
    game.dice.faces = (4, 5)
    keep = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        active.sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            trigger_confirmed=True,
            context="This actual new branch Girl keeps her head",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("sexy", "tough"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual new Girl completes her response")
    assert game.inspect(PLAYER, keep)["state"] == "complete"
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    final = state(game)
    assert CANARY in str(final.facts)
    with ledger.engine.connect() as c:
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    assert game.rebuild() > 0 and state(game) == final
