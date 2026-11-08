"""Only exact original-body endings close fighting and own postcareer death Tags."""

from uuid import uuid4

from test_harpy_defeat import choose, rolled
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine import m3_handler_consequences as handler
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_state import Draft, HandlerPersona
from girlframe.engine.m3_harpy_defeat import die, fight_required, harpy


def test_actual_death_closes_cut_link_fight_with_ending_source_not_fake_helpless(ledger):
    service, game, _, _, actor, _, _, _ = rolled(ledger, (1, 1))
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("shutdown",),
        text="Actual cut link and continue fighting",
        flag=True,
    )
    before = state(game)
    assert fight_required(before, actor) and not is_helpless(before, actor)
    actual = harpy(before, actor)
    after = die(before, actor, "actual-separate-fatal-source")
    effect = after.harpy_defeats[-1]
    assert effect.phase == "complete" and effect.ended_reason == "original_died"
    assert effect.ended_event == "actual-separate-fatal-source"
    assert not fight_required(after, actor) and not is_helpless(after, actor)
    assert harpy(after, actor).cell == actual.cell
    assert harpy(after, actor).frame_instance == actual.frame_instance
    assert harpy(after, actor).identities == actual.identities
    assert harpy(before, actor).condition_event != "actual-separate-fatal-source"


def test_owed_death_tag_is_recorded_on_actual_archived_killer_and_never_new_handler_body(ledger):
    service, game, _, _, actor, work, _, action = rolled(ledger, (1, 1))
    with ledger.engine.connect() as c:
        _, body, _ = service._source(c, work)
    killer = ActorRef.model_validate(body["requirement"]["opponent"])
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("death",),
        text="Actual dying Harpy's choice",
        fields={"killer": killer.token, "tag": "Harpy Killer"},
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon, consequence = handler.require(
            canon,
            killer,
            trigger="helpless",
            source_action=None,
            source_event="separately-owed-actual-handler-source",
            opponent=actor,
            appointment="actual-appointment",
            occurrence="actual-separate-fatal-choice",
        )
        canon = handler.apply(
            canon, consequence, "death", "Actual original Handler dies", "real-handler-death"
        )
        original_archive = canon.handler_archives[-1]
        game.event(
            c,
            1,
            str(uuid4()),
            "m3.handler_consequence_resolved",
            canon,
            event_id="real-handler-death",
            consequence=consequence,
        )
        canon.handler_persona = HandlerPersona(
            id="actual-new-handler-body",
            owner=1,
            appointment="actual-appointment",
            draft=Draft(name="Entirely new body"),
            source_event="actual-new-handler-birth",
        )
        game.event(
            c, 1, str(uuid4()), "synthetic.new_handler", canon, event_id="actual-new-handler-birth"
        )
    choose(
        service,
        game,
        ADMIN,
        "harpy_killer_fact",
        flag=True,
        text="The recorded actual original Handler killed this Harpy",
    )
    canon = state(game)
    effect = canon.harpy_defeats[-1]
    assert effect.phase == "complete" and effect.archived_tag
    assert effect.tag == "Harpy Killer" and effect.tag_id
    assert effect.killer == killer and effect.tag_recipient == killer
    assert effect.tag_applied_event is None
    assert canon.handler_archives[-1] == original_archive
    assert canon.handler_tags == [] and handler.active_handler(canon) != killer
    assert service.inspect(PLAYER, action)["state"] == "complete"


def test_actual_all_girl_assets_damaged_when_cutting_link_is_helpless_against_real_source_foe(
    ledger,
):
    from girlframe.engine.m3_world_state import Asset

    service, game, _, _, actor, work, _, _ = rolled(ledger, (1, 1))
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={
                "pilots": tuple(
                    x.model_copy(
                        update={
                            "assets": (
                                *x.assets,
                                Asset(
                                    id="actual-already-damaged-girl-asset",
                                    name="Actual Girl Asset",
                                    family="girl",
                                    description="Actual source extra Girl damage before unlink",
                                    damaged=True,
                                ),
                            )
                        }
                    )
                    if x.id == actor.entity
                    else x
                    for x in canon.world.pilots
                )
            }
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_additional_girl_damage", canon)
    with ledger.engine.connect() as c:
        _, body, _ = service._source(c, work)
    foe = ActorRef.model_validate(body["requirement"]["opponent"])
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("shutdown",),
        flag=True,
        text="Actually cut my link with all actual Girl Assets already damaged",
    )
    canon = state(game)
    assert not harpy(canon, actor).linked
    assert is_helpless(canon, actor, foe) and not fight_required(canon, actor)
    assert canon.harpy_defeats[-1].phase == "complete"
    assert canon.helpless_conditions[-1].subject == actor
    assert canon.helpless_conditions[-1].foe == foe
