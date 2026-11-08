"""Wyvern's distinct printed normals; only the mid-Roused strike is a work smoke.

Other normals are deliberately authored for the final P1 selection, not run while
implementing this unit. All fixtures are offline human-authoritative game facts.
"""

from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_wyvern as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_wyvern import WyvernService, prove_use
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store, tmp_path, monkeypatch):
    _, game = service(store, girl="OLDGEN", frame=rules.FRAME)
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.BEAST, rules.BURDEN, rules.CHASSIS, *rules.REQUISITIONS),
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
        canon = place(place(canon, 2, mode="piloting"), 3, mode="outside_frame")
        canon.sheets["2"].permissions = 20
        canon.sheets["2"].heat = 4
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.actual_wyvern_bodies_resources_and_scene", canon)
    return game, GameWorker(game), Gateway(), WyvernService(game)


def buy(controls, rule, **details):
    return controls.purchase(
        PLAYER,
        str(uuid4()),
        state(controls.game).revision,
        rule,
        "I voluntarily acquire this actual two-Permission source",
        **details,
    )


def roll(
    game,
    worker,
    gateway,
    *,
    play="wyvern_rouse",
    faces=(3, 4),
    target=None,
    source_work=None,
    heat=1,
):
    game.dice.faces = faces
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=play,
            context="I perform this actual source in the original Wyvern scene",
            trigger_confirmed=True,
            heat=heat,
            target_actor=target,
            source_work=source_work,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, identity)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), identity)
    pass_tags(game)
    return identity


def free_chat(worker, gateway):
    tick(worker, gateway, 5)


def test_actual_mid_rouse_then_single_real_crushing_strike_preserves_intrinsic_and_retry(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    actor, target = current_ref(before, 2), current_ref(before, 3)
    intrinsic = next(x for x in before.sheets["2"].assets if x.intrinsic == "wyvern_enormous")
    status = before.order
    action = roll(game, worker, gateway)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    source = rules.records(state(game), rules.Session)[-1]
    assert source.total == 8 and rules.roused(state(game), actor).session == action
    free_chat(worker, gateway)
    with ledger.engine.connect() as c:
        actual_asset = next(
            x.id
            for x in resolve(state(game), target, profiles(c, ledger.campaign_id)).assets
            if not x.damaged
        )
    unchanged = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        controls.use_roused(
            PLAYER,
            "invalid-actual-strike-rolls-back",
            900,
            state(game).revision,
            target,
            "strike",
            asset="not-an-actual-Asset",
        )
    assert state(game).model_dump_json() == unchanged
    payload = (PLAYER, "one-real-roused-strike", 900, state(game).revision, target, "strike")
    result = controls.use_roused(*payload, asset=actual_asset)
    assert controls.use_roused(*payload, asset=actual_asset) == result
    canon = state(game)
    assert next(x for x in canon.sheets["3"].assets if x.id == actual_asset).damaged
    assert rules.roused(canon, actor) is None
    assert next(x for x in canon.sheets["2"].assets if x.id == intrinsic.id) == intrinsic
    assert canon.order == status and game.dice.calls == 1
    with ledger.engine.connect() as c:
        used = prove_use(game, c, canon, result["id"])
        assert used.target == target and used.asset == actual_asset and used.completed_event
    unchanged = canon.model_dump_json()
    with pytest.raises(WorkflowError):
        controls.use_roused(
            PLAYER, str(uuid4()), 900, canon.revision, target, "strike", asset=actual_asset
        )
    assert state(game).model_dump_json() == unchanged
    with pytest.raises(WorkflowError):
        controls.use_roused(OTHER, str(uuid4()), 900, canon.revision, actor, "pin")


def test_high_rouse_pays_two_actual_legal_erasures_and_owner_chosen_heat(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    action = roll(game, worker, gateway, faces=(6, 6))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "wyvern_rouse_cost")
    ids = tuple(x[0] for x in game.decision(PLAYER, row["id"])["detail"]["identities"][:2])
    old = {x.id for x in state(game).sheets["2"].identities}
    payload = (
        PLAYER,
        "high-rouse-exact-cost",
        row["id"],
        row["revision"],
        ChoiceAnswer(denied=ids, number=6, text="My actual original erasures and Heat"),
    )
    game.respond(*payload)
    game.respond(*payload)
    canon = state(game)
    assert old - {x.id for x in canon.sheets["2"].identities} == set(ids)
    assert canon.sheets["2"].heat == 9
    assert (
        rules.roused(canon, current_ref(canon, 2))
        and game.inspect(PLAYER, action)["state"] == "complete"
    )


def test_low_rouse_acts_last_without_status_change_until_real_unlink(ledger, tmp_path, monkeypatch):
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch)
    order = state(game).order
    action = roll(game, worker, gateway, faces=(1, 1))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "wyvern_rouse_cost")
    identity = game.decision(PLAYER, row["id"])["detail"]["identities"][0][0]
    answer(game, PLAYER, "wyvern_rouse_cost", denied=(identity,))
    actor = current_ref(state(game), 2)
    assert rules.acts_last(state(game), actor) and state(game).order == order
    assert not rules.roused(state(game), actor)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    free_chat(worker, gateway)
    physical = PhysicalService(game.store)
    data = physical.preview(PLAYER)
    physical.operate(
        PLAYER,
        str(uuid4()),
        data["game_revision"],
        CockpitAction(
            actor=actor,
            operation="exit",
            expected_position=data["position_sha256"],
            account="I actually unlink and leave this cockpit",
            confirmed=True,
        ),
    )
    assert not rules.acts_last(state(game), actor) and state(game).order == order


def declare_party(game, controls, companions=()):
    result = controls.party(PLAYER, str(uuid4()), 900, state(game).revision, companions)
    for companion in companions:
        controls.attend(OTHER, str(uuid4()), result["id"], state(game).revision, (companion,))
    return result["id"]


def ask_and_answer(game, controls, action, *, questions=("engine",), danger=None):
    source = rules.records(state(game), rules.Session)[-1]
    chooser = ADMIN if source.total < 8 else PLAYER
    fields = {"danger": danger} if source.total < 8 else {}
    answer(game, chooser, "wyvern_questions", options=questions, fields=fields)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "wyvern_unmark")
    detail = game.decision(PLAYER, row["id"])["detail"]
    answer(
        game,
        PLAYER,
        "wyvern_unmark",
        denied=tuple(x[0] for x in detail["identities"][: detail["count"]]),
    )
    if source.total >= 11:
        answer(game, ADMIN, "wyvern_danger", options=(danger,))
    for question in rules.records(state(game), rules.Question):
        if question.session != action:
            continue
        controls.answer(
            PLAYER,
            str(uuid4()),
            question.id,
            state(game).revision,
            "My own Frame voice answer, including its exact trailing detail.\n" * 40,
        )
        controls.answer(
            OTHER,
            str(uuid4()),
            question.id,
            state(game).revision,
            "A distinct actual table human's additional contribution",
        )
    answer(game, PLAYER, "wyvern_answers_done", options=("done",))


def test_mid_exploration_actual_companion_attendance_and_lossless_private_frame_answers(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    companion = current_ref(state(game), 3)
    party = controls.party(PLAYER, str(uuid4()), 900, state(game).revision, (companion,))["id"]
    with pytest.raises(WorkflowError):
        roll(game, worker, gateway, play="wyvern_explore", source_work=party)
    controls.attend(OTHER, str(uuid4()), party, state(game).revision, (companion,))
    action = roll(game, worker, gateway, play="wyvern_explore", source_work=party)
    ask_and_answer(game, controls, action)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    saved = controls.view(OTHER, action)
    assert len(saved["questions"][0]["answers"]) == 2
    assert saved["questions"][0]["answers"][0]["text"].endswith("trailing detail.\n" * 1)
    assert controls.view(OTHER, action) == saved
    assert not any(
        x.session == action and not x.ended_event
        for x in rules.records(state(game), rules.InteriorGuest)
    )
    with ledger.engine.connect() as c:
        assert resolve(state(game), companion, profiles(c, ledger.campaign_id)).cell == (0, 0)


def test_high_exploration_two_questions_wait_actual_original_handler_elapsed_time(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    party = declare_party(game, controls)
    action = roll(game, worker, gateway, play="wyvern_explore", source_work=party, faces=(6, 6))
    ask_and_answer(game, controls, action, questions=("engine", "halls"), danger="delay")
    source = rules.records(state(game), rules.Session)[-1]
    assert game.inspect(PLAYER, action)["state"] != "complete" and len(source.questions) == 2
    with pytest.raises(WorkflowError):
        controls.elapsed(
            PLAYER, str(uuid4()), source.danger, state(game).revision, "I claim time has passed"
        )
    controls.elapsed(
        ADMIN,
        "actual-time-before-safe-return",
        source.danger,
        state(game).revision,
        "We spend the actual remaining scene interval finding the safe return route",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert next(
        x for x in rules.records(state(game), rules.Danger) if x.id == source.danger
    ).returned_event


def test_low_exploration_handler_choice_then_genuine_escape_keep_and_its_real_results(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    party = declare_party(game, controls)
    parent = roll(game, worker, gateway, play="wyvern_explore", source_work=party, faces=(1, 1))
    ask_and_answer(game, controls, parent, questions=("panel",), danger="escape")
    source = rules.records(state(game), rules.Session)[-1]
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    game.dice.faces = (3, 4)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=1,
            parent=parent,
            source_work=source.danger,
            context="I keep my head to negotiate the actual trapped return route",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, child)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), child)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("sexy",))
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="The actual completed escape retains its ordinary consequences",
    )
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    danger = next(x for x in rules.records(state(game), rules.Danger) if x.id == source.danger)
    assert danger.child == child and danger.child_completed_event and danger.returned_event


def test_deep_exploration_real_payment_adds_exact_two_source_questions(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    payload = (
        PLAYER,
        "actual-deep-purchase",
        state(game).revision,
        rules.DEEP,
        "I voluntarily buy my two new Frame questions",
    )
    result = controls.purchase(
        *payload,
        questions=("Who painted the oldest corridor?", "What remains under the sealed floor?"),
    )
    assert (
        controls.purchase(
            *payload,
            questions=("Who painted the oldest corridor?", "What remains under the sealed floor?"),
        )
        == result
    )
    canon = state(game)
    assert canon.sheets["2"].permissions == 18
    extra = next(x for x in rules.records(canon, rules.DeepQuestions) if x.receipt == result["id"])
    assert set(extra.questions) <= set(rules.questions(canon, current_ref(canon, 2)).values())
    party = declare_party(game, controls)
    action = roll(game, worker, gateway, play="wyvern_explore", source_work=party)
    custom = rules.identity("question", extra.id, "0")
    ask_and_answer(game, controls, action, questions=(custom,))
    assert game.inspect(PLAYER, action)["state"] == "complete"


@pytest.mark.parametrize("kind", ["contraband", "past", "void"])
def test_renovation_actual_room_and_girl_asset_with_handler_past_answer_and_void_work(
    ledger, tmp_path, monkeypatch, kind
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    result = buy(
        controls,
        rules.RENOVATE,
        room="The original kitchen",
        kind=kind,
        name="Recovered keepsake",
        description="A small physical keepsake from this original Frame",
    )
    value = next(x for x in rules.records(state(game), rules.Renovation) if x.id == result["id"])
    with pytest.raises(WorkflowError):
        controls.view(OTHER, value.id)
    if kind == "past":
        assert not value.completed_event and not value.asset
        with pytest.raises(WorkflowError):
            controls.past_answer(
                PLAYER, str(uuid4()), value.id, state(game).revision, "Someone else's past"
            )
        controls.past_answer(
            ADMIN,
            str(uuid4()),
            value.id,
            state(game).revision,
            "It is the badge I lost on the evacuation ship",
        )
    canon = state(game)
    value = next(x for x in rules.records(canon, rules.Renovation) if x.id == value.id)
    assert canon.sheets["2"].permissions == before.sheets["2"].permissions - 2
    actual = next(x for x in canon.sheets["2"].assets if x.id == value.asset)
    assert actual.family == "girl" and actual.void == (kind == "void")
    assert bool(value.completed_event) or value.work
    assert not any(x.family == "frame" and x.id == actual.id for x in canon.sheets["2"].assets)


@pytest.mark.parametrize(
    "tier,faces,slot",
    [("mid", (3, 4), "gunner"), ("high", (6, 6), "captain"), ("low", (1, 1), "battery")],
)
def test_real_frame_wraith_tiers_actual_handler_rules_tag_and_table_play(
    ledger, tmp_path, monkeypatch, tier, faces, slot
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    buy(controls, rules.WRAITH)
    action = roll(game, worker, gateway, play="wyvern_wraith", faces=faces)
    answer(
        game,
        ADMIN if tier == "low" else PLAYER,
        "wyvern_wraith",
        options=(slot,),
        fields={} if slot == "battery" else {"name": "Original mind"},
    )
    fields = {"tag": "Still here"} if tier != "mid" else {}
    answer(
        game,
        ADMIN,
        "wyvern_wraith_rules",
        options=("frame_bound_npc",),
        fields=fields,
        text="A Frame-bound NPC mind; only the named host bonus, real Tags, "
        "and its actual human-authored role",
    )
    canon = state(game)
    mind = rules.records(canon, rules.Wraith)[-1]
    assert game.inspect(PLAYER, action)["state"] == "complete" and mind.persona.kind == "npc"
    assert mind.active and mind.stubborn == (tier == "high")
    npc = next(x for x in canon.world.npcs if x.id == mind.persona.entity)
    assert npc.source_kind == "wyvern_wraith" and npc.jobs == ()
    assert (mind.name == "Sarah") == (slot == "battery")
    assert bool(mind.tag) == (tier != "mid")
    relevant = rules.BONUSES[slot][0]
    assert rules.wraith_bonus(canon, current_ref(canon, 2), relevant) == 1
    free_chat(worker, gateway)
    controls.voice(
        OTHER,
        str(uuid4()),
        mind.id,
        state(game).revision,
        "My own actual table contribution",
        take_control=True,
    )
    assert controls.view(PLAYER, mind.id)["voices"][-1]["author"] == OTHER.user_id
    assert (
        next(x for x in state(game).world.npcs if x.id == mind.persona.entity).controller
        == OTHER.user_id
    )
    if tier == "high":
        with pytest.raises(WorkflowError):
            controls.dismiss(PLAYER, str(uuid4()), mind.id, state(game).revision)
    else:
        controls.dismiss(PLAYER, str(uuid4()), mind.id, state(game).revision)
        assert not rules.wraith_bonus(state(game), current_ref(state(game), 2), relevant)


def test_protector_mid_real_shield_and_recipient_bond_choice_then_real_movement_end(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    buy(controls, rules.PROTECT)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    before = depth(state(game), actor, target)
    action = roll(game, worker, gateway, play="wyvern_protector", target=target)
    answer(game, OTHER, "wyvern_shield_bond", options=("deepen",))
    assert depth(state(game), actor, target) == before + 1
    assert (
        rules.shielded(state(game), target) and game.inspect(PLAYER, action)["state"] == "complete"
    )
    free_chat(worker, gateway)
    with pytest.raises(WorkflowError, match="[Ss]hield"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="put_someone_beneath_you",
                target_actor=target,
                heat=0,
                context="I try an actual Play against the protected person",
                trigger_confirmed=True,
            ),
        )
    from girlframe.services.m3_movement import MovementService

    MovementService(game).move(
        OTHER,
        str(uuid4()),
        state(game).revision,
        900,
        target,
        (1, 0),
        frame=False,
        account="I actually move away from the protected position",
    )
    assert not rules.shielded(state(game), target)


def test_protector_high_actual_approacher_owns_give_up_and_optional_tag(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    buy(controls, rules.PROTECT)
    from test_enforcement_initiative import cast_target

    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_world import WorldService

    WorldService(MissionService(ledger)).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="actual-approacher",
            name="Actual approaching person",
            jobs=("civilian",),
            detail="A real person in the source scene",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    approaching = ActorRef(kind="npc", entity="actual-approacher")
    cast_target(game, approaching)
    target = current_ref(state(game), 3)
    action = roll(game, worker, gateway, play="wyvern_protector", target=target, faces=(6, 6))
    canon = state(game)
    shield = rules.records(canon, rules.Shield)[-1]
    assert shield.high and game.inspect(PLAYER, action)["state"] == "complete"
    free_chat(worker, gateway)
    attempt = controls.approach(
        ADMIN,
        str(uuid4()),
        shield.id,
        canon.revision,
        approaching,
        "I actually approach the protected person and see it is hopeless",
    )
    payload = (ADMIN, "actual-give-up-tag", attempt["id"], state(game).revision)
    controls.give_up(*payload, tag="An immovable shield")
    controls.give_up(*payload, tag="An immovable shield")
    tags = state(game).sheets["2"].tags
    assert any(x.label == "An immovable shield" and x.giver_actor == approaching for x in tags)


def test_protector_low_weakens_actual_bond_and_original_handler_performs_real_play(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    buy(controls, rules.PROTECT)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    before = depth(state(game), actor, target)
    action = roll(game, worker, gateway, play="wyvern_protector", target=target, faces=(1, 1))
    canon = state(game)
    assert depth(canon, actor, target) == max(0, before - 1) and not rules.shielded(canon, target)
    assert game.inspect(PLAYER, action)["state"] != "complete"
    grant = next(x for x in canon.handler_plays if x.source_action == action)
    handler = HandlerPlayService(ledger)
    handler.submit(
        ADMIN,
        str(uuid4()),
        grant.id,
        canon.revision,
        "brief",
        Effect(kind="brief", account="The actual source Handler makes the real printed Play"),
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_actual_leviathan_chassis_carries_original_other_frame_after_real_owner_accepts(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    target = current_ref(state(game), 3)
    proposed = controls.propose_cargo(PLAYER, str(uuid4()), 900, state(game).revision, target)
    with pytest.raises(WorkflowError):
        controls.accept_cargo(PLAYER, str(uuid4()), proposed["id"], state(game).revision)
    payload = (OTHER, "actual-owner-cargo", proposed["id"], state(game).revision)
    result = controls.accept_cargo(*payload)
    assert controls.accept_cargo(*payload) == result
    value = next(x for x in rules.records(state(game), rules.Cargo) if x.id == proposed["id"])
    assert (
        value.accepted_event
        and value.boarded_event
        and rules.cargo(state(game), target, value.guest_frame)
    )
    from girlframe.services.m3_movement import MovementService

    MovementService(game).move(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        current_ref(state(game), 2),
        (1, 0),
        frame=True,
        account="I actually transport the other physical Frame inside my Wyvern",
    )
    with ledger.engine.connect() as c:
        guest = resolve(state(game), target, profiles(c, ledger.campaign_id))
        assert guest.frame_cell == (1, 0) and guest.cell == (0, 0)
    controls.unload(PLAYER, str(uuid4()), value.id, state(game).revision)
    assert not rules.cargo(state(game), target, value.guest_frame)
    with ledger.engine.connect() as c:
        guest = resolve(state(game), target, profiles(c, ledger.campaign_id))
        assert guest.frame_cell == (1, 0) and guest.cell == (0, 0)


def test_chassis_keep_adds_actual_big_enough_without_replacing_ordinary_traits(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch)
    game.dice.faces = (3, 4)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=1,
            piloting=True,
            context="I keep my head while actually piloting my huge original Wyvern",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("sexy",))
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="Its true bulk and the actual selected traits are enough",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    with ledger.engine.connect() as c:
        result = game.action(c, action)["data"]["result"]
    assert {"big_enough", "tough", "in_control"} <= set(result["positive"])
    assert result["negative"] == ["sexy"] and game.dice.calls == 1
