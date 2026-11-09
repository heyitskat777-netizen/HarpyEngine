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


# Deferred final-P1 normal; not run during the Sprite source adapter assignment.
def test_actual_native_eat_sprite_leap_pays_real_asset_then_feeds_once_without_retargeted_receipt(
    ledger, tmp_path, monkeypatch
):
    import asyncio
    import json

    from test_mission_ui import current
    from test_world import gorgon

    from girlframe.discord_adapter.m3_consume import open_choice
    from girlframe.discord_adapter.m3_sprite import open_sprite
    from girlframe.engine.m3_world import update
    from girlframe.services.m3_consume import prove_resolution
    from girlframe.services.m3_sprite import SpriteService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    # Existing physical-Sprite source fixture: genuine World bodies/Assets, not a
    # public new-Sprite producer. Its visibility and own decision are real services.
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            gorgons=canon.world.gorgons
            + (gorgon("sprite", "actual-eat-interceptor", sprite_group=True),),
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_Sprite_body", canon)
    WorldService(MissionService(ledger)).reveal(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "actual-eat-interceptor",
        "The actual Sprite group is physically encountered beside the target",
    )
    cockpit(game, "pilot")
    before = state(game)
    intended_asset = asset(game, 3)
    action = roll(game, worker, gateway, target=target, piloting=True)
    receipt = game.inspect(PLAYER, action)["receipt"]
    heat_after_roll = state(game).sheets["2"].heat

    async def bite():
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "consume_eat")
        opened = current(2, int(uuid4().int % 1000000000))
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, game.decision(PLAYER, row["id"]))
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 99801))
        form.values.update(
            option=("bite",),
            target_asset=(intended_asset,),
            account="I actually bite; this is still my original intended target",
        )
        submitted = current(2, int(uuid4().int % 1000000000))
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(bite())
    consumed = next(x for x in rules.records(state(game), rules.Consumption) if x.session == action)
    assert consumed.target == target and consumed.option == "bite"
    assert controls.view(PLAYER, consumed.id)["pending_sprite"]
    assert rules.hunger(state(game), actor) == rules.hunger(before, actor) == "Gnawing"
    assert not next(x for x in state(game).sheets["3"].assets if x.id == intended_asset).damaged
    svc = SpriteService(ledger)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "battle_sprite_intercept")
    identity = json.loads(row["body_json"])["work_id"]
    offered = svc.get(ADMIN, identity)
    option = offered["options"][0]
    with pytest.raises(WorkflowError):
        svc.get(OTHER, identity)

    async def leap():
        opened = current(1, int(uuid4().int % 1000000000))
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_sprite(opened, svc, identity)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2, 99802))
        form.values.update(option=("0",), account="My actual Sprite leaps in to take this blow")
        submitted = current(1, int(uuid4().int % 1000000000))
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        return str(submitted.id)

    key = asyncio.run(leap())
    after = state(game)
    original_sprite = next(x for x in after.world.gorgons if x.id == "actual-eat-interceptor")
    assert next(x for x in original_sprite.assets if x.id == option["asset"]).damaged
    assert not next(x for x in after.sheets["3"].assets if x.id == intended_asset).damaged
    assert rules.hunger(after, actor) == "Quiet"
    assert after.sheets["2"].heat == heat_after_roll and game.dice.calls == 1
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert game.inspect(PLAYER, action)["state"] == "complete"
    saved = controls.view(PLAYER, consumed.id)
    assert saved["source"]["target"] == target.model_dump(mode="json")
    assert saved["resolution"]["recipient"] == option["actor"]
    assert saved["resolution"]["feeding_event"] and not saved["pending_sprite"]
    with ledger.engine.connect() as c:
        assert prove_resolution(game, c, after, saved["resolution"]["id"]).option == "bite"
    result = svc.respond(
        ADMIN,
        key,
        identity,
        offered["revision"],
        offered["game_revision"],
        ActorRef.model_validate(option["actor"]),
        option["asset"],
        "My actual Sprite leaps in to take this blow",
    )
    assert result["id"] == identity
    assert state(game).revision == after.revision
    tick(worker, gateway, 6)


# Deferred P1 normal; no pytest during the paid-cap-loss source adapter assignment.
def test_actual_paid_cap_installment_loss_native_regrowth_preserves_receipt_and_new_birth(
    ledger, tmp_path, monkeypatch
):
    import asyncio
    import json

    from test_mission_ui import current

    from girlframe.discord_adapter.m3_consume import open_choice
    from girlframe.engine.m3_assets import counts_toward_limit
    from girlframe.engine.m3_requisition_state import Installation
    from girlframe.services.m3_consume_regrowth import prove_regrowth
    from girlframe.services.m3_frame_asset_losses import installment_loss
    from girlframe.services.m3_requisitions import RequisitionService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    acquire(controls, rules.PARTAKE)
    actor = current_ref(state(game), 2)
    old = next(x for x in state(game).sheets["2"].assets if x.family == "frame")
    purchase = RequisitionService(game)
    # Reach this actual Frame's real cap through paid additions, then explicitly
    # replace the old component in one further genuine paid installation.
    index = 0
    while True:
        quote = purchase.view(PLAYER)
        sheet = state(game).sheets["2"]
        at_cap = (
            sum(
                counts_toward_limit(sheet, value)
                for value in sheet.assets
                if value.family == "frame"
            )
            >= quote["frame_capacity"]
        )
        choice = Installation(
            name="Actual paid plate " + str(index),
            description="Actual purchased permanent hardware " + str(index),
            replace=old.id if at_cap else None,
            account="I actually install this component on my original Frame",
            trigger_confirmed=True,
        )
        args = PLAYER, str(uuid4()), actor, quote["source_sha256"], choice
        paid = purchase.buy(*args)
        assert purchase.buy(*args) == paid
        if at_cap:
            break
        index += 1
    receipt = next(
        x
        for x in state(game).requisitions
        if x.kind == "asset_installment" and x.installation.replace == old.id
    )
    assert receipt.actor == actor and receipt.installation.replace == old.id
    assert not any(x.id == old.id for x in state(game).sheets["2"].assets)
    frame = rules.frame(state(game), actor)
    with ledger.engine.connect() as c:
        loss = installment_loss(game, c, state(game), receipt)
        assert loss is not None
        assert loss.asset == old and loss.source_kind == "asset_installment"
        assert loss.frame == frame
    girl = asset(game, 2)
    cockpit(game, "pilot")
    action = roll(game, worker, gateway, play="dive_deep", heat=0, faces=(4, 5), piloting=True)
    if any(x["kind"] == "dive_select" for x in game.choices(PLAYER)):
        answer(
            game,
            PLAYER,
            "dive_select",
            options=("erase_identity_and_table_question",),
            text="My actual primary Dive before the optional regrowth",
        )
        ordinary = next(x for x in state(game).sheets["2"].identities if not x.protected)
        answer(
            game,
            PLAYER,
            "dive_effect",
            fields={"identity": ordinary.id},
            text="What does this original Frame need?",
        )
        for viewer in (PLAYER, OTHER, ADMIN):
            answer(game, viewer, "dive_table_answer", text="My own actual table answer")
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "consume_partake")
    detail = game.decision(PLAYER, row["id"])["detail"]
    token = rules.identity("missing-frame-installment", receipt.id)
    assert token in detail["regrow_missing"]
    replacement = detail["regrow_replacements"][0][0]
    before = state(game)
    raw_receipt = game.inspect(PLAYER, action)["receipt"]

    async def native():
        opened = current(2, int(uuid4().int % 1000000000))
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, game.decision(PLAYER, row["id"]))
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 99810))
        form.values.update(
            option=("regrow",),
            girl_asset=(girl,),
            frame_assets=(token,),
            account="I pay actual Girl damage to regrow my paid-removed feature",
        )
        select = current(2, int(uuid4().int % 1000000000))
        select.channel_id = 900
        await form.confirm.callback(select)
        assert form.completed, select.edit_original_response.call_args_list
        space = select.edit_original_response.call_args.kwargs["view"]
        space.values["replacement_0"] = (replacement,)
        submitted = current(2, int(uuid4().int % 1000000000))
        submitted.channel_id = 900
        await space.confirm.callback(submitted)
        assert space.completed, submitted.edit_original_response.call_args_list
        return str(submitted.id)

    key = asyncio.run(native())
    born = state(game)
    game.respond(
        PLAYER,
        key,
        row["id"],
        row["revision"],
        ChoiceAnswer(
            options=("regrow",),
            fields={
                "girl_asset": girl,
                "frame_assets": json.dumps([token]),
                "regrow_replacements": json.dumps({token: replacement}),
            },
            text="I pay actual Girl damage to regrow my paid-removed feature",
        ),
    )
    assert state(game).revision == born.revision
    after = state(game)
    regrown = next(
        x
        for x in rules.records(after, rules.RegrownFrame)
        if x.loss_kind == "asset_installment" and x.loss == receipt.id
    )
    assert regrown.original == old and regrown.frame == receipt.frame_instance == frame
    assert regrown.loss_event == receipt.source_event
    assert regrown.component.id != old.id and regrown.component.void == old.void
    assert not regrown.component.damaged and regrown.component in after.sheets["2"].assets
    assert regrown.replacement == replacement
    assert not any(x.id in (old.id, replacement) for x in after.sheets["2"].assets)
    assert next(x for x in after.sheets["2"].assets if x.id == girl).damaged
    assert after.sheets["2"].permissions == before.sheets["2"].permissions
    assert after.neural_connections == before.neural_connections
    assert after.placements == before.placements
    assert receipt in after.requisitions
    assert game.inspect(PLAYER, action)["receipt"] == raw_receipt
    with ledger.engine.connect() as c:
        assert prove_regrowth(game, c, after, regrown.id) == regrown
        from girlframe.services.m3_consume_regrowth import _selections

        assert token not in {x.token for x in _selections(game, c, after, actor)}
    assert controls.view(PLAYER, regrown.id)["type"] == "regrowth"
    with pytest.raises(WorkflowError):
        controls.view(OTHER, regrown.id)
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"


# Deferred accepted-offer provider normal; root runs the sole minimal node after freeze.
def test_actual_accepted_defeat_component_loss_then_native_same_frame_regrowth(
    ledger, tmp_path, monkeypatch
):
    import asyncio
    import json

    from test_mission_ui import current

    from girlframe.discord_adapter.m3_consume import open_choice
    from girlframe.services.m3_consume_regrowth import prove_regrowth
    from girlframe.services.m3_frame_asset_losses import defeat_alternative_losses

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    acquire(controls, rules.PARTAKE)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            ),
        }
    )
    with ledger.transaction() as c:
        canon = state(game)
        frames = [x for x in canon.sheets["2"].assets if x.family == "frame"]
        for value in frames[1:]:
            value.damaged = True
        last = frames[0].id
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_Frame_damage", canon)
    cockpit(game, "pilot")
    actor = current_ref(state(game), 2)
    frame = rules.frame(state(game), actor)
    game.dice.faces = (1, 1)
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            piloting=True,
            context="Actual confrontation while piloting my original Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, parent)["state"] in ("acquiring", "ready_to_roll"):
        game.roll(PLAYER, str(uuid4()), parent)
    pass_tags(game)
    answer(game, OTHER, "beneath_select", options=("damage",), text="My actual counterattack")
    answer(game, PLAYER, "beneath_details", denied=(last,))
    assert any(x["kind"] == "beneath_defeat" for x in game.choices(PLAYER))
    lost = next(x for x in state(game).sheets["2"].assets if x.id == last)
    assert lost.damaged
    game.dice.faces = (1, 1)
    defeat = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            parent=parent,
            heat=0,
            piloting=True,
            context="Actual required Defeat from the real last-Asset counterattack",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, defeat)["state"] in ("acquiring", "ready_to_roll"):
        game.roll(PLAYER, str(uuid4()), defeat)
    pass_tags(game)
    defeat_receipt = game.inspect(PLAYER, defeat)["receipt"]
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("handler_ruinous_alternative",),
        text="I ask my actual Handler for the printed alternative",
    )
    answer(
        game,
        ADMIN,
        "defeat_alternative",
        flag=True,
        fields={"assets": last, "frame_context": "inside"},
        text="My actual equally ruinous offer permanently removes that named Frame component",
    )
    assert any(x.id == last for x in state(game).sheets["2"].assets)
    offered = next(x for x in game.choices(PLAYER) if x["kind"] == "defeat_accept_alternative")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), offered["id"], offered["revision"], ChoiceAnswer(flag=True)
        )
    answer(
        game,
        PLAYER,
        "defeat_accept_alternative",
        flag=True,
        text="My own actual acceptance of that precise offered loss",
    )
    assert not any(x.id == last for x in state(game).sheets["2"].assets)
    assert rules.frame(state(game), actor) == frame and not state(game).sheets["2"].frame_scrapped
    assert game.inspect(PLAYER, defeat)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert game.inspect(PLAYER, defeat)["receipt"] == defeat_receipt
    with ledger.engine.connect() as c:
        loss = next(
            x for x in defeat_alternative_losses(game, c, state(game), actor) if x.asset.id == last
        )
        assert loss.source_kind == "defeat_alternative" and loss.asset == lost
    tick(worker, gateway, 6)
    girl = asset(game, 2)
    dive = roll(game, worker, gateway, play="dive_deep", heat=0, faces=(4, 5), piloting=True)
    if any(x["kind"] == "dive_select" for x in game.choices(PLAYER)):
        answer(
            game,
            PLAYER,
            "dive_select",
            options=("erase_identity_and_table_question",),
            text="My actual primary Dive after the accepted loss",
        )
        ordinary = next(x for x in state(game).sheets["2"].identities if not x.protected)
        answer(
            game,
            PLAYER,
            "dive_effect",
            fields={"identity": ordinary.id},
            text="What does this same Frame remember?",
        )
        for viewer in (PLAYER, OTHER, ADMIN):
            answer(game, viewer, "dive_table_answer", text="My actual table answer")
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "consume_partake")
    token = rules.identity("missing-frame-defeat", loss.id)
    assert token in game.decision(PLAYER, row["id"])["detail"]["regrow_missing"]
    before = state(game)
    raw_dive, calls = game.inspect(PLAYER, dive)["receipt"], game.dice.calls

    async def native():
        opened = current(2, int(uuid4().int % 1000000000))
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, game.decision(PLAYER, row["id"]))
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 99820))
        form.values.update(
            option=("regrow",),
            girl_asset=(girl,),
            frame_assets=(token,),
            account="My actual Girl cost regrows this source-proved missing feature",
        )
        submitted = current(2, int(uuid4().int % 1000000000))
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        return str(submitted.id)

    key = asyncio.run(native())
    born = state(game)
    game.respond(
        PLAYER,
        key,
        row["id"],
        row["revision"],
        ChoiceAnswer(
            options=("regrow",),
            fields={"girl_asset": girl, "frame_assets": json.dumps([token])},
            text="My actual Girl cost regrows this source-proved missing feature",
        ),
    )
    assert state(game).revision == born.revision
    regrown = next(
        x
        for x in rules.records(born, rules.RegrownFrame)
        if x.loss_kind == "defeat_alternative" and x.loss == loss.id
    )
    assert regrown.original == lost and regrown.frame == frame
    assert regrown.component.id != last and not regrown.component.damaged
    assert regrown.component.void == lost.void and regrown.component in born.sheets["2"].assets
    assert next(x for x in born.sheets["2"].assets if x.id == girl).damaged
    assert (
        born.neural_connections == before.neural_connections
        and born.placements == before.placements
    )
    assert game.dice.calls == calls and game.inspect(PLAYER, dive)["receipt"] == raw_dive
    assert game.inspect(PLAYER, defeat)["receipt"] == defeat_receipt
    with ledger.engine.connect() as c:
        assert prove_regrowth(game, c, born, regrown.id) == regrown
        from girlframe.services.m3_consume_regrowth import _selections

        assert token not in {x.token for x in _selections(game, c, born, actor)}
    assert controls.view(PLAYER, regrown.id)["type"] == "regrowth"
    with pytest.raises(WorkflowError):
        controls.view(OTHER, regrown.id)
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, dive)["state"] == "complete"


def _actual_cap_defeat_void_context(ledger, tmp_path, monkeypatch):
    """New source consumers share genuine paid capacity and required-Defeat setup."""
    from girlframe.engine.m3_assets import counts_toward_limit
    from girlframe.engine.m3_requisition_state import Installation
    from girlframe.services.m3_requisitions import RequisitionService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    acquire(controls, rules.PARTAKE)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    actor = current_ref(state(game), 2)
    purchase = RequisitionService(game)
    index = 0
    while True:
        quote = purchase.view(PLAYER)
        sheet = state(game).sheets["2"]
        if (
            sum(counts_toward_limit(sheet, x) for x in sheet.assets if x.family == "frame")
            >= quote["frame_capacity"]
        ):
            break
        purchase.buy(
            PLAYER,
            str(uuid4()),
            actor,
            quote["source_sha256"],
            Installation(
                name="Actual spare cap plate " + str(index),
                description="Actual paid original Frame part",
                account="I actually install this paid component",
                trigger_confirmed=True,
            ),
        )
        index += 1
    lost = next(
        x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.intrinsic
    )
    with ledger.transaction() as c:
        damaged = state(game)
        for value in damaged.sheets["2"].assets:
            if value.family == "frame" and value.id != lost.id:
                value.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_cap_frame_damage", damaged)
    cockpit(game, "pilot")
    game.dice.faces = (1, 1)
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            piloting=True,
            context="Actual confrontation while piloting my original Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, parent)["state"] in ("acquiring", "ready_to_roll"):
        game.roll(PLAYER, str(uuid4()), parent)
    pass_tags(game)
    answer(game, OTHER, "beneath_select", options=("damage",), text="My actual counterattack")
    answer(game, PLAYER, "beneath_details", denied=(lost.id,))
    game.dice.faces = (3, 3)
    defeat = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            parent=parent,
            heat=0,
            piloting=True,
            trigger_confirmed=True,
            context="Actual required Defeat after the last working Frame Asset is damaged",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, defeat)["state"] in ("acquiring", "ready_to_roll"):
        game.roll(PLAYER, str(uuid4()), defeat)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("new_girl_and_frame_void_assets_heat4",),
        fields={
            "girl_name": "Actual emergency blood adaptation",
            "girl_description": "Actual new Void-corrupted Girl feature from Defeat",
            "frame_name": "Actual emergency Void plate",
            "frame_description": "Actual new Frame blood-grown component at the cap",
            "frame_replace": lost.id,
        },
        text="I choose the actual printed new-Void survival option",
    )
    assert game.inspect(PLAYER, defeat)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    actual_lost = lost.model_copy(update={"damaged": True})
    assert not any(x.id == lost.id for x in state(game).sheets["2"].assets)
    tick(worker, gateway, 6)
    return game, worker, gateway, controls, actor, actual_lost, defeat


def _actual_next_partake(game, worker, gateway):
    dive = roll(game, worker, gateway, play="dive_deep", heat=0, faces=(4, 5), piloting=True)
    if any(x["kind"] == "dive_select" for x in game.choices(PLAYER)):
        answer(
            game,
            PLAYER,
            "dive_select",
            options=("erase_identity_and_table_question",),
            text="Actual communion before the actual source-owned Partake",
        )
        identity = next(x for x in state(game).sheets["2"].identities if not x.protected)
        answer(
            game,
            PLAYER,
            "dive_effect",
            fields={"identity": identity.id},
            text="What does this original Frame remember?",
        )
        for viewer in (PLAYER, OTHER, ADMIN):
            answer(game, viewer, "dive_table_answer", text="My own actual table answer")
    return dive, next(x for x in game.choices(PLAYER) if x["kind"] == "consume_partake")


def _native_actual_cap_partake(game, row, *, girl, token=None, replacement=None, excrete=None):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m3_consume import open_choice

    async def perform():
        opened = current(2, uuid4().int % 1000000000)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, game.decision(PLAYER, row["id"]))
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, uuid4().int % 1000000000))
        form.values.update(
            option=("excrete" if excrete else "regrow",),
            girl_asset=(girl,),
            account="My actual selected Girl cost and current Frame component exchange",
        )
        if excrete:
            form.values.update(
                replace_frame=(replacement,),
                new_name=excrete,
                new_description="Actual source-excreted Void hardware",
            )
        else:
            form.values["frame_assets"] = (token,)
        submitted = current(2, uuid4().int % 1000000000)
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        if not excrete and replacement:
            space = submitted.edit_original_response.call_args.kwargs["view"]
            space.values["replacement_0"] = (replacement,)
            final = current(2, uuid4().int % 1000000000)
            final.channel_id = 900
            await space.confirm.callback(final)
            assert space.completed, final.edit_original_response.call_args_list
            before = state(game)
            await space.confirm.callback(final)
        else:
            before = state(game)
            await form.confirm.callback(submitted)
        assert state(game) == before

    asyncio.run(perform())


def test_actual_new_void_defeat_cap_loss_then_native_same_frame_regrowth(
    ledger, tmp_path, monkeypatch
):
    from girlframe.services.m3_consume_regrowth import _selections, prove_regrowth
    from girlframe.services.m3_frame_asset_losses import defeat_void_losses

    game, worker, gateway, controls, actor, lost, defeat = _actual_cap_defeat_void_context(
        ledger, tmp_path, monkeypatch
    )
    frame = rules.frame(state(game), actor)
    receipt = game.inspect(PLAYER, defeat)["receipt"]
    with ledger.engine.connect() as c:
        loss = next(
            x for x in defeat_void_losses(game, c, state(game), actor) if x.asset.id == lost.id
        )
        assert loss.asset == lost and loss.frame == frame
    dive, row = _actual_next_partake(game, worker, gateway)
    token = rules.identity("missing-frame-defeat-new-void", loss.id)
    assert token in game.decision(PLAYER, row["id"])["detail"]["regrow_missing"]
    replacement = next(
        x.id
        for x in state(game).sheets["2"].assets
        if x.family == "frame" and not x.void and not x.intrinsic
    )
    girl = asset(game, 2)
    calls = game.dice.calls
    _native_actual_cap_partake(game, row, girl=girl, token=token, replacement=replacement)
    born = state(game)
    regrown = next(
        x
        for x in rules.records(born, rules.RegrownFrame)
        if x.loss_kind == "defeat_new_void" and x.loss == loss.id
    )
    assert regrown.original == lost and regrown.component.id != lost.id and regrown.frame == frame
    assert regrown.component.void == lost.void and not regrown.component.damaged
    assert regrown.component in born.sheets["2"].assets
    assert next(x for x in born.sheets["2"].assets if x.id == girl).damaged
    with ledger.engine.connect() as c:
        assert prove_regrowth(game, c, born, regrown.id) == regrown
        assert token not in {x.token for x in _selections(game, c, born, actor)}
    assert controls.view(PLAYER, regrown.id)["type"] == "regrowth"
    with pytest.raises(WorkflowError):
        controls.view(OTHER, regrown.id)
    assert game.inspect(PLAYER, defeat)["receipt"] == receipt and game.dice.calls == calls
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, dive)["state"] == "complete"


def test_actual_partake_excretion_then_regrowth_cap_losses_have_prior_sources_only(
    ledger, tmp_path, monkeypatch
):
    from girlframe.services.m3_consume_regrowth import _selections, prove_regrowth
    from girlframe.services.m3_frame_asset_losses import partake_losses

    # The real new-Void Defeat gives a third Girl Asset: excretion +two real damage costs.
    game, worker, gateway, controls, actor, _, _ = _actual_cap_defeat_void_context(
        ledger, tmp_path, monkeypatch
    )
    frame = rules.frame(state(game), actor)
    first, row = _actual_next_partake(game, worker, gateway)
    excreted_old = next(
        x
        for x in state(game).sheets["2"].assets
        if x.family == "frame" and not x.void and not x.intrinsic
    )
    eaten = asset(game, 2)
    _native_actual_cap_partake(
        game,
        row,
        girl=eaten,
        replacement=excreted_old.id,
        excrete="Actual source-grown excreted shell",
    )
    assert not any(x.id == eaten for x in state(game).sheets["2"].assets)
    with ledger.engine.connect() as c:
        loss = next(
            x
            for x in partake_losses(game, c, state(game), actor)
            if x.source_kind == "partake_excrete" and x.asset.id == excreted_old.id
        )
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, first)["state"] == "complete"
    second, row = _actual_next_partake(game, worker, gateway)
    token = rules.identity("missing-frame-partake-excrete", loss.id)
    replacement = next(
        x
        for x in state(game).sheets["2"].assets
        if x.family == "frame" and not x.void and not x.intrinsic
    )
    _native_actual_cap_partake(
        game, row, girl=asset(game, 2), token=token, replacement=replacement.id
    )
    grown = next(
        x
        for x in rules.records(state(game), rules.RegrownFrame)
        if x.loss_kind == "partake_excrete" and x.loss == loss.id
    )
    with ledger.engine.connect() as c:
        assert prove_regrowth(game, c, state(game), grown.id) == grown
        displaced = next(
            x
            for x in partake_losses(game, c, state(game), actor)
            if x.source_kind == "partake_regrowth" and x.asset.id == replacement.id
        )
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, second)["state"] == "complete"
    third, row = _actual_next_partake(game, worker, gateway)
    next_token = rules.identity("missing-frame-partake-regrowth", displaced.id)
    assert next_token in game.decision(PLAYER, row["id"])["detail"]["regrow_missing"]
    final_replacement = next(
        x.id
        for x in state(game).sheets["2"].assets
        if x.family == "frame" and not x.void and not x.intrinsic and x.id != grown.component.id
    )
    _native_actual_cap_partake(
        game, row, girl=asset(game, 2), token=next_token, replacement=final_replacement
    )
    final = state(game)
    last = next(
        x
        for x in rules.records(final, rules.RegrownFrame)
        if x.loss_kind == "partake_regrowth" and x.loss == displaced.id
    )
    assert last.original == replacement and last.frame == frame
    assert last.component.id != replacement.id and last.component in final.sheets["2"].assets
    with ledger.engine.connect() as c:
        assert prove_regrowth(game, c, final, last.id) == last
        assert next_token not in {x.token for x in _selections(game, c, final, actor)}
        assert token not in {x.token for x in _selections(game, c, final, actor)}
    assert controls.view(PLAYER, last.id)["type"] == "regrowth"
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, third)["state"] == "complete"


def _elective_regrowth_ready(ledger, tmp_path, monkeypatch):
    from girlframe.engine.m3_assets import counts_toward_limit
    from girlframe.engine.m3_requisition_state import Installation
    from girlframe.services.m3_requisitions import RequisitionService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    acquire(controls, rules.PARTAKE)
    actor = current_ref(state(game), 2)
    original = next(x for x in state(game).sheets["2"].assets if x.family == "frame")
    purchases = RequisitionService(game)
    index = 0
    while True:
        data = purchases.view(PLAYER)
        sheet = state(game).sheets["2"]
        if (
            sum(counts_toward_limit(sheet, x) for x in sheet.assets if x.family == "frame")
            >= data["frame_capacity"]
        ):
            break
        purchases.buy(
            PLAYER,
            str(uuid4()),
            actor,
            data["source_sha256"],
            Installation(
                name="Actual elective spare " + str(index),
                description="Actual permanently installed paid source hardware",
                account="I actually pay for and install this original Frame component",
                trigger_confirmed=True,
            ),
        )
        index += 1
    return game, worker, gateway, controls, actor, original


def _elective_dive(game, worker, gateway):
    """Use actual worker progression; a missing committed receipt must not be concealed."""
    game.dice.faces = (4, 5)
    heat = state(game).sheets["2"].heat
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            heat=heat if heat >= 5 else 0,
            piloting=True,
            context="I genuinely commune with my original current Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, identity)["receipt"]
    pass_tags(game)
    return identity


def _elective_partake(game, worker, gateway):
    action = _elective_dive(game, worker, gateway)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("erase_identity_and_table_question",),
        text="My actual original communion before optional Partake",
    )
    ordinary = next(
        x for x in state(game).sheets["2"].identities if not x.protected and not x.paired
    )
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"identity": ordinary.id},
        text="What does this actual original Frame need now?",
    )
    for viewer in (PLAYER, OTHER, ADMIN):
        if any(x["kind"] == "dive_table_answer" for x in game.choices(viewer)):
            answer(game, viewer, "dive_table_answer", text="My own actual table answer")
    return action, next(x for x in game.choices(PLAYER) if x["kind"] == "consume_partake")


def test_actual_supply_delivery_cap_loss_survives_true_expiry_then_native_partake_regrowth(
    ledger, tmp_path, monkeypatch
):
    """Deferred: a true temporary delivery displaces one permanent component, never free supply."""
    from test_supply_drop import acquire as buy_supply
    from test_supply_drop import launch, native_receive, propose, settle

    from girlframe.engine import m3_handler_ordinary as ordinary
    from girlframe.engine import m3_supply_drop as supply
    from girlframe.services.m3_consume_regrowth import _selections, prove_regrowth
    from girlframe.services.m3_frame_asset_losses import supply_drop_losses
    from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService
    from girlframe.services.m3_handler_pr import HandlerPRService
    from girlframe.services.m3_supply_drop import SupplyDropService

    game, worker, gateway, controls, actor, old = _elective_regrowth_ready(
        ledger, tmp_path, monkeypatch
    )
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(ordinary.RULE, supply.RULE, rules.STARVATION, rules.EAT, *rules.REQUISITIONS),
    )
    HandlerOrdinaryService(ledger).record_session(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "Actual supply source Session",
        "The original Handler genuinely begins this Session",
    )
    public = HandlerPRService(ledger)
    event = public.plan(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "Actual supply Foundation feature",
        "The original Girl participates in a real feature",
        (actor,),
    )["id"]
    public.activity(
        ADMIN,
        str(uuid4()),
        event,
        state(game).revision,
        "I actually host this Foundation feature",
        hosting=True,
    )
    public.activity(
        PLAYER,
        str(uuid4()),
        event,
        state(game).revision,
        "My actual original Girl participates in this feature",
    )
    public.submit_result(
        ADMIN,
        str(uuid4()),
        event,
        state(game).revision,
        "The original participants actually perform the planned feature",
    )
    award = public.resolve(
        ADMIN,
        str(uuid4()),
        event,
        state(game).revision,
        True,
        "The genuine adjudicator records the actual successful result",
    )["award"]
    delivery = SupplyDropService(ledger)
    buy_supply(delivery, award)
    missions = MissionService(ledger)
    mission = launch(missions)
    identity = propose(delivery, game, mission)
    native_receive(delivery, identity, replace=old.id, number=991700)
    use = next(x for x in supply.uses(state(game)) if x.id == identity)
    assert use.replacement == old.id and use.phase == "delivered"
    assert not any(x.id == old.id for x in state(game).sheets["2"].assets)
    with ledger.engine.connect() as c:
        loss = next(x for x in supply_drop_losses(game, c, state(game), actor) if x.id == identity)
        assert loss.asset == old and loss.event == use.effect_event
    # Record the real Handler-owned mission outcome first. This actual lifetime
    # operation expires its delivered equipment and creates the genuine owed work.
    active = missions.get(ADMIN, mission)["mission"]
    missions.end(ADMIN, str(uuid4()), mission, active["revision"], True)
    settle(missions, game, mission)
    expired = next(x for x in supply.uses(state(game)) if x.id == identity)
    assert expired.phase == "expired" and expired.expiry_event != use.effect_event
    assert not any(x.id in (old.id, use.asset) for x in state(game).sheets["2"].assets)
    cockpit(game, "pilot")
    action, row = _elective_partake(game, worker, gateway)
    detail = game.decision(PLAYER, row["id"])["detail"]
    token = rules.identity("missing-frame-supply-drop-cap", identity)
    assert token in detail["regrow_missing"] and use.asset not in detail["regrow_missing"]
    before, calls = state(game), game.dice.calls
    receipt = game.inspect(PLAYER, action)["receipt"]
    girl = next(x.id for x in before.sheets["2"].assets if x.family == "girl" and not x.damaged)
    _native_actual_cap_partake(game, row, girl=girl, token=token)
    final = state(game)
    component = next(
        x
        for x in rules.records(final, rules.RegrownFrame)
        if x.loss_kind == "supply_drop_cap" and x.loss == identity
    )
    assert component.original == old and component.loss_event == use.effect_event
    assert component.component.id not in (old.id, use.asset) and not component.component.damaged
    assert next(x for x in final.sheets["2"].assets if x.id == girl).damaged
    assert not any(x.id in (old.id, use.asset) for x in final.sheets["2"].assets)
    assert supply.uses(final) == supply.uses(before)
    assert game.dice.calls == calls and game.inspect(PLAYER, action)["receipt"] == receipt
    with ledger.engine.connect() as c:
        assert prove_regrowth(game, c, final, component.id) == component
        assert token not in {x.token for x in _selections(game, c, final, actor)}
    with pytest.raises(WorkflowError):
        controls.view(OTHER, component.id)
    assert controls.view(PLAYER, component.id)["type"] == "regrowth"
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_actual_paid_sup_dive_cap_loss_then_native_partake_regrowth_keeps_void_birth(
    ledger, tmp_path, monkeypatch
):
    """Deferred: only this true owned Dive gain authorizes its displaced component."""
    import asyncio

    from test_mission_ui import current
    from test_sup import purchase as buy_sup

    from girlframe.discord_adapter.m3_dive import open_dive
    from girlframe.discord_adapter.m3_sup import GROW
    from girlframe.engine import m3_sup as sup
    from girlframe.services.m3_consume_regrowth import _selections, prove_regrowth
    from girlframe.services.m3_frame_asset_losses import sup_dive_losses

    game, worker, gateway, controls, actor, old = _elective_regrowth_ready(
        ledger, tmp_path, monkeypatch
    )
    paid = buy_sup(game, tmp_path, monkeypatch)
    cockpit(game, "pilot")
    growth_action = _elective_dive(game, worker, gateway)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("void_and_unmark_all",),
        text="I choose my actual Frame's printed Void gain",
    )
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_effect")
    before = state(game)

    async def grow():
        opened = current(2, 991800)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_dive(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(asset=(GROW,))
        select = current(2, 991801)
        select.channel_id = 900
        await form.confirm.callback(select)
        assert form.completed, select.edit_original_response.call_args_list
        actual = select.edit_original_response.call_args.kwargs["view"]
        actual.values.update(
            name="Actual Sup-grown Void plate",
            family=("frame",),
            replace=(old.id,),
            description="PRIVATE_SUP actual new already-Void organic hardware",
        )
        submitted = current(2, 991802)
        submitted.channel_id = 900
        await actual.confirm.callback(submitted)
        assert actual.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await actual.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(grow())
    grown = sup.growths(state(game))[-1]
    assert grown.purchase == paid.id and grown.choice.replace == old.id
    assert grown.action == growth_action and grown.frame == rules.frame(state(game), actor)
    assert not any(x.id == old.id for x in state(game).sheets["2"].assets)
    assert next(x for x in state(game).sheets["2"].assets if x.id == grown.asset).void
    assert state(game).sheets["2"].permissions == before.sheets["2"].permissions
    with ledger.engine.connect() as c:
        loss = next(x for x in sup_dive_losses(game, c, state(game), actor) if x.id == grown.asset)
        assert loss.asset == old and loss.event == grown.event
    answer(
        game,
        PLAYER,
        "consume_partake",
        options=("pass",),
        text="I decline optional Partake on this first real Dive",
    )
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, growth_action)["state"] == "complete"
    action, row = _elective_partake(game, worker, gateway)
    detail = game.decision(PLAYER, row["id"])["detail"]
    token = rules.identity("missing-frame-sup-dive-cap", grown.asset)
    assert token in detail["regrow_missing"]
    replacement = detail["regrow_replacements"][0][0]
    before, calls = state(game), game.dice.calls
    receipt = game.inspect(PLAYER, action)["receipt"]
    girl = next(x.id for x in before.sheets["2"].assets if x.family == "girl" and not x.damaged)
    _native_actual_cap_partake(game, row, girl=girl, token=token, replacement=replacement)
    final = state(game)
    component = next(
        x
        for x in rules.records(final, rules.RegrownFrame)
        if x.loss_kind == "sup_dive_cap" and x.loss == grown.asset
    )
    assert component.original == old and component.loss_event == grown.event
    assert component.component.id not in (old.id, grown.asset, replacement)
    assert component.component.void == old.void and component.replacement == replacement
    assert next(x for x in final.sheets["2"].assets if x.id == grown.asset).void
    assert next(x for x in final.sheets["2"].assets if x.id == girl).damaged
    assert final.sheets["2"].permissions == before.sheets["2"].permissions
    assert game.dice.calls == calls and game.inspect(PLAYER, action)["receipt"] == receipt
    with ledger.engine.connect() as c:
        assert prove_regrowth(game, c, final, component.id) == component
        assert token not in {x.token for x in _selections(game, c, final, actor)}
        assert (
            next(x for x in sup_dive_losses(game, c, final, actor) if x.id == grown.asset).asset
            == old
        )
    assert controls.view(PLAYER, component.id)["type"] == "regrowth"
    with pytest.raises(WorkflowError):
        controls.view(OTHER, component.id)
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"
