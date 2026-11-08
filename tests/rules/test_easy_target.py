"""Printed Easy Target outcomes through real owned choices, Plays and consequences."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_easy_target import EasyTargetService, prove
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

CONTEXT = "PRIVATE_TASK I endure the actual dangerous drill requested by the other person"


def ready(store, tmp_path, monkeypatch, *, mixed=False):
    _, game = service(store, girl="NEWGIRL", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        actual.order = (2, 3)
        actual.sheets["2"].heat = 4
        actual.sheets["3"].heat = 4
        if mixed:
            actual.world = actual.world.model_copy(
                update={
                    "npcs": tuple(
                        Npc(
                            id=x,
                            name=x,
                            jobs=("civilian",),
                            detail="An actual independent scene person",
                            controller=3,
                            cell=(0, 0),
                            revealed=True,
                        )
                        for x in ("cohort", "bystander")
                    )
                }
            )
        game.event(c, 1, str(uuid4()), "synthetic.actual_source_bodies_and_resources", actual)
    if mixed:
        cast = CastService(ActorService(MissionService(store)))
        for ref, viewer in (
            (ActorRef(kind="npc", entity="cohort"), OTHER),
            (ActorRef(kind="npc", entity="bystander"), OTHER),
            (current_ref(state(game), 1), ADMIN),
        ):
            data = cast.view(viewer, 900)
            cast.change(
                viewer, str(uuid4()), 900, data["game_revision"], data["cast_revision"], "join", ref
            )
    return game, GameWorker(game), Gateway(), EasyTargetService(game)


def source(game, worker, gateway, faces=(3, 4), *, selected=None):
    game.dice.faces = faces
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            heat=1,
            context="PRIVATE_MISTAKE I make the actual foolish mistake",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    if sum(faces) + 1 >= 8:
        ref = selected or current_ref(state(game), 3)
        answer(
            game,
            PLAYER,
            "easy_target_select",
            options=(ref.token,),
            text="I choose this actual person",
        )
        answer(
            game, OTHER, "easy_target_tag", text="Actual source vulnerability " + str(uuid4())[:8]
        )
    return identity


def choose(game, viewer, actor, urge, *, play="keep_your_head", context=CONTEXT, primary=None):
    fields = {} if urge in ("pass", "cohort", "contempt") else dict(play=play, context=context)
    if primary:
        fields["primary"] = primary
    return answer(
        game,
        viewer,
        "easy_target_react:" + actor.token,
        options=(urge,),
        fields=fields,
        text="PRIVATE_URGE My actual person chooses " + urge,
    )


def validate(game, actor):
    answer(
        game,
        ADMIN,
        "easy_target_validate:" + actor.token,
        flag=True,
        text="The real task has the printed trigger and an actual implemented source",
    )


def child(game, worker, gateway, work, *, viewer=PLAYER, faces=(4, 4), tag=False, target=None):
    value = rules.get(state(game), rules.Reaction, work)
    game.dice.faces = faces
    identity = game.begin(
        viewer,
        str(uuid4()),
        900,
        state(game).sheets[str(viewer.user_id)].revision,
        PlayInput(
            play=value.play,
            parent=value.session,
            source_work=work,
            context=value.context,
            target_actor=target,
            heat=0,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if tag:
        data = next(x for x in game.choices(OTHER) if x["kind"] == "tag_window")
        detail = game.decision(OTHER, data["id"])
        marker = next(x["token"] for x in detail["tag_markers"] if x["label"] == "cohort")
        actual_tag = state(game).sheets["2"].tags[-1]
        answer(
            game,
            OTHER,
            "tag_window",
            options=("tag",),
            denied=(actual_tag.id,),
            number=1,
            fields={"marker": marker},
            text="This actual cohort helps the actual primary task",
        )
        answer(game, PLAYER, "tag_window", options=("pass",))
        answer(game, ADMIN, "tag_window", options=("pass",))
        for viewer2 in (PLAYER, OTHER, ADMIN):
            for row in game.choices(viewer2):
                if row["kind"] in ("tag_marker_agreement", "tag_consent"):
                    game.respond(
                        viewer2, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(flag=True)
                    )
    else:
        pass_tags(game)
    return identity


def finish_keep(game, viewer=PLAYER):
    answer(game, viewer, "actor_keep", options=("desperate", "tough"), denied=("sexy",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual completed endurance is enough")


def assault(game, worker, gateway, *, parent=None, work=None):
    actor, target = current_ref(state(game), 3), current_ref(state(game), 2)
    service = BattleService(game.store)
    data = service.preview(OTHER, 900)
    attacker = next(x for x in data["actors"] if x["ref"] == actor.model_dump(mode="json"))
    victim = next(x for x in data["actors"] if x["ref"] == target.model_dump(mode="json"))
    strike_id = next(
        x.id for x in state(game).sheets["3"].assets if x.family == "girl" and not x.damaged
    )
    strike = next(x for x in attacker["assets"] if x["id"] == strike_id)
    victim_id = next(
        x.id for x in state(game).sheets["2"].assets if x.family == "girl" and not x.damaged
    )
    asset = next(x for x in victim["assets"] if x["id"] == victim_id)
    context = (
        rules.get(state(game), rules.Reaction, work).context
        if work
        else "A real physical bout turns into actual bodily harm"
    )
    declaration = Declaration(
        play="all_out_assault",
        actor=actor,
        target=target,
        attacking_asset=strike["id"],
        target_asset=asset["id"],
        actor_sha256=attacker["sha256"],
        target_sha256=victim["sha256"],
        account=context,
    )
    proposed = service.propose(
        OTHER, str(uuid4()), data["revision"], 900, declaration, parent=parent
    )
    service.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        proposed["id"],
        opening=True,
        reach=True,
        outside_permission=True,
        indirect=False,
        evidence="Actual bodies, opening, reach and bodily impact are established",
    )
    game.dice.faces = (4, 5)
    identity = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="all_out_assault",
            parent=parent,
            source_work=work,
            target_actor=target,
            attacking_asset=declaration.attacking_asset,
            target_asset=declaration.target_asset,
            battle_context=proposed["id"],
            heat=0,
            context=context,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    for viewer in (ADMIN, PLAYER, OTHER):
        answer(
            game,
            viewer,
            "battle_assault_table",
            flag=False,
            text="Actual bodily attack, without vast advantage",
        )
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset["id"]).damaged
    return identity


def test_mid_actual_use_and_requested_work_keep_original_owners_and_real_consequences(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    actor = current_ref(state(game), 3)
    first = source(game, worker, gateway)
    choose(game, OTHER, actor, "use")
    work = rules.identity(first, actor)
    validate(game, actor)
    before = state(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"].startswith("easy_target_child:"))
    with pytest.raises(WorkflowError, match="REQUIRED_ACTUAL_PERFORMANCE"):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(text="Not an actual child"),
        )
    assert state(game) == before
    child(game, worker, gateway, work)
    finish_keep(game)
    answer(
        game,
        PLAYER,
        "easy_target_bond:" + actor.token,
        flag=True,
        text="I deepen our actual Bond after she finishes using me",
    )
    assert depth(state(game), current_ref(state(game), 2), actor) >= 1
    assert game.inspect(PLAYER, first)["state"] == "complete"
    tick(worker, gateway, 5)
    second = source(game, worker, gateway)
    choose(game, OTHER, actor, "request")
    validate(game, actor)
    child(game, worker, gateway, rules.identity(second, actor))
    finish_keep(game)
    answer(
        game,
        OTHER,
        "easy_target_judge:" + actor.token,
        flag=True,
        text="The original Newgirl actually did my requested work well",
    )
    assert state(game).order[0] == 2 and game.inspect(PLAYER, second)["state"] == "complete"
    with ledger.engine.connect() as c:
        assert "PRIVATE_URGE" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert prove(game, c, state(game), work).performance_event
    with pytest.raises(WorkflowError):
        controls.view(GuildViewer(9, 200, True, False), work)


def test_mid_hurt_real_body_damage_actual_newgirl_selected_and_executed_punishment(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    actor = current_ref(state(game), 3)
    identity = source(game, worker, gateway)
    choose(
        game,
        OTHER,
        actor,
        "hurt",
        play="all_out_assault",
        context="Actual unarmed bodily strike after the foolish mistake",
    )
    validate(game, actor)
    work = rules.identity(identity, actor)
    assault(game, worker, gateway, parent=identity, work=work)
    case = state(game).role_punishments[-1]
    assert case.chooser == current_ref(state(game), 2) and case.subject == actor
    role = RolePunishmentService(game)

    def change(viewer, **values):
        return role.change(
            viewer, str(uuid4()), case.id, role.get(viewer, case.id)["revision"], **values
        )

    details = Details(kind="quality_time", tag="Actual chosen quality time")
    change(
        PLAYER, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(ADMIN, scene="The Handler performs the original Newgirl's actually chosen consequence")
    change(OTHER, attest=True)
    change(ADMIN, execute=True, account="I carry out the actual selected quality time")
    assert controls.view(PLAYER, work)["work"]["completed_event"]


def test_high_each_actual_person_optional_cohort_real_assistance_and_exact_departure(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, mixed=True)
    actual = state(game)
    cohort, bystander = (ActorRef(kind="npc", entity=x) for x in ("cohort", "bystander"))
    reactor, handler = current_ref(actual, 3), current_ref(actual, 1)
    identity = source(game, worker, gateway, (5, 5), selected=cohort)
    choose(game, OTHER, reactor, "request")
    choose(game, OTHER, cohort, "cohort", primary=rules.identity(identity, reactor))
    choose(game, OTHER, bystander, "pass")
    choose(game, ADMIN, handler, "contempt")
    validate(game, reactor)
    answer(
        game,
        ADMIN,
        "easy_target_contempt:" + handler.token,
        options=("leave",),
        text="My actual Handler person leaves with contempt",
    )
    assert not any(x.actor == handler for x in state(game).scene_casts[0].roles)
    assert any(x.actor == cohort for x in state(game).scene_casts[0].roles)
    child(game, worker, gateway, rules.identity(identity, reactor), tag=True)
    finish_keep(game)
    own = controls.view(OTHER, rules.identity(identity, cohort))["work"]
    primary = controls.view(PLAYER, rules.identity(identity, reactor))["work"]
    assert own["consequence"] == primary["consequence"] == "cohort-exempt"
    assert state(game).order[-1] == 2 and game.inspect(PLAYER, identity)["state"] == "complete"
    assert not any(x["kind"].startswith("easy_target_judge:") for x in game.choices(OTHER))

    async def reopen():
        from girlframe.discord_adapter.m3_easy_target import open_easy_target

        interaction = current(3, 98501)
        interaction.channel_id = 999
        await interaction.response.defer(ephemeral=True)
        await open_easy_target(
            interaction, EasyTargetService(game), rules.identity(identity, cohort)
        )
        assert "cohort-exempt" in str(interaction.edit_original_response.call_args)

    asyncio.run(reopen())


def test_low_actual_status_and_performance_then_real_protection_and_failure(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    identity = source(game, worker, gateway, (1, 1))
    actor = current_ref(state(game), 3)
    assert state(game).order[-1] == 2 and not rules.get(state(game), rules.Session, identity).tag
    row = next(x for x in game.choices(OTHER) if x["kind"] == "easy_target_react:" + actor.token)
    before = state(game)
    original = game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic rollback")

    answer_value = ChoiceAnswer(
        options=("other",),
        fields=dict(play="keep_your_head", context=CONTEXT, performer=actor.token),
        text="PRIVATE_OFF_LIST I ignore her and endure the real dangerous drill",
    )
    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        game.respond(OTHER, "98510", row["id"], row["revision"], answer_value)
    assert state(game) == before
    monkeypatch.setattr(game, "event", original)
    saved = game.respond(OTHER, "98510", row["id"], row["revision"], answer_value)
    assert game.respond(OTHER, "98510", row["id"], row["revision"], answer_value) == saved
    validate(game, actor)
    child(game, worker, gateway, rules.identity(identity, actor), viewer=OTHER)
    finish_keep(game, OTHER)
    assert controls.view(OTHER, rules.identity(identity, actor))["work"]["completed_event"]
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 2

    tick(worker, gateway, 5)
    protection = source(game, worker, gateway)
    choose(
        game,
        OTHER,
        actor,
        "protect",
        play="engage",
        context="I actually shield the original Newgirl in this physical drill",
    )
    validate(game, actor)
    ward = current_ref(state(game), 2)
    guard_work = rules.identity(protection, actor)
    child(game, worker, gateway, guard_work, viewer=OTHER, target=ward, faces=(4, 4))
    assets = [x for x in state(game).sheets["3"].assets if not x.damaged][:2]
    answer(
        game,
        OTHER,
        "engage_maneuvers",
        options=("protect", "cover"),
        fields={"protect": assets[0].id, "cover": assets[1].id},
        text="I take real protective position around the original ward",
    )
    assert controls.view(PLAYER, guard_work)["work"]["protection_event"]
    tick(worker, gateway, 5)
    assault(game, worker, gateway)
    saved = controls.view(PLAYER, guard_work)
    assert saved["can_failure_tag"]
    payload = (
        PLAYER,
        "actual-failure-once",
        guard_work,
        saved["revision"],
        True,
        "Failed to shield me",
    )
    result = controls.failure_tag(*payload)
    assert controls.failure_tag(*payload) == result
    assert state(game).sheets["3"].tags[-1].giver_actor == ward
