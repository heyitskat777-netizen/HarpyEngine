"""Real paid rule, owned actual rebirth retention and original Harpy action consumers."""

from uuid import uuid4

from test_enforcer_requisitions import approved, buy
from test_harpy_actor_plays import begin, pass_tags
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_retained_tag_permissions import reborn_with_lock

from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_enforcer import INITIATIVE
from girlframe.engine.m3_enforcer_requisitions import SNOOP
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_enforcer import EnforcerService
from girlframe.services.m3_missions import MissionService


def reborn(store, tmp_path, monkeypatch):
    def configure(game):
        service = approved(store, game, tmp_path, monkeypatch, extra=(INITIATIVE,))
        with store.transaction() as c:
            canon = state(game)
            canon.sheets["2"].permissions = 3
            game.event(c, 1, str(uuid4()), "synthetic.actual_prior_funds", canon)
        buy(service, SNOOP)

    game, worker, gateway, actor, *_ = reborn_with_lock(
        store, frame="THE ENFORCER", configure=configure, retained_plays=(SNOOP, INITIATIVE)
    )
    cast = CastService(ActorService(MissionService(store)))
    data = cast.view(PLAYER, 900)
    cast.change(
        PLAYER, str(uuid4()), 900, data["game_revision"], data["cast_revision"], "join", actor
    )
    return game, worker, gateway, actor, ActorPlayService(game)


def test_actual_paid_snoop_retained_at_real_birth_uses_original_harpy_and_actual_private_answers(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, actor, service = reborn(ledger, tmp_path, monkeypatch)
    assert "2" not in state(game).sheets
    game.dice.faces = (1, 1)
    original_calls = game.dice.calls
    action = begin(service, actor, play="snoop", target_actor=current_ref(state(game), 3))
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "snoop_select", options=("rebel_evidence",))
    answer(game, OTHER, "snoop_answer", text="PRIVATE_REAL_RETAINED_HARPY_FINDING")
    answer(game, OTHER, "snoop_answer", text="PRIVATE_REAL_RETAINED_HARPY_MISSED")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert "2" not in state(game).sheets and game.dice.calls == original_calls + 1


def test_actual_retained_initiative_mid_grasp_and_original_owned_release_use_no_pc_proxy(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, actor, service = reborn(ledger, tmp_path, monkeypatch)
    game.dice.faces = (4, 5)
    original_calls = game.dice.calls
    target = current_ref(state(game), 3)
    action = begin(
        service, actor, play="enforcement_initiative", target_actor=target, piloting=True
    )
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    actual = state(game)
    grip = actual.enforcer_grasps[-1]
    assert grip.actor == actor and grip.target == target and grip.held
    assert is_helpless(actual, target, actor)
    owned = EnforcerService(game)
    view = next(x for x in owned.grasps(PLAYER) if x["id"] == grip.id)
    owned.release_grasp(
        PLAYER,
        str(uuid4()),
        grip.id,
        view["revision"],
        "Original Harpy releases the actual original Frame grip",
    )
    assert not state(game).enforcer_grasps[-1].held and is_helpless(state(game), target, actor)
    assert "2" not in state(game).sheets and game.dice.calls == original_calls + 1


def test_actual_retained_harpy_high_instruction_and_actual_punishment_finishes_original_action(
    ledger, tmp_path, monkeypatch
):
    from test_ledger import ADMIN

    from girlframe.engine.m3_punishments import Details
    from girlframe.engine.m3_role_punishment_state import Instruction
    from girlframe.services.m3_role_punishments import RolePunishmentService

    game, worker, gateway, actor, service = reborn(ledger, tmp_path, monkeypatch)
    game.dice.faces = (6, 6)
    calls = game.dice.calls
    target = current_ref(state(game), 3)
    action = begin(
        service, actor, play="enforcement_initiative", target_actor=target, piloting=True
    )
    tick(worker, gateway, 3)
    pass_tags(game)
    case = state(game).role_punishments[-1]
    assert case.executor == actor and case.executor.kind == "external_pilot"
    assert case.pc_work is None and case.executor_frame is not None
    owned = RolePunishmentService(game)

    def change(viewer, **kwargs):
        data = owned.get(viewer, case.id)
        return owned.change(viewer, str(uuid4()), case.id, data["revision"], **kwargs)

    details = Details(kind="quality_time", tag="Actual original Harpy's instructed consequence")
    change(
        ADMIN, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(PLAYER, scene="Actual retained Harpy carries out the instructed source scene")
    change(OTHER, attest=True)
    change(PLAYER, execute=True, account="Actual original Harpy performs instructed Quality Time")
    actual = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert actual.sheets["3"].tags[-1].giver_actor == actor
    assert "2" not in actual.sheets and game.dice.calls == calls + 1
    assert actual.role_punishments[-1].completion_event is not None


def test_retained_harpy_high_rejects_rewritten_birth_and_cannot_execute_other_originals_case(
    ledger, tmp_path, monkeypatch
):
    import pytest

    from girlframe.services.m3_role_punishments import RolePunishmentService
    from girlframe.services.onboarding import WorkflowError

    game, worker, gateway, actor, service = reborn(ledger, tmp_path, monkeypatch)
    game.dice.faces = (6, 6)
    action = begin(
        service,
        actor,
        play="enforcement_initiative",
        target_actor=current_ref(state(game), 3),
        piloting=True,
    )
    tick(worker, gateway, 3)
    pass_tags(game)
    case = state(game).role_punishments[-1]
    with game.store.transaction() as c:
        altered = state(game)
        altered.career_archives = [
            row.model_copy(update={"links_json": "{}"})
            if row.id == altered.career_archives[-1].id
            else row
            for row in altered.career_archives
        ]
        game.event(c, 1, str(uuid4()), "synthetic.invalid_rewritten_birth", altered)
    owned = RolePunishmentService(game)
    data = owned.get(PLAYER, case.id)
    assert data["stale"]
    with pytest.raises(WorkflowError):
        owned.change(
            PLAYER,
            str(uuid4()),
            case.id,
            data["revision"],
            scene="Cannot attest through a rewritten original birth",
        )
    assert game.inspect(PLAYER, action)["state"] != "complete"
    assert not state(game).role_punishments[-1].effect_event
