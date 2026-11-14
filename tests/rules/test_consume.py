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
        game.dice.faces = (6, 6)
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
        receipt = game.inspect(PLAYER, refused)["receipt"]
        assert receipt["pre_total"] > 7
        pass_tags(game)
        pending = game.inspect(PLAYER, refused)
        assert pending["state"] == "awaiting_choices"
        assert pending["result"] is None  # Results remain private until completion.
        assert not any(x["kind"] == "actor_disobey" for x in game.choices(PLAYER))
        # A low result forbids refusal; it does not invent the Handler's discovery choice.
        answer(game, ADMIN, "handler_disobey", flag=False)
        completed = game.inspect(PLAYER, refused)
        assert completed["state"] == "complete"
        assert completed["result"]["tier"] == "low"
        assert completed["result"]["total"] == 7
        assert completed["result"]["can_disobey"] is False
        assert completed["receipt"] == receipt
        assert completed["result"]["handler_knows"] is False
        assert rules.disobey_low(state(game), actor)
        assert rules.tag(state(game), actor, fact.tag)
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


def _elective_partake(game, worker, gateway, *, decline_risk=False, finish_handler=False):
    action = _elective_dive(game, worker, gateway)
    if decline_risk:
        answer(game, PLAYER, "mockingbird_risk")
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
    if finish_handler and any(x["kind"] == "dive_select" for x in game.choices(ADMIN)):
        answer(
            game,
            ADMIN,
            "dive_select",
            options=("void_and_unmark_all",),
            text="The actual high result requires my printed Handler choice",
        )
        site = next(
            x.id for x in state(game).sheets["2"].assets if x.family == "girl" and not x.void
        )
        answer(
            game,
            PLAYER,
            "dive_effect",
            fields={"asset": site},
            text="I record the actual Void alteration at this owned Girl Asset",
        )
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


def test_actual_modular_off_duty_replacement_then_native_partake_regrows_original_hardware(
    ledger, tmp_path, monkeypatch
):
    """Deferred: a genuine paid recovery replaces hardware without losing its regrowth source."""
    import asyncio

    import test_strain_effect_service
    import test_strain_service
    from test_mission_ui import current
    from test_off_duty_cycle import activate, call, finish_routine, movement, prepared, roll_for
    from test_strain_service import ready as strain_ready

    from girlframe.discord_adapter.m3_off_duty_cycle import open_action
    from girlframe.engine import m3_modular as modular
    from girlframe.engine.m3_off_duty import RecoveryChoice
    from girlframe.services.m3_access import Access
    from girlframe.services.m3_consume_regrowth import _selections, prove_regrowth
    from girlframe.services.m3_frame_asset_losses import modular_recovery_losses
    from girlframe.services.m3_modular import ModularService

    monkeypatch.setattr(
        test_strain_service,
        "service",
        lambda store, frame: service(store, girl="OLDGEN", frame="CONSUME"),
    )
    monkeypatch.setattr(
        test_strain_effect_service,
        "ready",
        lambda store, face: strain_ready(store, face=face, frame="CONSUME"),
    )
    cycle, game, period = prepared(ledger)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.STARVATION, rules.EAT, *rules.REQUISITIONS, modular.RULE),
    )
    cycle.missions.access = Access(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon = place(place(canon, 2, mode="outside_frame"), 3, mode="outside_frame")
        canon.sheets["2"].permissions = 20
        canon.sheets["2"].heat = 1
        original = next(
            x for x in canon.sheets["2"].assets if x.family == "frame" and x.intrinsic is None
        )
        original.damaged = True
        old = original.model_copy(deep=True)
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_damaged_modular_hardware", canon)
    controls = ConsumeService(game)
    acquire(controls, rules.PARTAKE)
    modular_service = ModularService(game)
    offer = modular_service.menu(PLAYER)
    actor = ActorRef.model_validate(offer["actor"])
    paid = modular_service.buy(
        PLAYER,
        str(uuid4()),
        offer["revision"],
        actor,
        offer["frame"],
        "I genuinely pay for the LEGION repair source graft",
        "Actual additional modular fitting",
        "Actual newly acquired fitting, separate from the damaged old component",
        offer["donors"][0],
    )
    activate(cycle, game, period)
    recovery_action = roll_for(cycle, game, period, PLAYER, (2, 2))
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    receipt = game.inspect(PLAYER, recovery_action)["receipt"]

    async def recover():
        opened = current(2, 992100)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_action(opened, cycle, period, "recover")
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(repairs=("yes",), modular_assets=(old.id,))
        form.values["modular_name:" + old.id] = "Actual repaired-source replacement fitting"
        form.values["modular_description:" + old.id] = "Actual new hardware replacing the old part"
        submitted = current(2, 992101)
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(recover())
    assert game.inspect(PLAYER, recovery_action)["receipt"] == receipt
    born = state(game)
    fact = next(
        x for x in born.facts if x.get("kind") == "modular_repair" and x.get("old") == old.id
    )
    assert fact["period"] == period and fact["purchase"] == paid["id"]
    replacement = next(x for x in born.sheets["2"].assets if x.id == fact["new"])
    assert not replacement.damaged and old.id not in {x.id for x in born.sheets["2"].assets}
    with ledger.engine.connect() as c:
        loss = next(
            x for x in modular_recovery_losses(game, c, born, actor) if x.asset.id == old.id
        )
        assert loss.asset == old and loss.frame == rules.frame(born, actor)
    roll_for(cycle, game, period, OTHER, (4, 4))
    call(cycle, game, OTHER, period, "scene", None, (), "")
    call(cycle, game, OTHER, period, "recover", RecoveryChoice())
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    worker, gateway = GameWorker(game), Gateway()
    cockpit(game, "pilot")
    action, row = _elective_partake(game, worker, gateway)
    token = rules.identity("missing-frame-modular-recovery", loss.id)
    assert token in game.decision(PLAYER, row["id"])["detail"]["regrow_missing"]
    before, calls = state(game), game.dice.calls
    receipt = game.inspect(PLAYER, action)["receipt"]
    girl = next(x.id for x in before.sheets["2"].assets if x.family == "girl" and not x.damaged)
    _native_actual_cap_partake(game, row, girl=girl, token=token)
    final = state(game)
    regrown = next(
        x
        for x in rules.records(final, rules.RegrownFrame)
        if x.loss_kind == "modular_recovery" and x.loss == loss.id
    )
    assert regrown.original == old and regrown.loss_event == loss.event
    assert regrown.component.id not in (old.id, replacement.id)
    assert next(x for x in final.sheets["2"].assets if x.id == replacement.id) == replacement
    assert next(x for x in final.sheets["2"].assets if x.id == girl).damaged
    assert final.sheets["2"].permissions == before.sheets["2"].permissions
    assert game.dice.calls == calls and game.inspect(PLAYER, action)["receipt"] == receipt
    with ledger.engine.connect() as c:
        assert prove_regrowth(game, c, final, regrown.id) == regrown
        assert token not in {x.token for x in _selections(game, c, final, actor)}
    with pytest.raises(WorkflowError):
        controls.view(OTHER, regrown.id)
    assert controls.view(PLAYER, regrown.id)["type"] == "regrowth"
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_actual_native_risk_sup_cap_exchange_then_partake_regrowth_preserves_original_roll(
    ledger, tmp_path, monkeypatch
):
    """Deferred: only the real Risk payment proves this second Sup gain-source family."""
    import asyncio
    import sys

    from test_mission_ui import current
    from test_sup import purchase as buy_sup

    from girlframe.discord_adapter.m3_mockingbird import open_mockingbird
    from girlframe.discord_adapter.m3_sup import GROW
    from girlframe.engine import m3_mockingbird as mockingbird
    from girlframe.engine import m3_sup as sup
    from girlframe.services.m3_consume_regrowth import _selections, prove_regrowth
    from girlframe.services.m3_frame_asset_losses import sup_risk_losses

    original_service = service
    monkeypatch.setattr(
        sys.modules[__name__],
        "service",
        lambda store, **kwargs: original_service(store, girl="MOCKINGBIRD", frame="CONSUME"),
    )
    game, worker, gateway, controls, actor, old = _elective_regrowth_ready(
        ledger, tmp_path, monkeypatch
    )
    paid = buy_sup(game, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.STARVATION, rules.EAT, *rules.REQUISITIONS, sup.RULE, mockingbird.RISK),
    )
    cockpit(game, "pilot")
    game.dice.faces = (1, 2)
    incoming = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            piloting=True,
            context="I really resist this incoming threat inside my own Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, incoming)["receipt"]
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "mockingbird_risk")
    receipt, calls = game.inspect(PLAYER, incoming)["receipt"], game.dice.calls

    async def grow():
        opened = current(2, 992200)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_mockingbird(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(total=("9",), asset=(GROW,))
        selected = current(2, 992201)
        selected.channel_id = 900
        await form.confirm.callback(selected)
        assert form.completed, selected.edit_original_response.call_args_list
        growth = selected.edit_original_response.call_args.kwargs["view"]
        growth.values.update(
            name="Actual Risk-grown Void plate",
            family=("frame",),
            replace=(old.id,),
            description="PRIVATE_RISK_SUP actual organic corrupted plate born for this payment",
        )
        submitted = current(2, 992202)
        submitted.channel_id = 900
        await growth.confirm.callback(submitted)
        assert growth.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await growth.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(grow())
    grown = next(x for x in sup.growths(state(game)) if x.action == incoming)
    assert grown.purchase == paid.id and grown.choice.replace == old.id
    assert game.inspect(PLAYER, incoming)["receipt"] == receipt and game.dice.calls == calls
    assert game.inspect(PLAYER, incoming)["state"] != "complete"
    with ledger.engine.connect() as c:
        loss = next(x for x in sup_risk_losses(game, c, state(game), actor) if x.id == grown.asset)
        assert loss.asset == old and loss.event == grown.event
    answer(game, PLAYER, "actor_keep", options=("in_control", "vicious"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual defense is sufficient")
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, incoming)["state"] == "complete"
    action, row = _elective_partake(game, worker, gateway, decline_risk=True)
    detail = game.decision(PLAYER, row["id"])["detail"]
    token = rules.identity("missing-frame-sup-risk-cap", grown.asset)
    assert token in detail["regrow_missing"]
    replacement = next(x[0] for x in detail["regrow_replacements"] if x[0] != grown.asset)
    before, calls = state(game), game.dice.calls
    receipt = game.inspect(PLAYER, action)["receipt"]
    girl = next(x.id for x in before.sheets["2"].assets if x.family == "girl" and not x.damaged)
    _native_actual_cap_partake(game, row, girl=girl, token=token, replacement=replacement)
    final = state(game)
    regrown = next(
        x
        for x in rules.records(final, rules.RegrownFrame)
        if x.loss_kind == "sup_risk_cap" and x.loss == grown.asset
    )
    assert regrown.original == old and regrown.loss_event == grown.event
    assert regrown.component.id not in (old.id, grown.asset, replacement)
    assert next(x for x in final.sheets["2"].assets if x.id == grown.asset).void
    assert next(x for x in final.sheets["2"].assets if x.id == girl).damaged
    assert game.dice.calls == calls and game.inspect(PLAYER, action)["receipt"] == receipt
    assert final.sheets["2"].permissions == before.sheets["2"].permissions
    with ledger.engine.connect() as c:
        assert prove_regrowth(game, c, final, regrown.id) == regrown
        assert token not in {x.token for x in _selections(game, c, final, actor)}
    with pytest.raises(WorkflowError):
        controls.view(OTHER, regrown.id)
    assert controls.view(PLAYER, regrown.id)["type"] == "regrowth"
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"


def _acquire_modular_for_consume(game):
    from girlframe.services.m3_modular import ModularService

    source = ModularService(game)
    data = source.menu(PLAYER)
    source.buy(
        PLAYER,
        str(uuid4()),
        data["revision"],
        ActorRef.model_validate(data["actor"]),
        data["frame"],
        "Actual paid original Modular graft",
        "Actual additional fitting",
        "Actual new hardware from this paid graft",
        data["donors"][0],
    )


def _assert_native_modular_loss_regrowth(game, worker, gateway, controls, loss, replacement):
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_assets import counts_toward_limit, frame_capacity
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_consume_regrowth import _selections, prove_regrowth

    with game.store.engine.connect() as c:
        canon = state(game)
        body = resolve(canon, loss.actor, profiles(c, game.store.campaign_id))
    if body.piloting is not True:
        cockpit(game, "pilot")
    action, row = _elective_partake(game, worker, gateway, finish_handler=True)
    detail = game.decision(PLAYER, row["id"])["detail"]
    token = rules.identity("missing-frame-" + loss.source_kind.replace("_", "-"), loss.id)
    assert token in detail["regrow_missing"]
    before, calls = state(game), game.dice.calls
    sheet = before.sheets["2"]
    full = sum(
        counts_toward_limit(sheet, x) for x in sheet.assets if x.family == "frame"
    ) >= frame_capacity(sheet, before)
    displaced = (
        next((x[0] for x in detail["regrow_replacements"] if x[0] != replacement.id), None)
        if full
        else None
    )
    receipt = game.inspect(PLAYER, action)["receipt"]
    girl = next(x.id for x in sheet.assets if x.family == "girl" and not x.damaged)
    _native_actual_cap_partake(game, row, girl=girl, token=token, replacement=displaced)
    final = state(game)
    regrown = next(
        x
        for x in rules.records(final, rules.RegrownFrame)
        if x.loss_kind == loss.source_kind and x.loss == loss.id
    )
    assert regrown.original == loss.asset and regrown.loss_event == loss.event
    assert regrown.component.id not in (loss.asset.id, replacement.id, displaced)
    assert next(x for x in final.sheets["2"].assets if x.id == replacement.id) == replacement
    assert next(x for x in final.sheets["2"].assets if x.id == girl).damaged
    assert not any(x.id == loss.asset.id for x in final.sheets["2"].assets)
    assert game.dice.calls == calls and game.inspect(PLAYER, action)["receipt"] == receipt
    assert final.sheets["2"].permissions == sheet.permissions
    with game.store.engine.connect() as c:
        assert prove_regrowth(game, c, final, regrown.id) == regrown
        assert token not in {x.token for x in _selections(game, c, final, loss.actor)}
    with pytest.raises(WorkflowError):
        controls.view(OTHER, regrown.id)
    assert controls.view(PLAYER, regrown.id)["type"] == "regrowth"
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_actual_native_paid_quote_modular_repair_then_partake_regrowth(
    ledger, tmp_path, monkeypatch
):
    """Deferred: actual shortage/quoted payment, distinct from free ordinary recovery."""
    import asyncio

    import test_repair_service
    import test_strain_service
    from test_mission_ui import current
    from test_off_duty_cycle import call, finish_routine, movement, roll_for
    from test_repair_service import ready as repair_ready

    from girlframe.discord_adapter.m3_repairs import open_quote
    from girlframe.engine import m3_modular as modular
    from girlframe.engine.m3_core import RepairSelection
    from girlframe.engine.m3_off_duty import RecoveryChoice
    from girlframe.services.m3_access import Access
    from girlframe.services.m3_frame_asset_losses import modular_quote_losses

    def configured(store, frame):
        missions, game = service(store, girl="OLDGEN", frame="CONSUME")
        approved(
            store,
            game,
            tmp_path,
            monkeypatch,
            extra=(rules.STARVATION, rules.EAT, *rules.REQUISITIONS, modular.RULE),
        )
        missions.access = Access(store)
        return missions, game

    monkeypatch.setattr(test_strain_service, "service", configured)
    original_period = test_repair_service.source_period

    def placed_period(store):
        effects, cycle, game, period = original_period(store)
        with store.transaction() as c:
            canon = state(game)
            canon = place(place(canon, 2, mode="outside_frame"), 3, mode="outside_frame")
            game.event(
                c, 1, str(uuid4()), "synthetic.actual_original_repair_period_positions", canon
            )
        return effects, cycle, game, period

    monkeypatch.setattr(test_repair_service, "source_period", placed_period)
    repairs, cycle, game, period = repair_ready(ledger)
    cycle.missions.access = Access(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 20
        game.event(c, 1, str(uuid4()), "synthetic.actual_quote_owner_resources", canon)
    controls = ConsumeService(game)
    acquire(controls, rules.PARTAKE)
    _acquire_modular_for_consume(game)
    actor = current_ref(state(game), 2)
    old = next(x.model_copy(deep=True) for x in state(game).sheets["2"].assets if x.id == "frame:1")
    quote = repairs.offer(ADMIN, str(uuid4()), state(game).revision, period, 2, old.id, 2)
    before = state(game)

    async def accept():
        opened = current(2, 992300)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_quote(opened, repairs, quote["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 992301))
        form.values.update(answer=("accept",), modular_assets=(old.id,))
        form.values["modular_name:" + old.id] = "Actual quoted replacement"
        form.values["modular_description:" + old.id] = "New hardware for the actual priced repair"
        submitted = current(2, 992302)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(accept())
    born = state(game)
    assert born.sheets["2"].permissions == before.sheets["2"].permissions - 2
    with ledger.engine.connect() as c:
        loss = next(x for x in modular_quote_losses(game, c, born, actor) if x.asset.id == old.id)
    fact = next(
        x
        for x in born.facts
        if x.get("kind") == "modular_repair" and x.get("source") == "repair_quote:" + quote["id"]
    )
    replacement = next(x for x in born.sheets["2"].assets if x.id == fact["new"])
    assert loss.asset == old
    roll_for(cycle, game, period, OTHER, (4, 4))
    call(
        cycle,
        game,
        OTHER,
        period,
        "scene",
        "nearby_city",
        (3, 2),
        "We actually play the required high OffDuty scene together in a nearby city",
    )
    call(cycle, game, OTHER, period, "acknowledge", 3)
    call(cycle, game, PLAYER, period, "acknowledge", 3)
    sheet = state(game).sheets["3"]
    selection = RepairSelection(
        **{
            family: tuple(x.id for x in sheet.assets if x.family == family and x.damaged)[:1]
            for family in ("girl", "frame")
        }
    )
    call(cycle, game, OTHER, period, "recover", RecoveryChoice(repairs=selection))
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    _assert_native_modular_loss_regrowth(
        game, GameWorker(game), Gateway(), controls, loss, replacement
    )


def test_actual_native_doctor_patient_modular_repair_then_partake_regrowth(
    ledger, tmp_path, monkeypatch
):
    """Deferred: actual other Doctor performs the Play; only the patient selects replacement."""
    import asyncio

    import test_m2_game
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_doctor import open_choice
    from girlframe.engine import m3_doctor as doctor
    from girlframe.engine import m3_modular as modular
    from girlframe.services.m3_doctor import DoctorService
    from girlframe.services.m3_frame_asset_losses import modular_doctor_losses

    original_ready, original_selected = test_m2_game.ready, test_m2_game.selected
    monkeypatch.setattr(
        test_m2_game,
        "ready",
        lambda store, girl, frame: original_ready(store, girl, frame, other_frame=doctor.BOOK),
    )
    monkeypatch.setattr(
        test_m2_game, "selected", lambda girl, frame: original_selected(girl, doctor.BOOK)
    )
    # The real setup helper now saves/reviews/activates Other's actual Doctor profile and draft.
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            rules.STARVATION,
            rules.EAT,
            *rules.REQUISITIONS,
            modular.RULE,
            doctor.NANO,
            doctor.TRACK,
        ),
    )
    acquire(controls, rules.PARTAKE)
    _acquire_modular_for_consume(game)
    actor = current_ref(state(game), 2)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].heat = 2
        old = next(
            x for x in canon.sheets["2"].assets if x.family == "frame" and x.intrinsic is None
        )
        old.damaged = True
        old = old.model_copy(deep=True)
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_patient_damage", canon)
    game.dice.faces = (3, 4)
    action = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="nanobot_injection",
            target_actor=actor,
            heat=2,
            context="I actually treat this original patient",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.inspect(OTHER, action)["receipt"]
    pass_tags(game)
    receipt, calls = game.inspect(OTHER, action)["receipt"], game.dice.calls
    source = DoctorService(game)

    async def treat():
        row = next(x for x in game.choices(OTHER) if x["kind"] == "doctor_nanobot_benefits")
        opened = current(3, 992400)
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, source, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(choices=("repair",))
        selected = current(3, 992401)
        await form.confirm.callback(selected)
        assert form.completed, selected.edit_original_response.call_args_list
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "doctor_patient")
        patient = current(2, 992402)
        await patient.response.defer(ephemeral=True)
        await open_choice(patient, source, row["id"])
        owned = patient.edit_original_response.call_args.kwargs["view"]
        assert not await owned.interaction_check(current(3, 992403))
        owned.values.update(assets=(old.id,), modular_assets=(old.id,))
        owned.values["modular_name:" + old.id] = "Actual Nanobot replacement"
        owned.values["modular_description:" + old.id] = "Patient-authored new repaired hardware"
        submitted = current(2, 992404)
        await owned.confirm.callback(submitted)
        assert owned.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await owned.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(treat())
    born = state(game)
    assert game.inspect(OTHER, action)["receipt"] == receipt and game.dice.calls == calls
    with ledger.engine.connect() as c:
        loss = next(x for x in modular_doctor_losses(game, c, born, actor) if x.asset.id == old.id)
    fact = next(
        x for x in born.facts if x.get("kind") == "modular_repair" and x.get("old") == old.id
    )
    replacement = next(x for x in born.sheets["2"].assets if x.id == fact["new"])
    assert loss.asset == old
    tick(worker, gateway, 6)
    assert game.inspect(OTHER, action)["state"] == "complete"
    _assert_native_modular_loss_regrowth(game, worker, gateway, controls, loss, replacement)


def test_actual_native_supply_repair_modular_replacement_then_partake_regrowth(
    ledger, tmp_path, monkeypatch
):
    """Deferred: genuine used advancement/mission repair, never temporary equipment expiry."""
    import asyncio

    import test_strain_service
    from test_mission_ui import current
    from test_supply_drop import acquire as acquire_supply
    from test_supply_drop import launch, propose, settle
    from test_supply_drop import ready as supply_ready

    from girlframe.discord_adapter.m3_supply_drop import open_delivery
    from girlframe.engine import m3_handler_advancements as awards
    from girlframe.engine import m3_modular as modular
    from girlframe.engine import m3_supply_drop as supply
    from girlframe.services.m3_access import Access
    from girlframe.services.m3_frame_asset_losses import modular_supply_losses

    def configured(store, frame):
        missions, game = service(store, girl="OLDGEN", frame="CONSUME")
        approved(
            store,
            game,
            tmp_path,
            monkeypatch,
            extra=(
                rules.STARVATION,
                rules.EAT,
                *rules.REQUISITIONS,
                modular.RULE,
                *awards.RULES,
                supply.RULE,
            ),
        )
        missions.access = Access(store)
        return missions, game

    monkeypatch.setattr(test_strain_service, "service", configured)
    game, supplies, missions, award = supply_ready(ledger, tmp_path, monkeypatch)
    acquire_supply(supplies, award)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 20
        game.event(c, 1, str(uuid4()), "synthetic.actual_original_modular_funds", canon)
    controls = ConsumeService(game)
    acquire(controls, rules.PARTAKE)
    _acquire_modular_for_consume(game)
    actor = current_ref(state(game), 2)
    with ledger.transaction() as c:
        canon = state(game)
        old = next(
            x for x in canon.sheets["2"].assets if x.family == "frame" and x.intrinsic is None
        )
        old.damaged = True
        old = old.model_copy(deep=True)
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_supply_repair_damage", canon)
    mission = launch(missions)
    identity = propose(supplies, game, mission, "repair", old.id)

    async def receive():
        opened = current(2, 992500)
        await opened.response.defer(ephemeral=True)
        await open_delivery(opened, supplies, identity)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 992501))
        form.values.update(
            receive=("yes",),
            modular=("replace",),
            name="Actual Supply repair replacement",
            description="Owned replacement from this actual mission repair",
            account="I genuinely receive the actual source repair",
        )
        submitted = current(2, 992502)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(receive())
    born = state(game)
    use = next(x for x in supply.uses(born) if x.id == identity)
    assert use.kind == "repair" and use.phase == "repaired"
    with ledger.engine.connect() as c:
        loss = next(x for x in modular_supply_losses(game, c, born, actor) if x.asset.id == old.id)
    fact = next(
        x for x in born.facts if x.get("kind") == "modular_repair" and x.get("source") == identity
    )
    replacement = next(x for x in born.sheets["2"].assets if x.id == fact["new"])
    assert loss.asset == old and loss.event == use.effect_event
    data = missions.get(ADMIN, mission)["mission"]
    missions.end(ADMIN, str(uuid4()), mission, data["revision"], True)
    settle(missions, game, mission)
    assert next(x for x in supply.uses(state(game)) if x.id == identity).phase == "repaired"
    _assert_native_modular_loss_regrowth(
        game, GameWorker(game), Gateway(), controls, loss, replacement
    )


def _native_actual_sup_cap_growth(game, opener, old, first_values, *, number, name):
    import asyncio

    from test_mission_ui import current

    async def respond():
        opened = current(2, number)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await opener(opened)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, number + 1))
        form.values.update(first_values)
        selected = current(2, number + 2)
        selected.channel_id = 900
        await form.confirm.callback(selected)
        assert form.completed, selected.edit_original_response.call_args_list
        growth = selected.edit_original_response.call_args.kwargs["view"]
        growth.values.update(
            name=name,
            family=("frame",),
            replace=(old.id,),
            description="PRIVATE_SUP_FAMILY actual source-owned new Void hardware: " + name,
        )
        actual = current(2, number + 3)
        actual.channel_id = 900
        await growth.confirm.callback(actual)
        assert growth.completed, actual.edit_original_response.call_args_list
        saved = state(game)
        await growth.confirm.callback(actual)
        assert state(game) == saved

    asyncio.run(respond())


def test_actual_native_sex_sup_cap_loss_then_partake_preserves_owned_counterpart_and_source(
    ledger, tmp_path, monkeypatch
):
    from test_sup import purchase as buy_sup

    from girlframe.discord_adapter.m3_mockingbird_sex import open_sex
    from girlframe.engine import m3_mockingbird as mockingbird
    from girlframe.engine import m3_sup as sup
    from girlframe.services.m3_frame_asset_losses import sup_sex_losses
    from girlframe.services.m3_mockingbird_plays import MockingbirdService

    game, worker, gateway, controls, actor, old = _elective_regrowth_ready(
        ledger, tmp_path, monkeypatch
    )
    paid = buy_sup(game, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.STARVATION, rules.EAT, *rules.REQUISITIONS, sup.RULE, mockingbird.SEX),
    )
    caster = current_ref(state(game), 3)
    source = MockingbirdService(game)
    trigger = source.propose(
        OTHER,
        str(uuid4()),
        900,
        caster,
        "mockingbird_sex",
        (actor,),
        "My actual original voluntary interaction with this other person",
    )
    source.attest(PLAYER, str(uuid4()), trigger["id"], actor, True)
    game.dice.faces = (6, 6)
    action = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="mockingbird_sex",
            source_work=trigger["id"],
            heat=0,
            context="Actual accepted counterpart source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.inspect(OTHER, action)["receipt"]
    pass_tags(game)
    original_target = next(
        x for x in state(game).sheets["2"].assets if x.family == "girl" and not x.void
    ).model_copy(deep=True)
    answer(game, OTHER, "mockingbird_sex_infect", fields={"asset": original_target.id})
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "mockingbird_sex_rewrite")
    before, calls = state(game), game.dice.calls
    receipt = game.inspect(OTHER, action)["receipt"]

    async def opener(interaction):
        await open_sex(interaction, game, row["id"])

    _native_actual_sup_cap_growth(
        game, opener, old, {"mode": ("grow",)}, number=992600, name="Actual counterpart Sup plate"
    )
    born = state(game)
    grown = next(x for x in sup.growths(born) if x.action == action)
    assert grown.purchase == paid.id and grown.actor == actor
    assert next(x for x in born.sheets["2"].assets if x.id == original_target.id) == original_target
    assert born.sheets["3"].assets == before.sheets["3"].assets
    assert depth(born, caster, actor) == min(2, depth(before, caster, actor) + 1)
    assert game.inspect(OTHER, action)["receipt"] == receipt and game.dice.calls == calls
    with ledger.engine.connect() as c:
        loss = next(x for x in sup_sex_losses(game, c, born, actor) if x.id == grown.asset)
    assert loss.asset == old
    replacement = next(x for x in born.sheets["2"].assets if x.id == grown.asset)
    tick(worker, gateway, 6)
    assert game.inspect(OTHER, action)["state"] == "complete"
    _assert_native_modular_loss_regrowth(game, worker, gateway, controls, loss, replacement)


def test_actual_native_dormant_sup_cap_loss_then_attack_completion_and_partake(
    ledger, tmp_path, monkeypatch
):
    import test_battle_pipeline
    import test_battle_service
    from test_battle_pipeline import dormant_source, table
    from test_sup import purchase as buy_sup

    from girlframe.discord_adapter.m3_battle_dormant import open_dormant
    from girlframe.discord_adapter.m3_sup import GROW
    from girlframe.engine import m3_sup as sup
    from girlframe.engine.m3_assets import counts_toward_limit
    from girlframe.engine.m3_requisition_state import Installation
    from girlframe.services.m3_battle_dormant import DormantService
    from girlframe.services.m3_frame_asset_losses import sup_dormant_losses
    from girlframe.services.m3_requisitions import RequisitionService

    _, game = service(ledger, girl="OLDGEN", frame="CONSUME")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.STARVATION, rules.EAT, *rules.REQUISITIONS, sup.RULE),
    )
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"world", "playbooks"}}
            )
        }
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 20
        canon.sheets["2"].heat = 1
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_unplaced_consume_resources", canon)
    worker, gateway, controls = GameWorker(game), Gateway(), ConsumeService(game)
    actor = current_ref(state(game), 2)
    monkeypatch.setattr(test_battle_service, "ready", lambda store: (game, worker, gateway))
    original_prepared = test_battle_pipeline.prepared
    acquired = {}

    def paid_prepared(store, *, girl=None):
        # The real Battle helper establishes the previously unknown bodies once.
        result = original_prepared(store, girl=girl)
        acquire(controls, rules.PARTAKE)
        purchases = RequisitionService(game)
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
                    name="Actual Dormant source spare " + str(len(sheet.assets)),
                    description="Actual paid hardware before the real attack declaration",
                    account="I genuinely purchase this original permanent component",
                    trigger_confirmed=True,
                ),
            )
        acquired["sup"] = buy_sup(game, tmp_path, monkeypatch)
        # dormant_source builds its own fresh declaration after these real purchases.
        return result

    monkeypatch.setattr(test_battle_pipeline, "prepared", paid_prepared)
    actual_game, _, _, action, work = dormant_source(ledger, monkeypatch)
    paid = acquired["sup"]
    assert actual_game is game
    with ledger.engine.connect() as c:
        declaration = game.action(c, action)["data"]["battle"]
    old = next(
        x.model_copy(deep=True)
        for x in state(game).sheets["2"].assets
        if x.family == "frame" and not x.void and x.id != declaration["attacking_asset"]
    )
    source = DormantService(ledger, game)
    receipt, calls = game.inspect(PLAYER, action)["receipt"], game.dice.calls

    async def opener(interaction):
        await open_dormant(interaction, source, work)

    _native_actual_sup_cap_growth(
        game,
        opener,
        old,
        {"asset": (GROW,), "piloting": ("yes",)},
        number=992700,
        name="Actual Dormant-payment Sup plate",
    )
    born = state(game)
    grown = next(x for x in sup.growths(born) if x.action == work)
    assert grown.purchase == paid.id and game.inspect(PLAYER, action)["state"] != "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == calls
    with ledger.engine.connect() as c:
        loss = next(x for x in sup_dormant_losses(game, c, born, actor) if x.id == grown.asset)
    assert loss.asset == old and source.get(PLAYER, work)["state"] == "resolved"
    replacement = next(x for x in born.sheets["2"].assets if x.id == grown.asset)
    table(game)
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    _assert_native_modular_loss_regrowth(game, worker, gateway, controls, loss, replacement)


def test_actual_native_cleanup_exposure_sup_cap_loss_then_real_period_and_partake(
    ledger, tmp_path, monkeypatch
):
    import test_budget_cleanup
    from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
    from test_sup import purchase as buy_sup
    from test_supply_drop import launch, settle
    from test_world import gorgon

    from girlframe.discord_adapter.m3_budget_cleanup import open_cleanup
    from girlframe.discord_adapter.m3_sup import GROW
    from girlframe.engine import m3_budget_cleanup as cleanup
    from girlframe.engine import m3_sup as sup
    from girlframe.engine.m3_strain_effects import Choice
    from girlframe.engine.m3_world_state import Faction
    from girlframe.services.m3_budget_cleanup import CleanupService
    from girlframe.services.m3_frame_asset_losses import sup_cleanup_losses
    from girlframe.services.m3_off_duty_cycle import CycleService

    game, worker, gateway, controls, actor, old = _elective_regrowth_ready(
        ledger, tmp_path, monkeypatch
    )
    paid = buy_sup(game, tmp_path, monkeypatch)
    missions = MissionService(ledger)
    mission = launch(missions)
    data = missions.get(ADMIN, mission)["mission"]
    missions.end(ADMIN, str(uuid4()), mission, data["revision"], True)
    settle(missions, game, mission)
    effects, actual_game, mission, work, _, draw = test_budget_cleanup.ready(
        ledger, existing=(missions, game, {"id": mission})
    )
    assert actual_game is game
    test_budget_cleanup.select(effects, mission, work, "exposure")
    identity = work + ":cleanup"
    source = CleanupService(ledger)
    actual = cleanup.get(state(game), identity)
    assert (
        actual.selected is not None and actual.people[actual.selected] == actor and draw.calls == 1
    )

    async def opener(interaction):
        await open_cleanup(interaction, source, identity)

    _native_actual_sup_cap_growth(
        game,
        opener,
        old,
        {"asset": (GROW,)},
        number=992800,
        name="Actual cleanup-exposure Sup plate",
    )
    born = state(game)
    grown = next(x for x in sup.growths(born) if x.action == identity)
    assert grown.purchase == paid.id and draw.calls == 1
    assert cleanup.get(born, identity).phase == "complete"
    assert test_budget_cleanup.resolved(ledger, identity) == "resolved"
    with ledger.engine.connect() as c:
        loss = next(x for x in sup_cleanup_losses(game, c, born, actor) if x.id == grown.asset)
    assert loss.asset == old
    replacement = next(x for x in born.sheets["2"].assets if x.id == grown.asset)
    period = actual.period
    for track in ("void", "rebellion"):
        request = next(x for x in state(game).strain.requests if x.track == track)
        reviewed = effects.strain.work(ADMIN, request.id)
        effects.strain.dice.face = 1
        rolled = effects.strain.roll(
            ADMIN, str(uuid4()), request.id, reviewed["revision"], reviewed["game_revision"]
        )
        effects.strain.choose(
            ADMIN, str(uuid4()), request.id, rolled["revision"], state(game).revision, 1
        )
        selected = (
            Choice(
                rule_id="strain.void.low.1.1",
                account="The actual new Directed appears at the map edge",
                gorgon=gorgon("directed", "cleanup-sup-arrival", (10, 0)),
            )
            if track == "void"
            else Choice(
                rule_id="strain.rebellion.low.1.1",
                account="Actual source organizing at the city",
                target="city0",
                faction=Faction(
                    id="cleanup-sup-group",
                    name="Actual cleanup-period group",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Actual new source group",
                ),
            )
        )
        effects.apply(
            ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, selected
        )
    cycle = CycleService(effects.strain.periods)
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    assert draw.calls == 1
    _assert_native_modular_loss_regrowth(game, worker, gateway, controls, loss, replacement)


def test_actual_learned_risk_sup_cap_loss_retains_real_lesson_payment_then_partake(
    ledger, tmp_path, monkeypatch
):
    import test_vatgrown_plays
    from test_sup import purchase as buy_sup

    from girlframe.discord_adapter.m3_mockingbird import open_mockingbird
    from girlframe.discord_adapter.m3_sup import GROW
    from girlframe.engine import m3_sup as sup
    from girlframe.engine import m3_vatgrown_plays as vat
    from girlframe.engine.m3_assets import counts_toward_limit
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.engine.m3_mockingbird import RISK
    from girlframe.engine.m3_requisition_state import Installation
    from girlframe.services.m3_frame_asset_losses import sup_risk_losses
    from girlframe.services.m3_learned_plays import available, prove_risk_lesson
    from girlframe.services.m3_requisitions import RequisitionService

    original_service = test_vatgrown_plays.service
    monkeypatch.setattr(
        test_vatgrown_plays,
        "service",
        lambda store, girl, frame: original_service(store, girl=girl, frame="CONSUME"),
    )
    game, worker, gateway, teacher_source = test_vatgrown_plays.ready(
        ledger, tmp_path, monkeypatch, teacher="MOCKINGBIRD"
    )
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            rules.STARVATION,
            rules.EAT,
            *rules.REQUISITIONS,
            sup.RULE,
            RISK,
            vat.EXPERIMENT,
            vat.INVESTMENT,
            vat.SEX,
        ),
    )
    actor = current_ref(state(game), 2)
    session, lesson_action = test_vatgrown_plays.sex(
        game,
        worker,
        gateway,
        teacher_source,
        (5, 5),
        counterpart_account="My actual original Mockingbird teaches one whole Risk Factor use",
    )
    own = state(game).sheets["2"]
    replaced = own.identities[0]
    remaining = {x.name.casefold() for x in own.identities if x.id != replaced.id}
    taught = next(
        x for x in state(game).sheets["3"].identities if x.name.casefold() not in remaining
    )
    test_vatgrown_plays.native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(taught.id,),
        replacements=(replaced.id,),
        play=(RISK,),
        account="I genuinely teach this printed Risk Factor Play once",
    )
    lesson = vat.records(state(game), vat.LearnedPlay)[-1]
    assert game.inspect(PLAYER, lesson_action)["state"] == "complete"
    teacher_source.send_away(
        OTHER,
        str(uuid4()),
        session,
        state(game).revision,
        "The actual teacher ends the required stay",
    )
    tick(worker, gateway, 6)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 20
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_learner_permissions", canon)
    controls = ConsumeService(game)
    acquire(controls, rules.PARTAKE)
    paid = buy_sup(game, tmp_path, monkeypatch)
    purchases = RequisitionService(game)
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
                name="Actual learner spare " + str(len(sheet.assets)),
                description="Actual permanently purchased pre-source hardware",
                account="Actual paid original spare",
                trigger_confirmed=True,
            ),
        )
    old = next(
        x.model_copy(deep=True)
        for x in state(game).sheets["2"].assets
        if x.family == "frame" and not x.void
    )
    with ledger.engine.connect() as c:
        assert available(game, c, state(game), actor, RISK).id == lesson.id
    cockpit(game, "pilot")
    heat = state(game).sheets["2"].heat
    game.dice.faces = (1, 2)
    incoming = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=heat if heat >= 5 else 0,
            piloting=True,
            context="I actually resist this original incoming threat",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, incoming)["receipt"]
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "mockingbird_risk")
    receipt, calls = game.inspect(PLAYER, incoming)["receipt"], game.dice.calls

    async def opener(interaction):
        await open_mockingbird(interaction, game, row["id"])

    _native_actual_sup_cap_growth(
        game,
        opener,
        old,
        {"total": ("9",), "asset": (GROW,)},
        number=992900,
        name="Actual consumed-lesson Sup plate",
    )
    born = state(game)
    grown = next(x for x in sup.growths(born) if x.action == incoming)
    assert grown.purchase == paid.id and not has_rule(born.sheets["2"], RISK, "MOCKINGBIRD")
    with ledger.engine.connect() as c:
        use = prove_risk_lesson(game, c, born, game.action(c, incoming))
        assert use.lesson == lesson.id and use.asset == grown.asset
        loss = next(x for x in sup_risk_losses(game, c, born, actor) if x.id == grown.asset)
        assert available(game, c, born, actor, RISK) is None
    assert (
        loss.asset == old
        and game.dice.calls == calls
        and game.inspect(PLAYER, incoming)["receipt"] == receipt
    )
    answer(game, PLAYER, "actor_keep", options=("in_control", "vicious"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual defense works")
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, incoming)["state"] == "complete"
    replacement = next(x for x in born.sheets["2"].assets if x.id == grown.asset)
    _assert_native_modular_loss_regrowth(game, worker, gateway, controls, loss, replacement)
