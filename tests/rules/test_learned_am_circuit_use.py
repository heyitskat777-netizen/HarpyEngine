"""Genuine retained AM lessons: actual baseline change, medical exchange, owned source use."""

import asyncio
from uuid import uuid4

import pytest
from test_consume import cockpit
from test_enforcement_initiative import cast_target
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current
from test_vatgrown_plays import _learn_daily_source, ready

from girlframe.discord_adapter.m3_handler_recovery import open_handler_recovery
from girlframe.engine import m3_am as scrutiny
from girlframe.engine import m3_am_code as code
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_girl_transition_state import Plan
from girlframe.engine.m3_medical import Care, Exchange
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_am_code import CodeService
from girlframe.services.m3_am_code import source as code_source
from girlframe.services.m3_am_scrutinized import ScrutinyService
from girlframe.services.m3_am_scrutinized import source as discovery_source
from girlframe.services.m3_girl_transition import GirlTransitionService
from girlframe.services.m3_handler_recovery import HandlerRecoveryService
from girlframe.services.m3_learned_plays import available, prove_consumed
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

BORROWED = "girl.princess.objectively-beautiful"


def defeat_source(game, worker, gateway, faces):
    """The actual counterattack destroys the last surviving Frame Asset, then Defeat."""
    with game.store.transaction() as c:
        canon = state(game)
        # These are prior physical equipment facts between separate episodes,
        # never a fabricated learning grant, medical completion or AM relabel.
        frames = [x for x in canon.sheets["2"].assets if x.family == "frame"]
        for number, asset in enumerate(frames):
            asset.damaged = number != 0
        game.event(
            c, 1, str(uuid4()), "synthetic.prior_repaired_frame_and_actual_other_damage", canon
        )
    if (
        next(x for x in state(game).placements if x.actor == current_ref(state(game), 2)).mode
        != "piloting"
    ):
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
            context="Actual source confrontation while piloting the original Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("damage",),
        text="Actual source counterattack against her final Frame Asset",
    )
    answer(game, PLAYER, "beneath_details", denied=(frames[0].id,))
    game.dice.faces = faces
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            heat=0,
            parent=parent,
            context="Real Defeat required by that original counterattack",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return child


def retained_nonpermanent_am(game, worker, gateway, lesson, rule):
    """Keep the actual acquired lesson through real Defeat transition and medical exchange."""
    original = current_ref(state(game), 2)
    defeat_source(game, worker, gateway, (1, 1))
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("change_girl_playbook",),
        fields={"girl_playbook": "AM"},
        text="The actual original Girl changes baseline",
    )
    tick(worker, gateway, 6)
    transitions = GirlTransitionService(game.store)
    task = transitions.tasks(PLAYER)[0]
    data = transitions.get(PLAYER, task["id"])
    transitions.configure(
        PLAYER,
        str(uuid4()),
        task["id"],
        data["revision"],
        Plan(account="Actual same-person artificial-mind baseline"),
    )
    data = transitions.get(PLAYER, task["id"])
    transitions.finalize(PLAYER, str(uuid4()), task["id"], data["revision"], data["game_revision"])
    assert current_ref(state(game), 2) == original and state(game).sheets["2"].girl == "AM"
    assert any(x.id == lesson.id for x in state(game).sheets["2"].girl_runtime.learned_plays)

    defeat_source(game, worker, gateway, (3, 3))
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("handler_rescue_swap_girl_play_on_waking",),
        text="Actual rescue, injury and source-bound medical recovery",
    )
    tick(worker, gateway, 6)
    medical = MedicalService(game.store)
    work = medical.tasks(PLAYER)[0]["id"]
    data = medical.get(PLAYER, work)
    medical.propose(
        PLAYER,
        str(uuid4()),
        work,
        data["revision"],
        Care(account="Actual treatment and waking of the original artificial Girl"),
    )
    data = medical.get(ADMIN, work)
    medical.confirm(
        ADMIN,
        str(uuid4()),
        work,
        data["revision"],
        data["game_revision"],
        True,
        "I confirm actual care and restored consciousness",
    )
    data = medical.get(PLAYER, work)
    medical.exchange(
        PLAYER,
        str(uuid4()),
        work,
        data["revision"],
        data["game_revision"],
        Exchange(removed=rule, acquired=BORROWED),
    )
    actual = state(game)
    own = actual.sheets["2"]
    assert own.girl == "AM" and own.medical_state == "fit"
    assert has_rule(own, rule, "AM")  # The real remaining temporary lesson.
    permanent = own.model_copy(
        update={"girl_runtime": own.girl_runtime.model_copy(update={"learned_plays": ()})}
    )
    assert not has_rule(permanent, rule, "AM")
    with game.store.engine.connect() as c:
        actual_lesson = available(game, c, actual, original, rule)
    assert actual_lesson.id == lesson.id and actual_lesson.rolled_event is None
    # The actual Handler rescue owns real custody after waking. Record their
    # genuinely unknown initial presence, then release only that original hold.
    recovery = HandlerRecoveryService(game)
    work = next(x["id"] for x in recovery.tasks(ADMIN) if x["pending"])
    data = recovery.get(ADMIN, work)
    if data["may_record_presence"]:
        recovery.record_initial_presence(
            ADMIN,
            str(uuid4()),
            work,
            data["revision"],
            (0, 0),
            "I witness my previously unknown actual location beside the recovered original body",
        )
    data = recovery.get(ADMIN, work)
    recovery.propose(
        ADMIN,
        str(uuid4()),
        work,
        data["revision"],
        "The actual care and required exchange are complete; I release her here",
    )
    proposed = recovery.get(PLAYER, work)
    with pytest.raises(WorkflowError):
        recovery.confirm(
            OTHER,
            str(uuid4()),
            work,
            proposed["revision"],
            proposed["proposal"]["event"],
            "Not the original patient",
        )
    key = str(uuid4())
    confirmation = (
        PLAYER,
        key,
        work,
        proposed["revision"],
        proposed["proposal"]["event"],
        "I confirm this same original vessel was released at the actual witnessed cell",
    )
    released = recovery.confirm(*confirmation)
    assert recovery.confirm(*confirmation) == released
    assert recovery.get(PLAYER, work)["phase"] == "released"
    released_pose = next(x for x in state(game).placements if x.actor == original)
    assert released_pose.vessel_id == proposed["vessel"] and released_pose.custody is None
    assert released_pose.girl_cell == (0, 0) and released_pose.mode == "outside_frame"


def learned_context(ledger, tmp_path, monkeypatch, rule):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="AM")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, scrutiny.RULE, code.RULE, BORROWED),
    )
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, rule)
    retained_nonpermanent_am(game, worker, gateway, lesson, rule)
    npc = ActorRef(kind="npc", entity="actual-learned-am-discoverer")
    WorldService(MissionService(ledger)).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Actual maintenance witness",
            jobs=("mechanic",),
            controller=1,
            detail="Actual source NPC newly recognizing the adjustment",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_target(game, npc)
    return game, worker, gateway, lesson, npc


def discovery_roll(game, worker, gateway, npc):
    source = ScrutinyService(game)
    identity = source.propose(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "The actual source NPC newly notices my adjustment",
    )["id"]
    root = source.confirm(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        True,
        True,
        "Actual new recognition confirmed by the NPC owner",
    )["action_id"]
    tick(worker, gateway, 3)
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=scrutiny.PLAY,
            parent=root,
            source_work=identity,
            target_actor=npc,
            heat=0,
            context="Actual response to the original newly confirmed discovery",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "am_select",
        options=("secret",),
        text="PRIVATE_SOURCE_SECRET Please keep my actual adjustment secret",
    )
    tick(worker, gateway, 5)
    return source, identity, root, action


def consumed_lesson(game, lesson, action):
    actual = state(game)
    saved = next(x for x in actual.sheets["2"].girl_runtime.learned_plays if x.id == lesson.id)
    assert saved.claimed_action == action and saved.rolled_event is not None
    with game.store.engine.connect() as c:
        source_action = game.action(c, action)
        assert prove_consumed(game, c, actual, source_action, lesson.rule_id, saved.rolled_event)
        assert available(game, c, actual, current_ref(actual, 2), lesson.rule_id) is None
    return saved


def test_real_retained_scrutinized_lesson_rolls_once_after_native_medical_removal(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, lesson, npc = learned_context(
        ledger, tmp_path, monkeypatch, scrutiny.RULE
    )
    before_calls = game.dice.calls
    source, identity, root, action = discovery_roll(game, worker, gateway, npc)
    saved = consumed_lesson(game, lesson, action)
    actual = state(game)
    assert game.dice.calls == before_calls + 1
    assert depth(actual, current_ref(actual, 2), npc) == 1
    receipt = game.inspect(PLAYER, action)["receipt"]
    with ledger.engine.connect() as c:
        value = discovery_source(game, c, actual, identity)
        assert scrutiny.holds_secret(actual, value)
    assert game.inspect(PLAYER, root)["state"] == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert identity in {x["id"] for x in source.menu(PLAYER, 900)["discoveries"]}
    assert identity not in {x["id"] for x in source.menu(OTHER, 900)["discoveries"]}
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert consumed_lesson(game, lesson, action) == saved


def test_real_retained_just_code_lesson_performs_owned_rewrite_once_and_reopens_privately(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, lesson, npc = learned_context(ledger, tmp_path, monkeypatch, code.RULE)
    _, discovery, _, _ = discovery_roll(game, worker, gateway, npc)
    # The still-native Scrutinized Play must not spend the separate Just Code lesson.
    with ledger.engine.connect() as c:
        assert (
            available(game, c, state(game), current_ref(state(game), 2), code.RULE).id == lesson.id
        )
    source = CodeService(game)
    identity = source.propose(
        PLAYER,
        str(uuid4()),
        discovery,
        state(game).revision,
        "Actual known operator performs identity-only maintenance",
    )["id"]
    root = source.confirm(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        "My actual NPC has real circuit access to this original body",
    )["action_id"]
    tick(worker, gateway, 3)
    before_calls = game.dice.calls
    selected = code.choices(state(game), current_ref(state(game), 2))[0]
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=code.PLAY,
            parent=root,
            source_work=identity,
            target_actor=npc,
            heat=0,
            context="Actual source-confirmed circuit maintenance",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, ADMIN, "am_code_options", options=("identities",))
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "am_code_edit")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("edit",), fields={selected.id: "Forged"}),
        )
    key = str(uuid4())
    details = ChoiceAnswer(
        options=("edit",),
        fields={selected.id: "Self-directed"},
        text="PRIVATE_CODE_DETAILS Actual source operator owns this rewrite",
    )
    result = game.respond(ADMIN, key, row["id"], row["revision"], details)
    assert game.respond(ADMIN, key, row["id"], row["revision"], details) == result
    saved = consumed_lesson(game, lesson, action)
    actual = state(game)
    session = code.session(actual, identity)
    replacement = next(
        x for x in actual.sheets["2"].identities if x.id == session.replacements[selected.id]
    )
    assert replacement.name == "Self-directed" and replacement.slot == selected.slot
    assert game.dice.calls == before_calls + 1
    assert (
        game.inspect(PLAYER, action)["state"] == game.inspect(PLAYER, root)["state"] == "complete"
    )
    with ledger.engine.connect() as c:
        assert code_source(game, c, actual, identity) == session
    assert identity in {x["id"] for x in source.menu(PLAYER, 900)["sessions"]}
    assert identity not in {x["id"] for x in source.menu(OTHER, 900)["sessions"]}
    assert consumed_lesson(game, lesson, action) == saved


def test_high_actual_handler_rescue_native_discharge_keeps_body_frame_and_private_history(ledger):
    from test_defeat_service import rolled

    game, worker, gateway, _, action = rolled(ledger, faces=(6, 6))
    from test_world import initial

    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial()
        game.event(c, 1, str(uuid4()), "synthetic.initial_handler_recovery_map", canon)
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("lower_status", "another_girl_gives_tag"),
        fields={"tag_giver": "3"},
        text="Actual original Handler rescue",
    )
    answer(game, OTHER, "defeat_tag_gift", options=("give",), text="Survivor")
    tick(worker, gateway, 6)
    controls = HandlerRecoveryService(game)
    identity = controls.tasks(PLAYER)[0]["id"]
    assert not controls.tasks(PLAYER)[0]["actionable"]
    assert controls.tasks(ADMIN)[0]["actionable"]
    before = state(game)
    original = current_ref(before, 2)
    pose = next(x for x in before.placements if x.actor == original)

    async def native(viewer, operation, **answers):
        screen = current(viewer.user_id, int(uuid4().int % 1000000000))
        await screen.response.defer(ephemeral=True)
        await open_handler_recovery(screen, controls, identity)
        choose = screen.edit_original_response.call_args.kwargs["view"]
        choose.values.update(action=(operation,))
        selected = current(viewer.user_id, int(uuid4().int % 1000000000))
        await choose.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(answers)
        submitted = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    if controls.get(ADMIN, identity)["may_record_presence"]:
        asyncio.run(
            native(
                ADMIN,
                "presence",
                cell=("0,0",),
                account="My actual previously unknown initial presence beside her",
            )
        )
    asyncio.run(
        native(ADMIN, "propose", account="I actually release this recovered original body here")
    )
    with pytest.raises(WorkflowError):
        controls.get(OTHER, identity)
    proposed = controls.get(PLAYER, identity)
    snapshot = state(game)
    with pytest.raises(WorkflowError):
        controls.confirm(
            PLAYER,
            str(uuid4()),
            identity,
            proposed["revision"],
            "wrong-proposal",
            "This is not the original witnessed source",
        )
    assert state(game) == snapshot
    asyncio.run(
        native(
            PLAYER, "confirm", account="PRIVATE_RELEASE_FACT I confirm my body was released here"
        )
    )
    shown = HandlerRecoveryService(game).get(PLAYER, identity)
    assert (
        shown["phase"] == "released"
        and shown["release"]["proposal"] == proposed["proposal"]["event"]
    )
    actual = state(game)
    released = next(x for x in actual.placements if x.actor == original)
    assert released.vessel_id == pose.vessel_id and released.frame_cell == pose.frame_cell
    assert released.frame_instance == pose.frame_instance and released.custody is None
    assert actual.sheets == before.sheets and actual.frame_locks == before.frame_locks
    assert controls.tasks(PLAYER) == []
