"""CONSUME's printed ordinary sources and real immediate consequences.

Only the link/Eat smoke is intended to run during implementation. The remaining
distinct printed normals are authored for the final P1 selection.
"""

from uuid import uuid4

import pytest
from test_enforcement_initiative import cast_target
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_consume as rules
from girlframe.engine.m2 import QUESTIONS, ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_consume import ConsumeService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store, tmp_path, monkeypatch):
    _, game = service(store, girl="OLDGEN", frame="CONSUME")
    approved(
        store, game, tmp_path, monkeypatch, extra=(rules.STARVATION, rules.EAT, *rules.REQUISITIONS)
    )
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "playbooks"}}
            )
        }
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2, mode="outside_frame"), 3, mode="outside_frame")
        canon.sheets["2"].permissions = 20
        canon.sheets["2"].heat = 1
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.actual_consume_bodies_and_resources", canon)
    return game, GameWorker(game), Gateway(), ConsumeService(game)


def cockpit(game, operation):
    physical = PhysicalService(game.store)
    data = physical.preview(PLAYER)
    payload = (
        PLAYER,
        str(uuid4()),
        data["game_revision"],
        CockpitAction(
            actor=ActorRef.model_validate(data["actor"]),
            operation=operation,
            expected_position=data["position_sha256"],
            account="My actual original cockpit transition",
            confirmed=True,
        ),
    )
    result = physical.operate(*payload)
    assert physical.operate(*payload) == result
    return result


def acquire(controls, rule):
    data = controls.menu(PLAYER, 900)
    return controls.purchase(
        PLAYER,
        str(uuid4()),
        data["source_sha256"],
        rule,
        "I voluntarily pay two actual Permissions",
    )


def roll(
    game,
    worker,
    gateway,
    *,
    play="consume_eat",
    target=None,
    faces=(3, 4),
    heat=1,
    source_work=None,
    piloting=False,
):
    game.dice.faces = faces
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=play,
            target_actor=target,
            heat=heat,
            source_work=source_work,
            piloting=piloting,
            context="I actually lunge at this person"
            if play == "consume_eat"
            else "I actually succumb to this impulse"
            if play == "consume_feral"
            else "I perform this genuinely triggered source Play",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    return action


def choose(game, viewer, kind, option=None, **fields):
    return answer(
        game,
        viewer,
        kind,
        options=(option,) if option else (),
        fields=fields,
        text="My actual original printed choice",
    )


def asset(game, owner, family="girl"):
    return next(
        x.id
        for x in state(game).sheets[str(owner)].assets
        if x.family == family
        and not x.damaged
        and x.id != rules.starving_asset(rules.frame(state(game), current_ref(state(game), 2)))
    )


def npc_target(game):
    world = WorldService(MissionService(game.store))
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="consume-prey",
            name="Actual on-scene target",
            jobs=("scientist",),
            detail="The actual original scientist",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    target = ActorRef(kind="npc", entity="consume-prey")
    cast_target(game, target)
    return target


def test_genuine_link_then_actual_mid_bite_lowers_hunger_and_removes_temporary_asset(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    assert rules.hunger(state(game), actor) == "Quiet"
    heat = state(game).sheets["2"].heat
    cockpit(game, "pilot")
    canon = state(game)
    assert rules.hunger(canon, actor) == "Gnawing" and canon.sheets["2"].heat == heat + 3
    temporary = rules.starving_asset(rules.frame(canon, actor))
    assert any(
        x.id == temporary and x.name == "Starving" and x.family == "girl"
        for x in canon.sheets["2"].assets
    )
    assert len([x for x in canon.sheets["3"].assets if x.family == "girl" and not x.damaged]) >= 2
    damaged = asset(game, 3)
    action = roll(game, worker, gateway, target=target)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "consume_eat")
    payload = (
        PLAYER,
        "consume-bite-once",
        row["id"],
        row["revision"],
        ChoiceAnswer(
            options=("bite",), fields={"target_asset": damaged}, text="I actually bite down"
        ),
    )
    result = game.respond(*payload)
    assert game.respond(*payload) == result
    canon = state(game)
    assert next(x for x in canon.sheets["3"].assets if x.id == damaged).damaged
    assert rules.hunger(canon, actor) == "Quiet"
    assert not any(x.id == temporary for x in canon.sheets["2"].assets)
    assert canon.sheets["2"].heat == heat + 2
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert not controls.tasks(OTHER)


@pytest.mark.parametrize(
    "branch",
    ["nonvulnerable_bite", "swallow_rip_out", "low_escape", "high_nibble", "high_kill_forget"],
)
def test_actual_eat_printed_branches_costs_custody_escape_bond_and_true_kill(
    ledger, tmp_path, monkeypatch, branch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    if branch == "high_nibble":
        acquire(controls, rules.NIBBLE)
    if branch == "high_kill_forget":
        acquire(controls, rules.DRIVE)
        target = npc_target(game)
    if branch in ("low_escape", "high_nibble", "high_kill_forget"):
        cockpit(game, "pilot")
    own_asset, target_asset = asset(game, 2), asset(game, 3)
    before_bond = depth(state(game), actor, target)
    faces = (1, 1) if branch == "low_escape" else (6, 6) if branch.startswith("high") else (3, 4)
    action = roll(game, worker, gateway, target=target, faces=faces)
    if branch == "nonvulnerable_bite":
        choose(game, PLAYER, "consume_eat", "bite", own_asset=own_asset, target_asset=target_asset)
        assert next(x for x in state(game).sheets["2"].assets if x.id == own_asset).damaged
        assert next(x for x in state(game).sheets["3"].assets if x.id == target_asset).damaged
    elif branch == "swallow_rip_out":
        choose(game, PLAYER, "consume_eat", "swallow", own_asset=own_asset)
        consumed = rules.records(state(game), rules.Consumption)[-1]
        assert consumed.custody
        actual = next(x for x in state(game).placements if x.actor == target)
        assert actual.custody == actor
        payload = (
            OTHER,
            "actual-prisoner-rip-out",
            consumed.id,
            state(game).revision,
            "I actually rip my way out",
        )
        result = controls.rip_out(*payload)
        assert controls.rip_out(*payload) == result
        assert next(x for x in state(game).placements if x.actor == target).custody is None
    elif branch == "low_escape":
        choose(game, PLAYER, "consume_eat", "repelled", own_asset=own_asset)
        assert next(x for x in state(game).sheets["2"].assets if x.id == own_asset).damaged
        assert rules.records(state(game), rules.Consumption)[-1].option == "repelled"
        assert any(x.get("kind") == "consume_escape" for x in state(game).facts)
    elif branch == "high_nibble":
        choose(game, PLAYER, "consume_eat", "nibble")
        canon = state(game)
        hold = rules.records(canon, rules.MouthHold)[-1]
        assert depth(canon, actor, target) == min(2, before_bond + 1)
        assert is_helpless(canon, actor, target) and rules.hunger(canon, actor) == "Ravenous"
        controls.release_mouth(
            OTHER, str(uuid4()), hold.id, canon.revision, "My actual body part leaves the mouth"
        )
        assert not rules.mouth_helpless(state(game), actor, target)
    else:
        choose(game, PLAYER, "consume_eat", "kill")
        assert not next(x for x in state(game).world.npcs if x.id == target.entity).alive
        choose(game, PLAYER, "consume_erase", "forget")
        assert rules.forgotten(state(game), target)
        assert rules.hunger(state(game), actor) == "Quiet"
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_real_repeated_link_reaches_ravenous_without_repeated_heat_then_food_roll_uses_four(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch)
    actor = current_ref(state(game), 2)
    before = state(game).sheets["2"].heat
    cockpit(game, "pilot")
    cockpit(game, "exit")
    cockpit(game, "pilot")
    assert rules.hunger(state(game), actor) == "Ravenous"
    assert state(game).sheets["2"].heat == before + 3
    target = npc_target(game)
    with pytest.raises(WorkflowError, match="RAVENOUS"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="consume_eat",
                target_actor=target,
                heat=1,
                context="Actual ravenous lunge",
                trigger_confirmed=True,
            ),
        )
    action = roll(game, worker, gateway, target=target, faces=(3, 4), heat=0)
    choose(game, PLAYER, "consume_eat", "kill")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert rules.hunger(state(game), actor) == "Quiet"
    assert state(game).sheets["2"].heat == before + 3


@pytest.mark.parametrize("branch", ["rabid", "bloodhound", "high", "low"])
def test_real_feral_source_tags_bonuses_and_required_original_owned_continuations(
    ledger, tmp_path, monkeypatch, branch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    acquire(controls, rules.FERAL)
    actor = current_ref(state(game), 2)
    faces = (6, 6) if branch == "high" else (1, 1) if branch == "low" else (4, 5)
    action = roll(game, worker, gateway, play="consume_feral", faces=faces, heat=0)
    chooser = ADMIN if branch in ("high", "low") else PLAYER
    if branch == "low":
        answer(game, chooser, "consume_feral", text="Leash held tight")
    else:
        choose(game, chooser, "consume_feral", "bloodhound" if branch == "high" else branch)
    fact = rules.records(state(game), rules.FeralEffect)[-1]
    assert rules.tag(state(game), actor, fact.tag)
    if branch == "high":
        child = rules.records(state(game), rules.Reaffirmation)[-1]
        assert game.inspect(PLAYER, action)["state"] != "complete"
        actual = roll(
            game, worker, gateway, play="check_sensors", faces=(3, 4), heat=0, source_work=child.id
        )
        answer(game, PLAYER, "actor_sensors", options=QUESTIONS[:2])
        answer(
            game,
            ADMIN,
            "handler_sensors",
            fields={"a1": "Actual factual sign", "a2": "Actual factual prey trail"},
        )
        tick(worker, gateway, 6)
        assert game.inspect(PLAYER, actual)["state"] == "complete"
        assert next(
            x for x in rules.records(state(game), rules.Reaffirmation) if x.id == child.id
        ).completed_event
    elif branch == "low":
        assert rules.disobey_low(state(game), actor)
        tick(worker, gateway, 6)
        order = game.issue_order(ADMIN, str(uuid4()), 900, 2, "Actually remain here")
        tick(worker, gateway, 2)
        answer(game, PLAYER, "order_response", options=("disobey",))
        refused = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="disobey_orders",
                parent=order["action_id"],
                order_id=order["order_id"],
                heat=0,
                context="My actual refusal",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        assert game.inspect(PLAYER, refused)["state"] == "complete"
        assert not any(x["kind"] == "actor_disobey" for x in game.choices(PLAYER))
    else:
        assert (
            rules.feral_bonus(state(game), actor, "flirt" if branch == "rabid" else "check_sensors")
            == 1
        )
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_actual_hound_additional_smell_has_real_original_handler_answer_and_time_eat_marks_identity(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    acquire(controls, rules.HOUND)
    acquire(controls, rules.TIME)
    action = roll(game, worker, gateway, play="check_sensors", faces=(4, 4), heat=0)
    answer(game, PLAYER, "actor_sensors", options=QUESTIONS[:2] + ("consume_smell",))
    answer(
        game,
        ADMIN,
        "handler_sensors",
        fields={"a1": "Actual danger", "a2": "Actual repair", "a3": "Actual smell of prey"},
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 6)
    cockpit(game, "pilot")
    target = current_ref(state(game), 3)
    action = roll(game, worker, gateway, target=target)
    identity = next(x.id for x in state(game).sheets["2"].identities if not x.marked)
    before = state(game).sheets["2"].heat
    choose(game, PLAYER, "consume_time_eat", "give", identity=identity)
    assert next(x for x in state(game).sheets["2"].identities if x.id == identity).marked
    assert state(game).sheets["2"].heat == before
    assert any(
        x.label == "Just Meat" and x.giver_actor == current_ref(state(game), 2)
        for x in state(game).sheets["3"].tags
    )
    choose(game, PLAYER, "consume_eat", "bite", target_asset=asset(game, 3))
    assert game.inspect(PLAYER, action)["state"] == "complete"


@pytest.mark.parametrize("option", ["regrow", "excrete", "appearance"])
def test_actual_dive_partake_changes_real_assets_or_original_appearance(
    ledger, tmp_path, monkeypatch, option
):
    import json

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    acquire(controls, rules.PARTAKE)
    girl, frame = asset(game, 2), asset(game, 2, "frame")
    with ledger.transaction() as c:
        canon = state(game)
        next(x for x in canon.sheets["2"].assets if x.id == frame).damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_frame_damage", canon)
    cockpit(game, "pilot")
    action = roll(game, worker, gateway, play="dive_deep", heat=0, faces=(4, 5), piloting=True)
    fields = {"girl_asset": girl}
    if option == "regrow":
        fields["frame_assets"] = json.dumps([frame])
    elif option == "excrete":
        fields["new_asset"] = json.dumps(
            dict(
                name="Actual excreted shell",
                description="New actual source-grown shell",
                damaged=False,
                void=True,
            )
        )
    else:
        fields["appearance"] = "My actual newly emerged appearance"
    choose(game, PLAYER, "consume_partake", option, **fields)
    canon = state(game)
    if option == "regrow":
        assert next(x for x in canon.sheets["2"].assets if x.id == girl).damaged
        assert not next(x for x in canon.sheets["2"].assets if x.id == frame).damaged
    elif option == "excrete":
        assert not any(x.id == girl for x in canon.sheets["2"].assets)
        assert any(
            x.name == "Actual excreted shell" and x.family == "frame" and x.void
            for x in canon.sheets["2"].assets
        )
    else:
        assert next(x for x in canon.sheets["2"].assets if x.id == girl).void
        assert rules.records(canon, rules.Partaking)[-1].appearance == fields["appearance"]
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("void_and_unmark_all",),
        text="Actual ordinary communion",
    )
    current = next(x for x in state(game).sheets["2"].assets if not x.void)
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"asset": current.id},
        text="Actual source-owned Void manifestation",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_real_cannibal_target_hierarchy_then_original_voluntary_two_permission_receipt(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    before = state(game).sheets["2"].permissions
    request = controls.propose_permit(
        PLAYER, str(uuid4()), 900, state(game).revision, target, "I choose this actual target"
    )["id"]
    with pytest.raises(WorkflowError):
        controls.review_permit(
            PLAYER,
            str(uuid4()),
            request,
            state(game).revision,
            False,
            "I cannot author the Handler's hierarchy fact",
        )
    controls.review_permit(
        ADMIN,
        str(uuid4()),
        request,
        state(game).revision,
        False,
        "This actual Girl is not my superior",
    )
    data = controls.menu(PLAYER, 900)
    payload = (
        PLAYER,
        "actual-cannibal-payment",
        data["source_sha256"],
        rules.FORMS,
        "I confirm exactly two actual Permissions",
    )
    result = controls.purchase(*payload, hierarchy=request)
    assert controls.purchase(*payload, hierarchy=request) == result
    assert state(game).sheets["2"].permissions == before - 2
    assert rules.permitted(state(game), actor, target)
    assert (
        not is_helpless(state(game), target)
        and next(x for x in state(game).placements if x.actor == target).custody is None
    )
    with pytest.raises(WorkflowError):
        controls.view(OTHER, request)


def test_actual_budget_loss_regrows_original_frame_feature_as_new_component_once(
    ledger, tmp_path, monkeypatch
):
    """Deferred: genuine permanent loss -> real Dive/price -> new source-owned hardware."""
    import asyncio
    import json
    from types import SimpleNamespace

    from test_strain import facts
    from test_strain_service import D6

    from girlframe.discord_adapter import m3_consume as native
    from girlframe.engine import m3_budget_removal as budget
    from girlframe.services.m3_budget_removal import RemovalService
    from girlframe.services.m3_consume_regrowth import prove_regrowth
    from girlframe.services.m3_off_duty import OffDutyService
    from girlframe.services.m3_strain import StrainService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.STARVATION, rules.EAT, *rules.REQUISITIONS, budget.RULE),
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"strain"}}
            )
        }
    )
    acquire(controls, rules.PARTAKE)
    # Initial damage is a fixture fact; the later missing inventory comes only from real Budget.
    with ledger.transaction() as c:
        current = state(game)
        for sheet in current.sheets.values():
            [value for value in sheet.assets if value.family == "frame"][-1].damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.existing_frame_repair_needs", current)
    strain = StrainService(OffDutyService(MissionService(ledger)), dice=D6(6))
    strain.configure(
        ADMIN, str(uuid4()), state(game).revision, "disaster_management", frozenset({"budget"})
    )
    period = strain.periods.begin(ADMIN, str(uuid4()))["id"]
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period,
        1,
        state(game).revision,
        facts(
            no_girl_void=True,
            at_least_half_have_void=False,
            frame_full_or_all_frames_some_repairs=True,
        ),
    )
    while True:
        request = next(
            value
            for value in state(game).strain.requests
            if value.track == "budget" and (value.kind == "endgame" or value.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)
    strain.choose(ADMIN, str(uuid4()), request.id, 1, state(game).revision, 4, endgame=True)
    work = request.id + ":effect"
    removal = RemovalService(ledger)
    for viewer in (PLAYER, OTHER):
        current = state(game)
        actor = current_ref(current, viewer.user_id)
        removal.review_context(
            ADMIN,
            str(uuid4()),
            work,
            actor,
            current.revision,
            inside_frame=False,
            piloting=False,
            in_battle=False,
            opponent=None,
            opponent_known=True,
            account="Actual original outside body and nonbattle Frame",
        )
        sheet = state(game).sheets[str(viewer.user_id)]
        selected_girl = next(value for value in sheet.assets if value.family == "girl")
        selected_frame = next(
            value for value in sheet.assets if value.family == "frame" and value.damaged
        )
        removal.remove(
            viewer,
            str(uuid4()),
            work,
            state(game).revision,
            selected_girl.id,
            selected_frame.id,
            "My actual compulsory Budget loss",
        )
    removal.finish(ADMIN, str(uuid4()), work, state(game).revision)
    original_actor = current_ref(state(game), 2)
    loss = next(value for value in budget.losses(state(game)) if value.actor == original_actor)
    assert not any(value.id == loss.frame_asset.id for value in state(game).sheets["2"].assets)
    girl = asset(game, 2)
    cockpit(game, "pilot")
    action = roll(game, worker, gateway, play="dive_deep", heat=0, faces=(4, 5), piloting=True)
    # Preserve the genuine primary Dive, including actual table authors, before optional Partake.
    if any(value["kind"] == "dive_select" for value in game.choices(PLAYER)):
        answer(
            game,
            PLAYER,
            "dive_select",
            options=("erase_identity_and_table_question",),
            text="I actually let go of this self-definition",
        )
        ordinary = next(
            value for value in state(game).sheets["2"].identities if not value.protected
        )
        answer(
            game,
            PLAYER,
            "dive_effect",
            fields={"identity": ordinary.id},
            text="What holds this Frame together?",
        )
        for viewer in (PLAYER, OTHER, ADMIN):
            answer(
                game,
                viewer,
                "dive_table_answer",
                text="Actual table answer by " + str(viewer.user_id),
            )
    choice = next(value for value in game.choices(PLAYER) if value["kind"] == "consume_partake")
    detail = game.decision(PLAYER, choice["id"])["detail"]
    token = rules.identity("missing-frame", loss.id)
    assert token in detail["regrow_missing"] and token in dict(detail["frame_assets"])
    before = state(game)
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(
                options=("regrow",),
                fields={"girl_asset": girl, "frame_assets": '["unproved-former-inventory"]'},
                text="This cannot spend the Girl cost without actual original hardware evidence",
            ),
        )
    assert state(game) == before
    request = (
        PLAYER,
        "actual-budget-partake-regrowth",
        choice["id"],
        choice["revision"],
        ChoiceAnswer(
            options=("regrow",),
            fields={"girl_asset": girl, "frame_assets": json.dumps([token])},
            text="I pay actual Girl damage to regrow my actual missing Frame feature",
        ),
    )
    game.respond(*request)
    game.respond(*request)
    born = state(game)
    regrown = next(
        value for value in rules.records(born, rules.RegrownFrame) if value.loss == loss.id
    )
    assert regrown.original == loss.frame_asset and regrown.frame == loss.frame
    assert regrown.component.id != loss.frame_asset.id
    assert regrown.component.void == loss.frame_asset.void and not regrown.component.damaged
    assert regrown.component in born.sheets["2"].assets
    assert next(value for value in born.sheets["2"].assets if value.id == girl).damaged
    assert len(born.sheets["2"].assets) == len(before.sheets["2"].assets) + 1
    assert (
        born.neural_connections == before.neural_connections
        and born.placements == before.placements
    )
    with ledger.engine.connect() as c:
        assert prove_regrowth(game, c, born, regrown.id) == regrown
    assert controls.view(PLAYER, regrown.id)["type"] == "regrowth"
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, regrown.id)
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    # A later genuine Dive cannot consume the same immutable loss a second time.
    later = roll(game, worker, gateway, play="dive_deep", heat=0, faces=(4, 5), piloting=True)
    if any(value["kind"] == "dive_select" for value in game.choices(PLAYER)):
        answer(
            game,
            PLAYER,
            "dive_select",
            options=("erase_identity_and_table_question",),
            text="A later actual Dive",
        )
        ordinary = next(
            value for value in state(game).sheets["2"].identities if not value.protected
        )
        answer(
            game, PLAYER, "dive_effect", fields={"identity": ordinary.id}, text="What changes next?"
        )
        for viewer in (PLAYER, OTHER, ADMIN):
            answer(
                game,
                viewer,
                "dive_table_answer",
                text="Actual later answer by " + str(viewer.user_id),
            )
    later_choice = next(
        value for value in game.choices(PLAYER) if value["kind"] == "consume_partake"
    )
    assert token not in game.decision(PLAYER, later_choice["id"])["detail"]["regrow_missing"]
    choose(game, PLAYER, "consume_partake", "pass")
    assert game.inspect(PLAYER, later)["state"] == "complete"
    captured = []
    monkeypatch.setattr(native, "viewer_from_interaction", lambda interaction: PLAYER)

    async def reply(interaction, text, view=None):
        captured.append(view)

    monkeypatch.setattr(native, "reply", reply)
    asyncio.run(
        native.open_consume(
            SimpleNamespace(user=SimpleNamespace(id=2), channel_id=999), controls, regrown.id
        )
    )
    assert native.clean(loss.frame_asset.name) in "".join(page.body for page in captured[0].pages)
    assert (
        len(
            [
                value
                for value in rules.records(state(game), rules.RegrownFrame)
                if value.loss == loss.id
            ]
        )
        == 1
    )
