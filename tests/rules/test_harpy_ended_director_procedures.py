"""Already-owned Tag/Dive procedures survive actual Director death without new body authority."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change
from test_harpy_actor_plays import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_harpy_defeat import harpy, update
from girlframe.engine.m3_void_state import HarpyIdentity, HarpyTag
from girlframe.engine.m3_world import update as update_world
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_battle_director import DirectorService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError


def prepared(store):
    svc, game, cast, actor = ready(store, faces=(6, 6))
    director = ActorRef(kind="npc", entity="original-owned-dive-director")
    with store.transaction() as c:
        canon = state(game)
        canon = update(
            canon,
            actor,
            identities=(
                HarpyIdentity(id="actual-free", name="Free", protected=True),
                HarpyIdentity(id="actual-first", name="First actual self"),
                HarpyIdentity(id="actual-second", name="Second actual self"),
            ),
        )
        from girlframe.engine.m3_handler_consequences import active_handler

        canon = update(
            canon,
            actor,
            tags=(
                HarpyTag(
                    id="actually-observed-tag",
                    label="Seen through the Void",
                    giver=1,
                    giver_ref=active_handler(canon),
                    observers=(1, 2, 3),
                ),
            ),
        )
        canon.world = update_world(
            canon.world,
            npcs=(
                Npc(
                    id=director.entity,
                    name="Original Director",
                    controller=3,
                    cell=(0, 0),
                    jobs=("director",),
                    detail="Actual original procedural Director",
                ),
            ),
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_roles", canon)
    from girlframe.engine.m3_actor_bonds import current_ref

    change(cast, OTHER, "withdraw", current_ref(state(game), 3))
    change(cast, OTHER, "join", director)
    change(cast, OTHER, "adjudicate", director)
    plays = HandlerPlayService(store)
    grant = plays.start(ADMIN, str(uuid4()), state(game).revision, (director,))["id"]
    plays.submit(
        ADMIN,
        str(uuid4()),
        grant,
        state(game).revision,
        "mess",
        Effect(kind="damage", target=director, account="Actual previously owed strike"),
    )
    with store.engine.connect() as c:
        work = c.scalar(
            sa.select(t.m3["m3_required_work"].c.id).where(
                t.m3["m3_required_work"].c.kind == "director_damage"
            )
        )
    return svc, game, actor, director, work


@pytest.mark.parametrize("ending_stage", ["tag", "judge_choice"])
def test_actual_dead_directors_human_completes_only_frozen_tag_and_dive_procedures(
    ledger, ending_stage
):
    svc, game, actor, director, work = prepared(ledger)
    preview = svc.preview(PLAYER, 900, actor)
    action = svc.begin(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        preview["actor"]["source_sha256"],
        director,
        preview["cast_revision"],
        PlayInput(
            play="dive_deep",
            heat=0,
            context="Actual original owned Void connection",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, action)["state"] == "tag_window"

    def finish_actor_choice():
        answer(
            game,
            PLAYER,
            "dive_select",
            options=("erase_identity_and_table_question",),
            text="Actual original actor's choice",
        )
        answer(
            game, PLAYER, "dive_effect", fields={"identity": "actual-first"}, text="What remains?"
        )
        for viewer in (ADMIN, PLAYER, OTHER):
            answer(game, viewer, "dive_table_answer", text="Actual answer " + str(viewer.user_id))

    if ending_stage == "judge_choice":
        for viewer in (ADMIN, PLAYER, OTHER):
            answer(game, viewer, "tag_window", options=("pass",))
        finish_actor_choice()
    ending = DirectorService(ledger)
    ending.respond(
        OTHER,
        str(uuid4()),
        work,
        ending.get(OTHER, work)["revision"],
        "death",
        "The actual original Director dies from the already owed injury",
    )
    corpse = next(x for x in state(game).world.npcs if x.id == director.entity)
    assert not corpse.alive
    if ending_stage == "tag":
        owned = next(x for x in game.choices(OTHER) if x["kind"] == "tag_window")
        data = game.decision(OTHER, owned["id"])
        assert len(data["roles"]) == 1
        from girlframe.services.m3_tag_markers import current

        with ledger.engine.connect() as c:
            markers = current(game, c, state(game), game.action(c, action), OTHER.user_id)
        assert len(markers) == 1 and markers[0].actor is None
        assert markers[0].bonus == 1 and markers[0].bond_depth == 0
        answer(
            game,
            OTHER,
            "tag_window",
            options=("tag",),
            denied=("actually-observed-tag",),
            number=1,
            text="This actual observed Tag helps the original Harpy",
            fields={"as_actor": markers[0].token},
        )
        for viewer in (ADMIN, PLAYER):
            answer(game, viewer, "tag_window", options=("pass",))
        with ledger.engine.connect() as c:
            modifier = game.action(c, action)["data"]["modifiers"][-1]
        assert modifier["amount"] == 1
        finish_actor_choice()
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "dive_select")
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("table_replaces_identity",), text="Not my source"),
        )
    answer(
        game,
        OTHER,
        "dive_select",
        options=("table_replaces_identity",),
        text="The real original human chooses this episode's remaining consequence",
    )
    answer(
        game, OTHER, "dive_effect", fields={"identity": "actual-second"}, text="Changed by the Void"
    )
    for viewer in (ADMIN, PLAYER, OTHER):
        answer(
            game,
            viewer,
            "dive_table_agreement",
            flag=True,
            text="Actual human agreement " + str(viewer.user_id),
        )
    canon = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert next(x for x in canon.world.npcs if x.id == director.entity) == corpse
    assert any(x.name == "Changed by the Void" for x in harpy(canon, actor).identities)
    assert canon.handler == 1
