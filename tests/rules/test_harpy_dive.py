"""Actual Harpy Dive uses its own live resources and table, preserving a same-human PC."""

from uuid import uuid4

from test_harpy_actor_plays import begin, pass_tags, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_harpy_defeat import harpy, update
from girlframe.engine.m3_void_state import HarpyIdentity
from girlframe.engine.m3_world_state import Npc


def rolled(store, faces=(4, 5), *, unvoid=False, npc=False):
    service, game, _, actor = ready(store, faces=faces)
    with store.transaction() as c:
        canon = state(game)
        canon = update(
            canon,
            actor,
            identities=(
                HarpyIdentity(id="ordinary", name="Actual ordinary", marked=True),
                HarpyIdentity(id="protected", name="Actual protected", protected=True, marked=True),
            ),
        )
        if unvoid:
            canon.world = canon.world.model_copy(
                update={
                    "pilots": tuple(
                        x.model_copy(
                            update={
                                "assets": tuple(
                                    a.model_copy(update={"void": False}) for a in x.assets
                                )
                            }
                        )
                        if x.id == actor.entity
                        else x
                        for x in canon.world.pilots
                    )
                }
            )
        if npc:
            canon.world = canon.world.model_copy(
                update={
                    "npcs": (
                        Npc(
                            id="nearby",
                            name="Actual nearby NPC",
                            jobs=("civilian",),
                            detail="An actual person nearby",
                            controller=3,
                            cell=(0, 0),
                            revealed=True,
                        ),
                    )
                }
            )
        game.event(c, 1, str(uuid4()), "synthetic.actual_harpy_resources", canon)
    original = state(game).sheets["2"].model_dump_json()
    action = begin(service, actor, play="dive_deep")
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, actor, action, original


def test_actual_harpy_gains_void_unmarks_own_ids_and_never_mutates_same_human_pc(ledger):
    game, actor, action, pilot = rolled(ledger, unvoid=True)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("void_and_unmark_all",),
        text="Actual Harpy connection",
    )
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"asset": "actual-harpy-asset"},
        text="The actual limb alters further",
    )
    after = state(game)
    assert all(not x.marked for x in harpy(after, actor).identities)
    assert after.world.pilots[-1].assets[0].void
    assert after.sheets["2"].model_dump_json() == pilot
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_actual_harpy_erases_only_ordinary_id_and_each_real_human_answers(ledger):
    game, actor, action, pilot = rolled(ledger)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("erase_identity_and_table_question",),
        text="Actual connection",
    )
    answer(
        game, PLAYER, "dive_effect", fields={"identity": "ordinary"}, text="What do you remember?"
    )
    assert not any(x.id == "ordinary" for x in harpy(state(game), actor).identities)
    for human in (ADMIN, PLAYER, OTHER):
        answer(game, human, "dive_table_answer", text="Actual answer " + str(human.user_id))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert state(game).sheets["2"].model_dump_json() == pilot and game.dice.calls == 1


def test_high_harpy_table_replaces_identity_and_real_director_manifests_nearby_npc_void(ledger):
    game, actor, action, pilot = rolled(ledger, (6, 6), npc=True)
    original_order = state(game).order
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("table_replaces_identity",),
        text="Actual painful rewrite",
    )
    answer(
        game,
        ADMIN,
        "dive_effect",
        fields={"identity": "ordinary"},
        text="New agreed actual Identity",
    )
    for human in (ADMIN, PLAYER, OTHER):
        answer(
            game,
            human,
            "dive_table_agreement",
            flag=True,
            text="I agree with this exact source proposal",
        )
    answer(
        game,
        ADMIN,
        "dive_select",
        options=("nearby_npcs_gain_void",),
        text="Actual nearby manifestation",
    )
    answer(game, ADMIN, "dive_effect", fields={"nearby": "brain"})
    after = state(game)
    assert (
        next(x for x in harpy(after, actor).identities if x.id == "ordinary").name
        == "New agreed actual Identity"
    )
    assert after.world.npcs[0].tags[-1].label == "Void of the brain"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert after.order == original_order and after.sheets["2"].model_dump_json() == pilot
    assert game.dice.calls == 1


def test_actual_harpy_subsumes_actual_linked_cockpit_without_pilot_placement_or_healing(ledger):
    game, actor, action, pilot = rolled(ledger)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("locked_cockpit_extraction_requires_frame_consent",),
        text="Actual Harpy subsumption",
    )
    answer(game, PLAYER, "dive_effect", flag=True)
    after = state(game)
    assert harpy(after, actor).subsumed and not harpy(after, actor).vitals_active
    assert any(x.owner == actor and x.active for x in after.frame_locks)
    assert not any(x.actor == actor for x in after.placements)
    assert (
        after.sheets["2"].model_dump_json() == pilot
        and game.inspect(PLAYER, action)["state"] == "complete"
    )
