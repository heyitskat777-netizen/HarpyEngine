"""Only first same-body naming adopts exact open Handler casts; replacement never does."""

from uuid import uuid4

import pytest
from test_handler_creation import agree, complete, ready, save
from test_handler_generations import accept_all, end_original, save_fresh
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def casting(svc):
    store = svc.store
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": store.policy.m3_approval.model_copy(
                update={
                    "subsystems": store.policy.m3_approval.subsystems | {"world", "plays"},
                }
            ),
        }
    )
    return CastService(ActorService(MissionService(store)))


def join(casts, ref):
    view = casts.view(ADMIN, 900)
    return casts.change(
        ADMIN, str(uuid4()), 900, view["game_revision"], view["cast_revision"], "join", ref
    )


def test_first_naming_adopts_only_exact_open_role_and_actual_tag_bond_bonus_with_stale_cast_guard(
    ledger,
):
    from test_m2_game import Gateway

    svc, game = ready(ledger)
    casts = casting(svc)
    old = ActorRef(kind="handler", entity="1")
    join(casts, old)
    game.close_scene(ADMIN, "actual-old-scene-close", 900)
    closed = state(game).scene_casts[0]
    assert not closed.open
    game.bind_scene(ADMIN, "actual-new-scene-bind", 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    join(casts, old)
    join(casts, ActorRef(kind="npc", entity="actual-npc"))
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].tags.append(
            TagState(
                id="actual-first-handler-tag",
                label="Observed actual Tag",
                giver=3,
                observers=(1, 2, 3),
            )
        )
        game.event(c, 1, "actual-observed-tag", "synthetic.actual_tag", canon)
    original = state(game)
    previous = next(x for x in original.scene_casts if x.open)
    unrelated = tuple(x for x in previous.roles if x.actor != old)
    old_view = casts.view(ADMIN, 900)
    save(svc, complete(svc, "Mistress"))
    agree(svc)
    view = svc.view(ADMIN)
    svc.activate(
        ADMIN, "actual-first-persona-and-cast", view["revision"], view["game_revision"], True
    )
    after = state(game)
    actual = current_ref(after, 1)
    adopted = next(x for x in after.scene_casts if x.open)
    role = next(x for x in adopted.roles if x.actor.kind == "handler")
    assert role.actor == actual and role.controller == 1
    assert role.source_event == after.handler_persona.source_event
    assert adopted.revision == previous.revision + 1
    assert tuple(x for x in adopted.roles if x.actor.kind != "handler") == unrelated
    assert adopted.facilitator == previous.facilitator
    assert adopted.facilitator_source == previous.facilitator_source
    assert next(x for x in after.scene_casts if not x.open) == closed
    with pytest.raises(WorkflowError, match="STALE_CAST"):
        casts.change(
            ADMIN,
            "old-cached-cast-withdraw",
            900,
            old_view["game_revision"],
            old_view["cast_revision"],
            "withdraw",
            old,
        )
    game.dice.faces = (3, 3)
    identity = game.begin(
        PLAYER,
        "actual-cast-bound-roll",
        900,
        after.sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            heat=0,
            context="Actual first Handler source table",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(GameWorker(game), Gateway(), 3)
    request = next(x for x in game.choices(ADMIN) if x["kind"] == "tag_window")
    data = game.decision(ADMIN, request["id"])
    marker = next(x["token"] for x in data["tag_markers"] if x["label"] == "Handler")
    for viewer in (PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(
        game,
        ADMIN,
        "tag_window",
        options=("tag",),
        denied=("actual-first-handler-tag",),
        number=1,
        text="Actual source Handler Bond",
        fields={"marker": marker},
    )
    with ledger.engine.connect() as c:
        applied = game.action(c, identity)["data"]["tag_marker_applied"]
    assert applied["actor"] == actual.model_dump(mode="json") and applied["amount"] == 2


def test_after_actual_death_fresh_persona_never_adopts_a_preserved_old_cast_reference(ledger):
    svc, game = ready(ledger)
    casts = casting(svc)
    old = ActorRef(kind="handler", entity="1")
    join(casts, old)
    original_cast = next(x for x in state(game).scene_casts if x.open)
    end_original(svc, game, create=False)
    assert not any(x.actor.kind == "handler" for x in state(game).scene_casts[0].roles)
    # A recovered historical cast reference is deliberately retained as old evidence,
    # never a fresh body's casting authority.
    with ledger.transaction() as c:
        canon = state(game)
        canon.scene_casts.append(
            original_cast.model_copy(
                update={
                    "id": "actual-recovered-old-cast",
                    "channel": 901,
                }
            )
        )
        game.event(c, 1, "actual-historical-cast-recovery", "synthetic.old_cast_recovery", canon)
    save_fresh(svc, complete(svc, "Trainer"))
    accept_all(svc)
    before = next(x for x in state(game).scene_casts if x.id == "actual-recovered-old-cast")
    view = svc.view(ADMIN)
    svc.activate(
        ADMIN,
        "actual-replacement-without-cast-adoption",
        view["revision"],
        view["game_revision"],
        True,
    )
    after = state(game)
    assert next(x for x in after.scene_casts if x.id == before.id) == before
    assert current_ref(after, 1) != old
    assert all(x.actor != current_ref(after, 1) for x in before.roles)
