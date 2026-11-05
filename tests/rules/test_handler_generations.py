"""Actual Handler body endings cannot give old forms or old NPC Bonds new authority."""

import asyncio
from uuid import uuid4

import pytest
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_handler_creation import (
    HandlerMenu,
    open_npc_agreement,
    open_npc_relationship,
)
from girlframe.engine import m3_handler_consequences as endings
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_state import NpcStarting
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_creation import NPC_AGREEMENT
from girlframe.services.onboarding import WorkflowError


def end_original(svc, game, *, create=True):
    if create:
        save(svc, complete(svc, "Insurgent"))
        agree(svc)
        view = svc.view(ADMIN)
        svc.activate(ADMIN, "activate-first", view["revision"], view["game_revision"], True)
    original = state(game)
    actor = current_ref(original, 1)
    source, effect = str(uuid4()), str(uuid4())
    requested, identity = endings.require(
        original,
        actor,
        trigger="asset_damage",
        source_action=None,
        source_event=source,
        opponent=None,
        appointment=svc.view(ADMIN)["appointment"],
    )
    with svc.store.transaction() as c:
        game.event(
            c, 1, "actual-handler-damage", "synthetic.handler_damage", requested, event_id=source
        )
        ended = endings.apply(requested, identity, "death", "Original Handler dies", effect)
        game.event(c, 1, "actual-handler-death", "synthetic.handler_death", ended, event_id=effect)
    return actor


def save_fresh(svc, draft, key="fresh-handler-save"):
    view = svc.view(ADMIN)
    return svc.save(
        ADMIN, key, view["revision"], view["appointment"], draft, generation=view["generation"]
    )


def accept_all(svc):
    offered = svc.propose(
        ADMIN, str(uuid4()), svc.view(ADMIN)["revision"], generation=svc.view(ADMIN)["generation"]
    )
    for identity in offered["ids"]:
        offer = svc.get_agreement(ADMIN, identity)
        proposal = offer["proposal"]
        uid = (
            proposal["relationship"]["controller"]
            if "relationship" in proposal
            else int(proposal["bond"]["pilot"]["entity"])
        )
        viewer = {1: ADMIN, 2: PLAYER, 3: OTHER}[uid]
        svc.answer(viewer, str(uuid4()), identity, offer["revision"], True)
    return offered


def test_actual_death_starts_new_generation_and_rejects_old_native_form(ledger):
    svc, game = ready(ledger)
    old_view = svc.view(ADMIN)
    old = end_original(svc, game, create=False)
    view = svc.view(ADMIN)
    assert view["generation"] != "initial" and view["revision"] == 0
    assert state(game).handler == 1 and state(game).handler_persona is None
    with pytest.raises(WorkflowError, match="STALE_HANDLER_GENERATION"):
        svc.save(
            ADMIN,
            "old-unsaved-native-form",
            0,
            old_view["appointment"],
            complete(svc),
            generation=old_view["generation"],
        )
    with pytest.raises(WorkflowError, match="STALE_HANDLER_GENERATION"):
        svc.save(ADMIN, "old-unbound-form", 0, old_view["appointment"], complete(svc))
    save_fresh(svc, complete(svc, "Trainer"))
    accept_all(svc)
    view = svc.view(ADMIN)
    svc.activate(ADMIN, "new-trainer-body", view["revision"], view["game_revision"], True)
    assert current_ref(state(game), 1) != old
    assert len(state(game).handler_archives) == 1


def test_post_death_insurgent_needs_real_new_npc_relationship_and_explicit_same_human_consent(
    ledger,
):
    svc, game = ready(ledger)
    old = end_original(svc, game)
    archived_depth = depth(state(game), old, ActorRef(kind="npc", entity="actual-npc"))
    assert archived_depth == 1
    draft = complete(svc, "Insurgent")
    save_fresh(svc, draft)
    assert "NPC relationship history" in str(svc.view(ADMIN)["missing"])
    with pytest.raises(WorkflowError, match="Personal NPC relationship"):
        svc.propose(
            ADMIN,
            "no-old-npc-inheritance",
            svc.view(ADMIN)["revision"],
            generation=svc.view(ADMIN)["generation"],
        )
    draft = draft.model_copy(
        update={
            "npc_starting": (
                NpcStarting(
                    npc=ActorRef(kind="npc", entity="actual-npc"),
                    controller=1,
                    history="NEW_PERSONA_HISTORY",
                ),
            )
        }
    )
    save_fresh(svc, draft, "new-npc-package")
    proposed = svc.propose(
        ADMIN,
        "propose-new-persona",
        svc.view(ADMIN)["revision"],
        generation=svc.view(ADMIN)["generation"],
    )
    task = next(x for x in svc.tasks(ADMIN) if x["kind"] == NPC_AGREEMENT)
    assert task["actionable"]
    inbox = next(x for x in InboxService(ledger).items(ADMIN) if x.identity == task["id"])
    assert inbox.task == NPC_AGREEMENT and inbox.incoming
    for identity in proposed["ids"]:
        offer = svc.get_agreement(ADMIN, identity)
        if "bond" in offer["proposal"]:
            uid = int(offer["proposal"]["bond"]["pilot"]["entity"])
            svc.answer(
                PLAYER if uid == 2 else OTHER, str(uuid4()), identity, offer["revision"], True
            )
    view = svc.view(ADMIN)
    with pytest.raises(WorkflowError, match="NPC controller"):
        svc.activate(
            ADMIN, "same-human-not-auto-consent", view["revision"], view["game_revision"], True
        )
    response = svc.get_agreement(ADMIN, task["id"])
    svc.answer(ADMIN, "actual-npc-controller-accepts", task["id"], response["revision"], True)
    view = svc.view(ADMIN)
    svc.activate(ADMIN, "new-insurgent-activation", view["revision"], view["game_revision"], True)
    actual = state(game)
    fresh = current_ref(actual, 1)
    assert fresh != old and depth(actual, fresh, ActorRef(kind="npc", entity="actual-npc")) == 1
    assert depth(actual, old, ActorRef(kind="npc", entity="actual-npc")) == archived_depth
    assert len(actual.world.npcs) == 1 and actual.handler_heat == 0 and actual.handler_tags == []


def test_native_new_npc_history_and_owned_response_survive_restart_and_private_long_review(ledger):
    svc, game = ready(ledger)
    end_original(svc, game, create=False)
    save_fresh(svc, complete(svc, "Insurgent"))

    async def run():
        owner = current(1, 77101)
        await owner.response.defer(ephemeral=True)
        await open_npc_relationship(owner, svc)
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(npc=("actual-npc",), history="*" * 1190)
        await form.confirm.callback(current(1, 77102))
        assert form.completed
        svc.propose(
            ADMIN,
            "native-new-npc-proposal",
            svc.view(ADMIN)["revision"],
            generation=svc.view(ADMIN)["generation"],
        )
        identity = next(x["id"] for x in svc.tasks(ADMIN) if x["kind"] == NPC_AGREEMENT)
        await open_npc_agreement(owner, svc, identity)
        pages = owner.edit_original_response.call_args.kwargs["view"]
        assert not await pages.interaction_check(current(2))
        assert pages.respond.disabled
        while not pages.next.disabled:
            await pages.next.callback(owner)
        responding = current(1, 77103)
        await pages.respond.callback(responding)
        answer = responding.edit_original_response.call_args.kwargs["view"]
        answer.values["decision"] = ("accept",)
        await answer.confirm.callback(current(1, 77104))
        assert answer.completed
        assert svc.get_agreement(ADMIN, identity)["decision"] == "accepted"

    asyncio.run(run())
    assert state(game).handler_persona is None


def test_only_actual_npc_controller_can_agree_and_changed_controller_invalidates_source(ledger):
    svc, game = ready(ledger)
    end_original(svc, game, create=False)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"controller": 2, "revealed": True})
                    for x in canon.world.npcs
                )
            }
        )
        game.event(c, 1, "actual-npc-controller", "synthetic.world", canon)
    draft = complete(svc, "Insurgent").model_copy(
        update={
            "npc_starting": (
                NpcStarting(
                    npc=ActorRef(kind="npc", entity="actual-npc"),
                    controller=2,
                    history="Actual source NPC history",
                ),
            )
        }
    )
    save_fresh(svc, draft)
    proposals = svc.propose(
        ADMIN,
        "foreign-controller-proposals",
        svc.view(ADMIN)["revision"],
        generation=svc.view(ADMIN)["generation"],
    )
    identity = next(x["id"] for x in svc.tasks(PLAYER) if x["kind"] == NPC_AGREEMENT)
    request = svc.get_agreement(PLAYER, identity)
    assert "PRIVATE_" not in str(request)
    with pytest.raises(WorkflowError, match="original relationship participant"):
        svc.answer(ADMIN, "not-actual-npc-controller", identity, request["revision"], True)
    svc.answer(PLAYER, "actual-npc-controller-consent", identity, request["revision"], True)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={"npcs": tuple(x.model_copy(update={"controller": 3}) for x in canon.world.npcs)}
        )
        game.event(c, 1, "actual-controller-change", "synthetic.world", canon)
    assert svc.get_agreement(PLAYER, identity)["stale"]
    before = state(game).model_dump_json()
    view = svc.view(ADMIN)
    with pytest.raises(WorkflowError, match="participating controller"):
        svc.activate(
            ADMIN, "stale-npc-controller-activate", view["revision"], view["game_revision"], True
        )
    assert state(game).model_dump_json() == before and len(proposals["ids"]) == 3


def test_cached_old_menu_cannot_propose_new_generation_with_same_revision(ledger):
    svc, game = ready(ledger)
    save(svc, complete(svc, "Trainer"))
    old_view = svc.view(ADMIN)
    assert old_view["revision"] == 1
    end_original(svc, game, create=False)
    save_fresh(svc, complete(svc, "Trainer"))
    new_view = svc.view(ADMIN)
    assert new_view["revision"] == old_view["revision"] == 1
    assert new_view["persona_id"] != old_view["persona_id"]
    assert new_view["generation"] != old_view["generation"]
    before = state(game).model_dump_json()

    async def run():
        stale = HandlerMenu(svc, ADMIN.user_id, old_view)
        caller = current(1, 77201)
        await stale.propose.callback(caller)
        content = caller.edit_original_response.call_args.kwargs["content"]
        assert "STALE_HANDLER_GENERATION" in content
        assert not any(x["kind"] == "handler_creation_agreement" for x in svc.tasks(PLAYER))
        fresh = HandlerMenu(svc, ADMIN.user_id, svc.view(ADMIN))
        await fresh.propose.callback(current(1, 77202))
        assert any(x["kind"] == "handler_creation_agreement" for x in svc.tasks(PLAYER))

    asyncio.run(run())
    assert state(game).model_dump_json() == before
    assert svc.view(ADMIN)["draft"] == new_view["draft"]
