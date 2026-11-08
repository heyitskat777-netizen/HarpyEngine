"""Actual Harpy Defeat sources, factual native setup, independent resources and honest dice."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_beneath_service import ready as base
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_world import initial

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef, CastRole, SceneCast
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_harpy_defeat import harpy
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
from girlframe.engine.m3_void_state import HarpyIdentity
from girlframe.engine.m3_world_state import AdversaryPilot, Asset
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.onboarding import WorkflowError


def ready(store, faces=(3, 4), *, intense=False):
    game, worker, gateway = base(store, faces)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "playbooks"}}
            )
        }
    )
    ref = ActorRef(kind="external_pilot", entity="actual-native-harpy")
    with store.transaction() as c:
        canon = state(game)
        world = initial()
        native = AdversaryPilot(
            id=ref.entity,
            name="Actual Harpy",
            kind="harpy",
            girl="MOCKINGBIRD",
            frame="JANUS",
            controller=2,
            cell=(0, 0),
            assets=(
                Asset(
                    id="actual-harpy-frame-asset",
                    family="frame",
                    name="Actual Frame Asset",
                    description="Existing original mechanical capability",
                ),
            ),
        )
        canon.world = world.model_copy(update={"pilots": (native,)})
        scene = game.scene(c, 900)
        cast = SceneCast(
            id=scene["id"],
            channel=900,
            roles=tuple(
                CastRole(actor=actor, controller=human, source_event="actual-source-cast")
                for actor, human in (
                    (current_ref(canon, 1), 1),
                    (ref, 2),
                    (current_ref(canon, 3), 3),
                )
            ),
            facilitator=1,
            facilitator_source="actual-source-cast",
        )
        canon.scene_casts = [cast]
        if intense:
            canon = set_depth(canon, ref, current_ref(canon, 3), 2, "actual-intense-bond")
        game.event(c, 1, "actual-world-harpy-source", "synthetic.world", canon)
    service = HarpyDefeatService(store, game=game)
    facts = NativeHarpyFacts(
        actor=ref,
        linked=True,
        girl_cell=(0, 0),
        frame_cell=(0, 0),
        heat=7,
        frame_shutdown=False,
        body_incapacitated=False,
        custody="free",
        identities=(HarpyIdentity(id="actual-free", name="Free"),),
        tags=(),
        account="Actual original Harpy resources and linked body, no copied PC",
        facts_confirmed=True,
    )
    original_sheet = state(game).sheets["2"].model_copy(deep=True)
    proposal = service.propose_runtime(
        PLAYER, "actual-runtime-proposal", state(game).revision, facts
    )
    service.review_setup(
        ADMIN,
        "actual-runtime-confirm",
        proposal["id"],
        state(game).revision,
        True,
        "Actual GM review of known body and resources",
    )
    assert state(game).sheets["2"] == original_sheet
    effects = HandlerPlayService(store)
    grant = effects.start(ADMIN, "actual-damage-play", state(game).revision, (ref,))
    effects.submit(
        ADMIN,
        "actual-last-frame-damage",
        grant["id"],
        state(game).revision,
        "mess",
        Effect(
            kind="damage",
            target=ref,
            asset="actual-harpy-frame-asset",
            account="The actual last Frame Asset is damaged",
        ),
    )
    with store.engine.connect() as c:
        work = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.kind == "harpy_defeat"
                )
            )
            .mappings()
            .one()
        )
    return service, game, worker, gateway, ref, work["id"], grant["id"]


def choose(service, game, viewer, kind, **kwargs):
    with service.store.engine.connect() as c:
        row = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.kind == kind,
                    t.m2["m2_choices"].c.actor_id == str(viewer.user_id),
                    t.m2["m2_choices"].c.state == "pending",
                )
            )
            .mappings()
            .one()
        )
    return service.respond(viewer, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(**kwargs))


def rolled(store, faces=(3, 4), *, intense=False):
    service, game, worker, gateway, ref, work, grant = ready(store, faces, intense=intense)
    action = service.begin(PLAYER, "actual-defeat-confirm", work, channel=900)["action_id"]
    # The gateway owns actual acknowledgement; direct service roll uses this exact held lock.
    tick(worker, gateway, 1)
    with store.engine.connect() as c:
        if game.action(c, action)["data"].get("receipt") is None:
            service.roll(PLAYER, "actual-harpy-roll", action)
    for viewer in (PLAYER, OTHER, ADMIN):
        choose(service, game, viewer, "tag_window", options=("pass",))
    return service, game, worker, gateway, ref, work, grant, action


@pytest.mark.parametrize("intense,modifier", [(False, 2), (True, 4)])
def test_real_harpy_roll_uses_one_pair_plus_actual_scene_bond_not_heat_or_human_sheet(
    ledger, intense, modifier
):
    service, game, _, _, ref, _, _, action = rolled(ledger, (3, 4), intense=intense)
    receipt = service.inspect(PLAYER, action)["receipt"]
    assert receipt["faces"] == [3, 4] and receipt["pre_total"] == 7 + modifier
    assert receipt["heat"] == 0 and game.dice.calls == 1 and harpy(state(game), ref).heat == 7
    with pytest.raises(WorkflowError):
        service.roll(OTHER, "cannot-steal-roll", action)
    assert game.dice.calls == 1


def test_mid_message_deepens_actual_original_bond_and_finishes_real_damage_source(ledger):
    service, game, worker, gateway, ref, work, grant, action = rolled(ledger)
    original = current_ref(state(game), 3)
    original_body = harpy(state(game), ref)
    original_assets = next(x for x in state(game).world.pilots if x.id == ref.entity).assets
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("message",),
        fields={"girl": original.token},
        text="My actual final comms message to you",
    )
    canon = state(game)
    assert depth(canon, ref, original) == 1
    assert canon.harpy_defeats[-1].account == "My actual final comms message to you"
    escaped = harpy(canon, ref)
    assert escaped.cell is None and escaped.frame_cell is None
    assert escaped.body_vessel == original_body.body_vessel
    assert escaped.frame_instance == original_body.frame_instance and escaped.linked
    assert escaped.heat == original_body.heat and escaped.identities == original_body.identities
    assert next(x for x in canon.world.pilots if x.id == ref.entity).assets == original_assets
    assert canon.harpy_defeats[-1].escaped
    assert canon.harpy_defeats[-1].departed == (ref,)
    assert not any(x.actor == ref for x in canon.scene_casts[0].roles)
    assert service.inspect(PLAYER, action)["state"] == "complete"
    assert next(x for x in canon.handler_plays if x.id == grant).state == "complete"
    with ledger.engine.connect() as c:
        assert service._row(c, work)["state"] == "resolved"
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(t.m2["m2_responses"])
                .where(t.m2["m2_responses"].c.actor_id == "3")
            )
            == 1
        )  # Actual Tag pass, no fabricated Girl reply.
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def place_girl(store, game, *, defeated=False):
    from test_physical_operations import place

    with store.transaction() as c:
        canon = state(game)
        if not any(x.actor.kind == "pilot" and x.actor.entity == "3" for x in canon.placements):
            canon = place(canon, 3, mode="outside_frame")
        if defeated:
            for asset in canon.sheets["3"].assets:
                if asset.family == "frame":
                    asset.damaged = True
        game.event(c, 3, str(uuid4()), "synthetic.actual_girl_placement", canon)
    return current_ref(state(game), 3)


def test_high_plea_requires_original_girls_actual_refusal_and_creates_real_status_and_tag(ledger):
    service, game, _, _, ref, _, _, action = rolled(ledger, (6, 6))
    girl = place_girl(ledger, game)
    before = state(game)
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("plead",),
        fields={"girl": girl.token},
        text="Will you come with me?",
    )
    assert service.inspect(PLAYER, action)["state"] == "awaiting_choices"
    with ledger.engine.connect() as c:
        row = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(t.m2["m2_choices"].c.kind == "harpy_girl_plea")
            )
            .mappings()
            .one()
        )
    with pytest.raises(WorkflowError):
        service.respond(
            PLAYER,
            "cannot-answer-her",
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("refuse",), text="No fake response", fields={"tag": "Forged"}),
        )
    choose(
        service,
        game,
        OTHER,
        "harpy_girl_plea",
        options=("refuse",),
        text="I refuse to follow you",
        fields={"tag": "Left Behind"},
    )
    after = state(game)
    tag = harpy(after, ref).tags[-1]
    assert tag.label == "Left Behind" and tag.giver_ref == girl
    assert after.order[0] == 3 and after.sheets["3"].permissions == before.sheets["3"].permissions
    assert harpy(after, ref).cell is None and harpy(after, ref).frame_cell is None
    assert service.inspect(PLAYER, action)["state"] == "complete"


def test_high_actual_kidnap_requires_defeated_accessible_original_and_preserves_parked_frame(
    ledger,
):
    service, game, _, _, ref, _, _, action = rolled(ledger, (6, 6))
    girl = place_girl(ledger, game)
    snapshot = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="defeated"):
        choose(
            service,
            game,
            PLAYER,
            "harpy_defeat_select",
            options=("kidnap",),
            fields={"girl": girl.token},
            text="No imaginary defeat or custody",
        )
    assert state(game).model_dump_json() == snapshot
    girl = place_girl(ledger, game, defeated=True)
    original = next(x for x in state(game).placements if x.actor == girl)
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("kidnap",),
        fields={"girl": girl.token},
        text="I take the actual defeated accessible Girl",
    )
    captured = next(x for x in state(game).placements if x.actor == girl)
    assert captured.custody == ref and captured.girl_cell is None
    assert (
        captured.frame_cell == original.frame_cell
        and captured.frame_instance == original.frame_instance
    )
    assert service.inspect(PLAYER, action)["state"] == "complete"


def test_rift_needs_real_owned_navigation_and_gm_review_before_unknown_crossing_and_known_return(
    ledger,
):
    from girlframe.engine.m3_actors import resolve
    from girlframe.services.m3_actors import profiles

    service, game, _, _, ref, _, _, _ = rolled(ledger)
    girl = place_girl(ledger, game)
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("rift",),
        text="I tear open the actual Voidspace Rift and escape",
    )
    portal = state(game).void_rifts[-1]
    before = state(game)
    proposal = service.propose_route(
        OTHER,
        "actual-rift-follow",
        before.revision,
        girl,
        rift=portal.id,
        account="I follow the actual original Harpy through this Rift",
        navigation="Actual source-owned Voidspace navigation equipment and route",
    )
    assert next(x for x in state(game).placements if x.actor == girl).girl_cell == (0, 0)
    with pytest.raises(WorkflowError):
        service.review_route(
            OTHER,
            "cannot-review-own-route",
            proposal["id"],
            state(game).revision,
            allow=True,
            account="Not the source judge",
        )
    service.review_route(
        ADMIN,
        "actual-crossing-review",
        proposal["id"],
        state(game).revision,
        allow=True,
        account="The actual equipment permits this route",
    )
    with ledger.engine.connect() as c:
        view = resolve(state(game), girl, profiles(c, ledger.campaign_id))
    assert (
        view.cell is None and view.frame_cell == (0, 0) and view.offstage_source == proposal["id"]
    )
    current = state(game)
    returned = service.propose_route(
        OTHER,
        "actual-return-proposal",
        current.revision,
        girl,
        return_of=proposal["id"],
        destination=(1, 1),
        account="My real route back to this cell",
        navigation="Actual return navigation with the same equipment",
    )
    service.review_route(
        ADMIN,
        "actual-return-review",
        returned["id"],
        state(game).revision,
        allow=True,
        account="Actual source path and destination confirmed",
    )
    with ledger.engine.connect() as c:
        view = resolve(state(game), girl, profiles(c, ledger.campaign_id))
    assert view.cell == (1, 1) and view.frame_cell == (0, 0) and view.offstage_source is None
    assert state(game).sheets["3"].assets == before.sheets["3"].assets
    service.close_rift(PLAYER, "actual-owner-rift-close", portal.id, state(game).revision)
    assert not state(game).void_rifts[-1].open and harpy(state(game), ref).cell is None


def test_actual_dead_directors_frozen_human_may_finish_only_source_proved_procedural_question(
    ledger,
):
    from girlframe.engine.m3_battle_director import die
    from girlframe.engine.m3_director import enter
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_harpy_defeat import ended_director_judge

    _, game, _, _, _, _, _ = ready(ledger)
    director = ActorRef(kind="npc", entity="actual-director")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={
                "npcs": (
                    *canon.world.npcs,
                    Npc(
                        id=director.entity,
                        name="Actual Director",
                        jobs=("director",),
                        controller=3,
                        detail="Actual original Director",
                        cell=(0, 0),
                        revealed=True,
                    ),
                )
            }
        )
        canon = enter(
            canon,
            1,
            director.entity,
            "actual-presence",
            ("Defiant", "Afraid"),
            "actual-context-source",
        )
        context = canon.director_contexts[-1]
        old_handler = ActorRef(kind="handler", entity="1", incarnation=context.id)
        cast = canon.scene_casts[0]
        cast = cast.model_copy(
            update={
                "roles": tuple(
                    x.model_copy(update={"actor": old_handler}) if x.actor.kind == "handler" else x
                    for x in cast.roles
                )
                + (CastRole(actor=director, controller=3, source_event="actual-cast-director"),),
                "adjudicator": director,
                "revision": cast.revision + 1,
            }
        )
        canon.scene_casts[0] = cast
        game.event(
            c,
            1,
            "actual-director-presence",
            "synthetic.director",
            canon,
            event_id=context.source_event,
        )
        ended = die(canon, director, "actual-dead-director-source", "Actual Director dies")
        game.event(
            c,
            3,
            "actual-director-death",
            "synthetic.actual_director_death",
            ended,
            event_id="actual-dead-director-source",
        )
        current = ended.scene_casts[0]
        assert ended_director_judge(game, c, ended, cast, current, director, 3)
        assert not ended_director_judge(game, c, ended, cast, current, director, 1)
        assert not ended_director_judge(game, c, canon, cast, cast, director, 3)
        forged = current.model_copy(update={"roles": ()})
        assert not ended_director_judge(game, c, ended, cast, forged, director, 3)
        without_fact = ended.model_copy(deep=True)
        without_fact.facts = [x for x in ended.facts if x.get("kind") != "director_body_ended"]
        assert not ended_director_judge(game, c, without_fact, cast, current, director, 3)


def test_low_death_uses_actual_killer_review_and_tag_on_original_not_successor(ledger):
    service, game, _, _, ref, work, _, action = rolled(ledger, (1, 1))
    with ledger.engine.connect() as c:
        _, body, _ = service._source(c, work)
    killer = ActorRef.model_validate(body["requirement"]["opponent"])
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("death",),
        text="My actual last words and death",
        fields={"killer": killer.token, "tag": "Harpy Killer"},
    )
    assert service.inspect(PLAYER, action)["state"] == "awaiting_choices"
    choose(
        service,
        game,
        ADMIN,
        "harpy_killer_fact",
        flag=True,
        text="The actual original Handler's attack killed this Harpy",
    )
    canon = state(game)
    assert not next(x for x in canon.world.pilots if x.id == ref.entity).alive
    assert (
        canon.handler_tags[-1].label == "Harpy Killer" and canon.handler_tags[-1].giver_actor == ref
    )
    assert canon.sheets["2"].character_id != ref.entity
    assert service.inspect(PLAYER, action)["state"] == "complete"


def test_foundation_capture_waits_for_actual_present_captor_facts_and_no_teleport(ledger):
    service, game, _, _, ref, _, _, action = rolled(ledger, (6, 6))
    captor = place_girl(ledger, game)
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("foundation",),
        text="I shut down and let the actual Foundation take me",
    )
    body = harpy(state(game), ref)
    assert body.frame_shutdown and body.body_incapacitated and body.custody == "free"
    choose(
        service,
        game,
        ADMIN,
        "harpy_capture_fact",
        flag=True,
        fields={"captor": captor.token},
        text="The actual present Foundation Girl takes custody here",
    )
    body = harpy(state(game), ref)
    assert body.custody == "captured" and body.custodian == captor and body.cell == (0, 0)
    assert next(x for x in state(game).world.pilots if x.id == ref.entity).custodian == 3
    assert service.inspect(PLAYER, action)["state"] == "complete"


def test_low_sever_link_releases_roll_but_source_fight_requires_real_helpless_condition(ledger):
    from girlframe.engine.m3_actor_bonds import make_helpless
    from girlframe.engine.m3_harpy_defeat import fight_required

    service, game, _, _, ref, _, _, action = rolled(ledger, (1, 1))
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("shutdown",),
        flag=True,
        text="I sever the actual link and continue fighting",
    )
    canon = state(game)
    effect = canon.harpy_defeats[-1]
    body = harpy(canon, ref)
    assert not body.linked and body.frame_shutdown and not body.body_incapacitated
    assert fight_required(canon, ref) and service.inspect(PLAYER, action)["state"] == "complete"
    with pytest.raises(WorkflowError, match="not actually Helpless"):
        service.finish_fight(PLAYER, "no-false-helpless", effect.id, canon.revision)
    with ledger.transaction() as c:
        actual = make_helpless(state(game), ref, current_ref(state(game), 3), "actual-later-combat")
        game.event(
            c,
            3,
            "actual-helpless-source",
            "synthetic.actual_combat",
            actual,
            event_id="actual-later-combat",
        )
    service.finish_fight(PLAYER, "actual-source-fight-finish", effect.id, state(game).revision)
    assert not fight_required(state(game), ref)
    assert state(game).harpy_defeats[-1].phase == "complete"


def test_converted_originals_real_forbidden_defeat_requires_owned_manual_no_dice_then_actual_tags(
    ledger,
):
    from test_adjudication_service import forbid
    from test_void_service import five_no
    from test_void_service import ready as void_ready
    from test_void_service import respond as void_respond

    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_adjudication import AdjudicationService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    void, game, worker, gateway, _, work = void_ready(ledger)
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"world", "playbooks"}}
            )
        }
    )
    forbid(game, 2, "defeat")
    five_no(void, work)
    draft = void.get(PLAYER, work)["rebirth_choice"]
    draft["account"] = "The actual original patient chooses this new Harpy body"
    void_respond(void, work, "rebirth", dict(choice=draft, account=draft["account"]))
    tick(worker, gateway, 6)
    canon = state(game)
    actor = ActorRef(kind="external_pilot", entity=canon.harpy_states[-1].id)
    assert "2" not in canon.sheets and harpy(canon, actor).blocked_plays[0].play == "defeat"
    casts = CastService(ActorService(MissionService(ledger)))
    cast = casts.view(PLAYER, 900)
    casts.change(
        PLAYER,
        "actual-converted-cast",
        900,
        cast["game_revision"],
        cast["cast_revision"],
        "join",
        actor,
    )
    plays = HandlerPlayService(ledger)
    frame_assets = [x.id for x in harpy(state(game), actor).assets if x.family == "frame"]
    for asset in frame_assets:
        source = plays.start(ADMIN, str(uuid4()), state(game).revision, (actor,))
        plays.submit(
            ADMIN,
            str(uuid4()),
            source["id"],
            state(game).revision,
            "mess",
            Effect(
                kind="damage",
                target=actor,
                asset=asset,
                account="Actual damage to this original Harpy Frame",
            ),
        )
    service = HarpyDefeatService(ledger, game=game)
    with ledger.engine.connect() as c:
        work = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.kind == "harpy_defeat"
                )
            )
            .mappings()
            .one()["id"]
        )
    calls, heat = game.dice.calls, harpy(state(game), actor).heat
    action = service.begin(PLAYER, "actual-forbidden-harpy-defeat", work, channel=900)["action_id"]
    tick(worker, gateway, 3)
    assert (
        game.inspect(PLAYER, action)["state"] == "awaiting_adjudication"
        and game.dice.calls == calls
    )
    with ledger.engine.connect() as c:
        row = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.action_id == action,
                    t.m2["m2_choices"].c.kind == "manual_adjudication",
                )
            )
            .mappings()
            .one()
        )
    adjudications = AdjudicationService(ledger)
    preview = adjudications.get(ADMIN, row["id"])
    with pytest.raises(WorkflowError):
        adjudications.submit(
            PLAYER,
            "cannot-assign-own-harpy-total",
            row["id"],
            preview["revision"],
            11,
            "No fabricated patient result",
        )
    receipt = adjudications.submit(
        ADMIN,
        "actual-harpy-manual-total",
        row["id"],
        preview["revision"],
        8,
        "The actual source circumstances receive this explicit whole pre-Tag adjudicated total",
    )["receipt"]
    assert receipt["faces"] is None and receipt["heat"] == 0 and receipt["pre_total"] == 8
    assert game.dice.calls == calls and harpy(state(game), actor).heat == heat
    for viewer in (PLAYER, OTHER, ADMIN):
        choose(service, game, viewer, "tag_window", options=("pass",))
    girl = current_ref(state(game), 3)
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("message",),
        fields={"girl": girl.token},
        text="The actual Harpy's comms after manual adjudication",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == calls
    assert harpy(state(game), actor).blocked_plays[0].play == "defeat"


def test_low_other_scene_harpy_rescue_moves_actual_bodies_without_fabricating_rescuer_reply(ledger):
    (
        service,
        game,
        worker,
        gateway,
        ref,
        work,
        _,
    ) = ready(ledger, (1, 1))
    rescuer = ActorRef(kind="external_pilot", entity="actual-scene-rescuer")
    with ledger.transaction() as c:
        canon = state(game)
        original = canon.world.pilots[0]
        other = original.model_copy(
            update={
                "id": rescuer.entity,
                "name": "Actual rescuer",
                "controller": 3,
                "cell": (1, 1),
                "assets": tuple(
                    x.model_copy(update={"id": "rescuer-" + x.id, "damaged": False})
                    for x in original.assets
                ),
            }
        )
        canon.world = canon.world.model_copy(update={"pilots": (*canon.world.pilots, other)})
        cast = canon.scene_casts[0]
        canon.scene_casts[0] = cast.model_copy(
            update={
                "roles": (
                    *cast.roles,
                    CastRole(actor=rescuer, controller=3, source_event="actual-rescuer-presence"),
                ),
                "revision": cast.revision + 1,
            }
        )
        game.event(c, 3, "actual-rescuer-source", "synthetic.actual_harpy", canon)
    proposed = service.propose_runtime(
        OTHER,
        "actual-rescuer-facts",
        state(game).revision,
        NativeHarpyFacts(
            actor=rescuer,
            linked=True,
            girl_cell=(1, 1),
            frame_cell=(1, 1),
            heat=0,
            frame_shutdown=False,
            body_incapacitated=False,
            custody="free",
            identities=(HarpyIdentity(id="rescuer-free", name="Free"),),
            tags=(),
            account="Actual other Harpy body in this scene",
            facts_confirmed=True,
        ),
    )
    service.review_setup(
        ADMIN,
        "actual-rescuer-review",
        proposed["id"],
        state(game).revision,
        True,
        "Actual other Harpy's present physical facts",
    )
    action = service.begin(PLAYER, "actual-rescue-source-roll", work, channel=900)["action_id"]
    tick(worker, gateway, 3)
    for viewer in (PLAYER, OTHER, ADMIN):
        choose(service, game, viewer, "tag_window", options=("pass",))
    resources = next(x for x in state(game).world.pilots if x.id == rescuer.entity).assets
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("rescue",),
        fields={"rescuer": rescuer.token},
        text="The other actual scene Harpy rescues me and we escape",
    )
    assert harpy(state(game), ref).cell is None and harpy(state(game), rescuer).cell is None
    assert next(x for x in state(game).world.pilots if x.id == rescuer.entity).assets == resources
    with ledger.engine.connect() as c:
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(t.m2["m2_responses"])
                .where(t.m2["m2_responses"].c.actor_id == "3")
            )
            == 1
        )
    assert service.inspect(PLAYER, action)["state"] == "complete"


def test_native_harpy_result_dropdown_and_original_girl_reply_are_real_owned_forms(ledger):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m3_harpy_defeat import open_choice

    service, game, _, _, _, _, _, action = rolled(ledger, (6, 6))
    girl = place_girl(ledger, game)
    with ledger.engine.connect() as c:
        selected = c.execute(
            sa.select(t.m2["m2_choices"].c.id).where(
                t.m2["m2_choices"].c.action_id == action,
                t.m2["m2_choices"].c.kind == "harpy_defeat_select",
            )
        ).scalar_one()

    async def run():
        interaction = current(2, 89101)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, service, selected)
        picker = interaction.edit_original_response.call_args.kwargs["view"]
        assert {x[0] for x in picker.options} == {"plead", "kidnap", "foundation"}
        assert not await picker.interaction_check(current(3))
        await picker.open_item(interaction, "plead")
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="Will you come with me?", girl=(girl.token,))
        await form.confirm.callback(current(2, 89102))
        assert form.completed
        with ledger.engine.connect() as c:
            choice = c.scalar(
                sa.select(t.m2["m2_choices"].c.id).where(
                    t.m2["m2_choices"].c.kind == "harpy_girl_plea"
                )
            )
        other = current(3, 89103)
        await other.response.defer(ephemeral=True)
        await open_choice(other, service, choice)
        form = other.edit_original_response.call_args.kwargs["view"]
        form.values.update(mode=("refuse",), tag="Left Behind", account="I refuse your plea")
        await form.confirm.callback(current(3, 89104))
        assert form.completed

    asyncio.run(run())
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_harpy_choice_projection_does_not_reveal_another_humans_hidden_npc(ledger):
    from girlframe.engine.m3_world_state import Npc

    service, game, worker, gateway, _, work, _ = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        hidden = ActorRef(kind="npc", entity="PRIVATE_HIDDEN_ROLE_ID")
        canon.world = canon.world.model_copy(
            update={
                "npcs": (
                    *canon.world.npcs,
                    Npc(
                        id=hidden.entity,
                        name="PRIVATE_HIDDEN_NAME",
                        jobs=("guard",),
                        controller=3,
                        detail="PRIVATE_HIDDEN_DETAIL",
                        cell=(0, 0),
                        revealed=False,
                    ),
                )
            }
        )
        cast = canon.scene_casts[0]
        canon.scene_casts[0] = cast.model_copy(
            update={
                "roles": (
                    *cast.roles,
                    CastRole(actor=hidden, controller=3, source_event="actual-private-role"),
                ),
                "revision": cast.revision + 1,
            }
        )
        game.event(c, 3, "actual-hidden-role-source", "synthetic.private_role", canon)
    action = service.begin(PLAYER, "actual-private-safe-defeat", work, channel=900)["action_id"]
    tick(worker, gateway, 3)
    for viewer in (PLAYER, OTHER, ADMIN):
        choose(service, game, viewer, "tag_window", options=("pass",))
    with ledger.engine.connect() as c:
        choice = c.scalar(
            sa.select(t.m2["m2_choices"].c.id).where(
                t.m2["m2_choices"].c.action_id == action,
                t.m2["m2_choices"].c.kind == "harpy_defeat_select",
            )
        )
    assert "PRIVATE_HIDDEN" not in str(service.decision(PLAYER, choice))


def test_girls_actual_acceptance_preserves_her_current_piloted_frame_and_all_resources(ledger):
    from test_physical_operations import place

    service, game, _, _, ref, _, _, action = rolled(ledger, (6, 6))
    with ledger.transaction() as c:
        canon = place(state(game), 3, mode="piloting")
        game.event(c, 3, "actual-piloted-girl-source", "synthetic.actual_placement", canon)
    girl = current_ref(state(game), 3)
    resources = state(game).sheets["3"].model_dump_json()
    original = next(x for x in state(game).placements if x.actor == girl)
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("plead",),
        fields={"girl": girl.token},
        text="Come with me",
    )
    choose(
        service,
        game,
        OTHER,
        "harpy_girl_plea",
        options=("come",),
        text="I choose to come with you in the Frame I am actually piloting",
    )
    moved = next(x for x in state(game).placements if x.actor == girl)
    assert moved.mode == "piloting" and moved.girl_cell is None and moved.frame_cell is None
    assert moved.frame_instance == original.frame_instance and moved.vessel_id == original.vessel_id
    assert moved.custody is None and state(game).sheets["3"].model_dump_json() == resources
    assert (
        harpy(state(game), ref).cell is None and game.inspect(PLAYER, action)["state"] == "complete"
    )
