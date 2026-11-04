"""Real transactional Observation uses the shared RNG, locks and private work queue."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_frame_reward_service import own as frame_work
from test_frame_reward_service import submit as frame_submit
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, Gateway, pass_tags, state, tick
from test_off_duty_cycle import activate, call, prepared

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_frame_rewards import Claim
from girlframe.engine.m3_observation_state import Details
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_punishments import Details as Punishment
from girlframe.services.inbox import InboxService
from girlframe.services.m3_frame_rewards import RewardService
from girlframe.services.m3_observation import ObservationService, work_id
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def setup(store, *, faces=(1, 1), hiding=True):
    cycle, game, period = prepared(store)
    activate(cycle, game, period)
    svc = ObservationService(cycle.periods)
    current = cycle.review(ADMIN, period)
    svc.order(
        ADMIN,
        "observation-order",
        period,
        current["revision"],
        state(game).revision,
        2,
        hiding,
        "PRIVATE_OBSERVATION_SUSPICION",
    )
    game.dice = Dice(faces)
    return svc, cycle, game, period


def roll_for(svc, game, period):
    before = state(game)
    action = game.begin(
        PLAYER,
        "observation-begin",
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="void_observation",
            off_duty_id=period,
            heat=0,
            context="Actual observation",
            trigger_confirmed=True,
        ),
    )["action_id"]
    assert state(game).order == before.order and game.dice.calls == 0
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    pass_tags(game)
    tick(worker, gateway, 8)
    return action


def select(svc, actor, period, values, key=None):
    data = svc.get(actor, work_id(period, 2, actor.user_id))
    return svc.select(
        actor,
        key or str(uuid4()),
        period,
        data["period_revision"],
        data["game_revision"],
        2,
        values,
    )


def pending(svc, actor, period):
    return next(
        x["id"]
        for x in svc.periods.get(actor, period)["work"]
        if x["kind"] == "observation_effect"
        and svc.get(actor, x["id"])["owner_id"] == str(actor.user_id)
    )


def apply(svc, actor, identity, details, key=None):
    data = svc.get(actor, identity)
    return svc.apply(
        actor,
        key or str(uuid4()),
        identity,
        data["revision"],
        data["period_revision"],
        data["game_revision"],
        details,
    )


def test_order_forces_substitution_and_status_changes_only_with_locked_actual_roll(ledger):
    svc, cycle, game, period = setup(ledger)
    before = state(game)
    with pytest.raises(WorkflowError, match="replaces"):
        game.begin(
            PLAYER,
            "cannot-roll-ordinary",
            900,
            before.sheets["2"].revision,
            PlayInput(
                play="go_off_duty",
                off_duty_id=period,
                heat=0,
                context="An ordinary attempt",
                trigger_confirmed=True,
            ),
        )
    action = roll_for(svc, game, period)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["base_modifier"] == 0 and receipt["modifier_source"] == "Void Assets"
    assert receipt["pre_total"] == 2 and state(game).order == (3, 2)
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    assert game.dice.calls == 1
    with pytest.raises(WorkflowError):
        roll_for(svc, game, period)
    assert game.dice.calls == 1
    assert InboxService(ledger).page(PLAYER, category="off_duty").total >= 1
    assert any(x.task == "m3_observation" for x in InboxService(ledger).items(PLAYER))
    with ledger.engine.connect() as c:
        assert "PRIVATE_OBSERVATION_SUSPICION" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )


@pytest.mark.parametrize("faces,count", [((1, 1), 0), ((4, 4), 1), ((6, 6), 2)])
def test_separate_handler_choice_count_and_private_task_ownership(ledger, faces, count):
    svc, _, game, period = setup(ledger, faces=faces)
    roll_for(svc, game, period)
    identity = work_id(period, 2, 2)
    assert svc.get(PLAYER, identity)["count"] == 1
    with pytest.raises(WorkflowError, match="other participants"):
        svc.get(OTHER, identity)
    if count:
        data = svc.get(ADMIN, work_id(period, 2, 1))
        assert data["count"] == count
        with pytest.raises(WorkflowError):
            select(svc, ADMIN, period, ())
    else:
        with pytest.raises(WorkflowError):
            svc.get(ADMIN, work_id(period, 2, 1))
    select(svc, PLAYER, period, ("hospital_stay",))
    if count:
        assert "hospital_stay" not in svc.get(ADMIN, work_id(period, 2, 1))["options"]


def test_actual_effect_scene_and_frame_review_gate_recovery_then_preserve_one_roll(ledger):
    svc, cycle, game, period = setup(ledger)
    action = roll_for(svc, game, period)
    select(svc, PLAYER, period, ("harpy_candidate_tag",))
    effect = pending(svc, PLAYER, period)
    with pytest.raises(WorkflowError):
        apply(svc, ADMIN, effect, Details(account="Cannot choose for the player"))
    apply(svc, PLAYER, effect, Details(account="Printed candidate designation"), "candidate-once")
    assert state(game).sheets["2"].tags[-1].label == "Harpy Candidate"
    with pytest.raises(WorkflowError):
        call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    call(
        cycle,
        game,
        PLAYER,
        period,
        "scene",
        "observation:harpy_candidate_tag",
        (2, 1),
        "Actual shared scene",
    )
    call(cycle, game, PLAYER, period, "acknowledge", 2)
    assert any(
        x.kind == "void_observation" and x.state == "pending" for x in state(game).obligations
    )
    call(cycle, game, ADMIN, period, "acknowledge", 2)
    assert not any(
        x.kind == "void_observation" and x.state == "pending" for x in state(game).obligations
    )
    rewards = RewardService(svc.periods)
    frame_submit(
        rewards,
        PLAYER,
        frame_work(rewards, PLAYER, period)["id"],
        Claim(fulfilled=False, account="No Frame trigger"),
    )
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    assert cycle.review(PLAYER, period)["own"]["recovered"] and game.dice.calls == 1
    assert game.inspect(PLAYER, action)["receipt"]["pre_total"] == 2


def test_moderate_consequence_requires_actual_moderate_effect_not_minor_or_scene_only(ledger):
    svc, cycle, game, period = setup(ledger)
    roll_for(svc, game, period)
    select(svc, PLAYER, period, ("moderate_punishment",))
    discipline = PunishmentService(ledger)
    task = next(x for x in svc.periods.get(ADMIN, period)["work"] if x["kind"] == "punishment")
    data = discipline.get(ADMIN, task["id"])
    with pytest.raises(WorkflowError, match="actual severity"):
        discipline.apply(
            ADMIN,
            "cannot-substitute-minor",
            task["id"],
            data["revision"],
            data["game_revision"],
            Punishment(kind="demotion"),
        )
    discipline.apply(
        ADMIN,
        "real-moderate",
        task["id"],
        data["revision"],
        data["game_revision"],
        Punishment(kind="libido_inhibitor"),
    )
    assert state(game).sheets["2"].libido_inhibited
    assert cycle.review(PLAYER, period)["own"]["observation"]["outcomes"][0]["resolved"]
    assert any(
        x.kind == "void_observation" and x.state == "pending" for x in state(game).obligations
    )


def test_effect_rollback_pause_and_stale_revisions_do_not_duplicate_or_lose_requests(
    ledger, monkeypatch
):
    svc, _, game, period = setup(ledger)
    roll_for(svc, game, period)
    select(svc, PLAYER, period, ("harpy_candidate_tag",))
    identity = pending(svc, PLAYER, period)
    before = state(game)
    original = svc.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic post-event failure")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError):
        apply(svc, PLAYER, identity, Details(account="Actual consequence"), "retry")
    assert state(game) == before and svc.get(PLAYER, identity)["state"] == "pending"
    monkeypatch.setattr(svc.game, "event", original)
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        apply(svc, PLAYER, identity, Details(account="Actual consequence"), "retry")
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    data = svc.get(PLAYER, identity)
    args = (
        PLAYER,
        "retry",
        identity,
        data["revision"],
        data["period_revision"],
        data["game_revision"],
        Details(account="Actual consequence"),
    )
    result = svc.apply(*args)
    assert svc.apply(*args) == result
    assert len(state(game).sheets["2"].tags) == len(before.sheets["2"].tags) + 1


def test_unrolled_cancel_preserves_observation_order_and_does_not_lower_status(ledger):
    from girlframe.services.m3_play_support import cancel_unrolled

    svc, cycle, game, period = setup(ledger)
    before = state(game)
    action = game.begin(
        PLAYER,
        "unrolled-begin",
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="void_observation",
            off_duty_id=period,
            heat=0,
            context="Observed",
            trigger_confirmed=True,
        ),
    )["action_id"]
    game.abort(ADMIN, "abort-before-acquire", action)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 5)
    cancel_unrolled(
        game, PLAYER, "cancel-unrolled", action, game.inspect(PLAYER, action)["revision"]
    )
    progress = cycle.review(PLAYER, period)["own"]
    assert progress["observation"] is not None and progress["action_id"] is None
    assert state(game).order == before.order and game.dice.calls == 0
    roll_for(svc, game, period)
    assert game.dice.calls == 1 and state(game).order == (3, 2)


def test_known_observation_roll_resumes_without_a_second_status_drop_or_new_dice(ledger):
    from test_m2_game import answer

    from girlframe.services.m3_play_support import resume

    svc, _, game, period = setup(ledger)
    before = state(game)
    action = game.begin(
        PLAYER,
        "interrupted-begin",
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="void_observation",
            off_duty_id=period,
            heat=0,
            context="Observed",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, action)["receipt"]
    answer(game, PLAYER, "tag_window", options=("pass",))
    game.abort(ADMIN, "abort-known-roll", action)
    tick(worker, gateway, 5)
    resume(game, PLAYER, "resume-known-roll", action, game.inspect(PLAYER, action)["revision"])
    tick(worker, gateway, 2)
    for actor in (ADMIN, OTHER):
        answer(game, actor, "tag_window", options=("pass",))
    tick(worker, gateway, 5)
    assert game.dice.calls == 1 and game.inspect(PLAYER, action)["receipt"] == receipt
    assert state(game).order == (3, 2)
    assert svc.get(PLAYER, work_id(period, 2, 2))["count"] == 1


def test_handler_may_review_hiding_after_roll_before_first_choices_but_cannot_change_committed_list(
    ledger,
):
    svc, cycle, game, period = setup(ledger, hiding=False)
    roll_for(svc, game, period)
    assert "reprogram" not in svc.get(PLAYER, work_id(period, 2, 2))["options"]
    data = cycle.review(ADMIN, period)
    svc.suspicion(
        ADMIN,
        "review-hiding",
        period,
        data["revision"],
        data["game_revision"],
        2,
        True,
        "The Handler now suspects concealment",
    )
    assert "reprogram" in svc.get(PLAYER, work_id(period, 2, 2))["options"]
    select(svc, PLAYER, period, ("reprogram",))
    task = pending(svc, PLAYER, period)
    original = state(game).sheets["2"]
    retain = next(x for x in original.identities if not x.protected)
    data = cycle.review(ADMIN, period)
    with pytest.raises(WorkflowError, match="committed"):
        svc.suspicion(
            ADMIN,
            "cannot-retcon-list",
            period,
            data["revision"],
            data["game_revision"],
            2,
            False,
            "Too late",
        )
    with pytest.raises(WorkflowError):
        apply(svc, ADMIN, task, Details(account="Not my Identity choice", identity=retain.id))
    defaults = svc.get(PLAYER, task)["starting_identities"]
    apply(
        svc,
        PLAYER,
        task,
        Details(
            account="I retain my current Identity",
            identity=retain.id,
            slot=None if "Malfunctioning" in defaults else defaults[0],
        ),
    )
    final = state(game).sheets["2"]
    assert retain.name in {x.name for x in final.identities}
    assert final.permissions == original.permissions and final.heat == original.heat


def director_for_observation(svc, game, period):
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_npc_roles import NpcRoleService
    from girlframe.services.m3_world import WorldService
    from girlframe.services.read_only_bot import GuildViewer

    actor = GuildViewer(4, 200, True, False)
    svc.store.join(actor, "join-director-player")
    roles = NpcRoleService(WorldService(svc.missions))
    result = roles.offer(
        ADMIN,
        "invite-director",
        state(game).revision,
        Npc(
            id="director",
            name="Separate Director",
            jobs=("director",),
            detail="Authority",
            controller=4,
            cell=(0, 0),
            revealed=True,
        ),
    )
    roles.respond(actor, "accept-director-role", result["id"], state(game).revision, "accept")
    roll_for(svc, game, period)
    select(svc, PLAYER, period, ("director_or_rival_arrives",))
    return actor, pending(svc, ADMIN, period)


def test_separate_director_must_answer_appearance_and_confirm_its_own_actual_scene(ledger):
    svc, cycle, game, period = setup(ledger)
    director, identity = director_for_observation(svc, game, period)
    result = apply(
        svc, ADMIN, identity, Details(npc="director", account="PRIVATE_SHARED_APPEARANCE")
    )
    assert result["awaiting_human"]
    assert not cycle.review(PLAYER, period)["own"]["observation"]["outcomes"][0]["resolved"]
    assert "PRIVATE_SHARED_APPEARANCE" not in str(svc.get(PLAYER, identity))
    with pytest.raises(WorkflowError):
        cycle.review(director, period)
    data = svc.get(director, identity)
    assert data["response_required"] and data["proposal_account"] == "PRIVATE_SHARED_APPEARANCE"
    with pytest.raises(WorkflowError):
        svc.answer_npc(
            OTHER,
            "cannot-play-director",
            identity,
            data["revision"],
            data["period_revision"],
            data["game_revision"],
            True,
        )
    result = svc.answer_npc(
        director,
        "actual-director-arrival",
        identity,
        data["revision"],
        data["period_revision"],
        data["game_revision"],
        True,
    )
    assert (
        svc.answer_npc(
            director,
            "actual-director-arrival",
            identity,
            data["revision"],
            data["period_revision"],
            data["game_revision"],
            True,
        )
        == result
    )
    assert cycle.review(PLAYER, period)["own"]["observation"]["outcomes"][0]["resolved"]
    with pytest.raises(WorkflowError):
        call(
            cycle,
            game,
            PLAYER,
            period,
            "scene",
            "observation:director_or_rival_arrives",
            (2, 1),
            "Cannot substitute Handler for Director",
        )
    call(
        cycle,
        game,
        PLAYER,
        period,
        "scene",
        "observation:director_or_rival_arrives",
        (2, 4),
        "Actual Director scene",
    )
    call(cycle, game, PLAYER, period, "acknowledge", 2)
    assert any(
        x.kind == "void_observation" and x.state == "pending" for x in state(game).obligations
    )
    assert any(x.task == "m3_off_duty" for x in InboxService(ledger).items(director))
    call(cycle, game, director, period, "acknowledge", 2)
    assert not any(
        x.kind == "void_observation" and x.state == "pending" for x in state(game).obligations
    )
    assert "4" not in state(game).sheets and state(game).order == (3, 2)
    required = [
        x for x in svc.periods.get(ADMIN, period)["work"] if x["kind"] == "director_presence"
    ]
    assert len(required) == 1
    with pytest.raises(WorkflowError, match="Handler/Girl"):
        call(
            cycle,
            game,
            ADMIN,
            period,
            "handler_scene",
            "routine",
            (1, 2),
            "Cannot skip the Director's rules",
        )


def test_declined_npc_appearance_returns_to_handler_without_fictional_effect(ledger):
    svc, cycle, game, period = setup(ledger)
    director, identity = director_for_observation(svc, game, period)
    apply(svc, ADMIN, identity, Details(npc="director", account="A proposed appearance"))
    data = svc.get(director, identity)
    svc.answer_npc(
        director,
        "return-appearance",
        identity,
        data["revision"],
        data["period_revision"],
        data["game_revision"],
        False,
    )
    assert svc.get(ADMIN, identity)["owner_id"] == "1"
    assert not cycle.review(PLAYER, period)["own"]["observation"]["outcomes"][0]["resolved"]
    assert not [x for x in state(game).facts if x.get("kind") == "observation_npc"]


def test_saved_npc_question_and_same_receipt_survive_rebuild_and_real_private_backup(
    ledger, tmp_path
):
    from pathlib import Path

    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_off_duty import OffDutyService
    from girlframe.services.onboarding import OnboardingStore

    svc, cycle, game, period = setup(ledger)
    director, identity = director_for_observation(svc, game, period)
    apply(svc, ADMIN, identity, Details(npc="director", account="Saved actual appearance proposal"))
    before = svc.get(director, identity)
    canon = state(game)
    game.rebuild()
    assert svc.get(director, identity) == before and state(game) == canon
    target = tmp_path / "observation-backup.db"
    copy_database(Path(ledger.engine.url.database), target)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(target)))
    try:
        restored = ObservationService(
            OffDutyService(
                MissionService(OnboardingStore(engine, ledger.policy), svc.missions.access.registry)
            )
        )
        assert restored.get(director, identity) == before
        result = restored.answer_npc(
            director,
            "restored-director-response",
            identity,
            before["revision"],
            before["period_revision"],
            before["game_revision"],
            True,
        )
        assert not result["awaiting_human"]
        assert svc.get(director, identity)["state"] == "pending"
        assert cycle.review(PLAYER, period)["own"]["roll"]["faces"] == [1, 1]
    finally:
        engine.dispose()


def test_observation_uses_final_bond_tag_adjustment_for_handler_selection_count(ledger):
    from test_m2_game import answer

    from girlframe.engine.m2 import TagState

    svc, _, game, period = setup(ledger, faces=(5, 5))
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].tags.append(TagState(id="known", label="Known", giver=3, observers=(3,)))
        game.event(c, 1, "known-tag", "synthetic.tag", canon)
    action = game.begin(
        PLAYER,
        "adjusted-observation",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="void_observation",
            off_duty_id=period,
            heat=0,
            context="Observed",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(
        game,
        OTHER,
        "tag_window",
        options=("tag",),
        denied=("known",),
        number=1,
        text="Actually relevant",
    )
    answer(game, ADMIN, "tag_window", options=("pass",))
    tick(worker, gateway, 5)
    assert svc.get(ADMIN, work_id(period, 2, 1))["count"] == 2
    with svc.store.engine.connect() as c:
        roll = svc.periods._get(c, period).progress["2"].roll
    assert roll.total == 12 and roll.faces == (5, 5) and roll.adjustments[0].amount == 2
    assert game.inspect(PLAYER, action)["receipt"]["pre_total"] == 10


def test_actual_frame_bonus_is_still_owned_and_granted_on_observation_route(ledger):
    svc, _, game, period = setup(ledger)
    roll_for(svc, game, period)
    rewards = RewardService(svc.periods)
    result = frame_submit(
        rewards,
        PLAYER,
        frame_work(rewards, PLAYER, period)["id"],
        Claim(
            fulfilled=True,
            official="handler:1",
            account="I actually demonstrated the JANUS Core was harmless",
        ),
    )
    assert result["reward_granted"] and state(game).sheets["2"].permissions == 1
