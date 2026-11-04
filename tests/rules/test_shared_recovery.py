"""Real root/child interruption, original choices and no repeated known dice."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, start, state, tick
from test_mission_service import service
from test_mission_ui import current

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.database.maintenance import copy_database
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.onboarding import OnboardingStore, WorkflowError

ledger = ledger_fixture


def ready(store, faces=(4, 5)):
    _, game = service(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    game.dice.faces = faces
    return RecoveryService(game), game, GameWorker(game), Gateway()


def restore(svc, game, worker, gateway, root):
    game.abort(ADMIN, str(uuid4()), root)
    tick(worker, gateway, 5)
    return next(x for x in svc.saved(PLAYER) if x["id"] == root)


@pytest.mark.parametrize("faces", ((1, 2), (4, 5), (6, 6)))
def test_known_root_restores_only_pending_decisions_and_preserves_receipt_spending_and_answers(
    ledger, faces
):
    svc, game, worker, gateway = ready(ledger, faces)
    root = start(game, identity="identity:0", gain=3, heat=3)
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, root)["receipt"]
    answer(game, PLAYER, "tag_window", options=("pass",))
    before = state(game)
    saved = restore(svc, game, worker, gateway, root)
    assert saved["rolled"] and not saved["cancellable"]
    assert svc.saved(OTHER) == []
    with pytest.raises(WorkflowError, match="discarded"):
        svc.recover(PLAYER, "cannot-discard", root, saved["revision"], cancel=True)
    assert game.dice.calls == 1 and state(game) == before
    resumed = svc.recover(PLAYER, "resume-root", root, saved["revision"])
    assert svc.recover(PLAYER, "resume-root", root, saved["revision"]) == resumed
    tick(worker, gateway)
    assert game.inspect(PLAYER, root)["receipt"] == receipt and game.dice.calls == 1
    assert not game.choices(PLAYER)
    answer(game, OTHER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    total = sum(faces) + 3
    if total <= 7:
        answer(game, PLAYER, "actor_keep", options=("tough",))
    elif total <= 10:
        answer(game, PLAYER, "actor_keep", options=("tough", "vicious"), denied=("desperate",))
    else:
        answer(game, PLAYER, "actor_keep", text="Survived the original test")
    answer(game, ADMIN, "handler_keep", flag=True, text="The original outcome remains enough")
    assert game.inspect(PLAYER, root)["state"] == "complete" and not svc.saved(PLAYER)
    assert game.dice.calls == 1 and state(game).sheets["2"].heat == before.sheets["2"].heat


def test_nested_other_human_response_restores_original_chain_without_repeating_either_roll(ledger):
    svc, game, worker, gateway = ready(ledger, (6, 6))
    root = start(game, play="flirt", target=3)
    tick(worker, gateway)
    pass_tags(game)
    answer(
        game, PLAYER, "actor_flirt", options=("name",), fields={"extra": "escape"}, text="Too far"
    )
    answer(game, OTHER, "target_flirt", text="PRIVATE_ORIGINAL_ANSWER")
    answer(game, OTHER, "flirt_escape", options=("play",))
    game.dice.faces = (4, 5)
    child = game.begin(
        OTHER,
        "actual-child",
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            context="Actual escape",
            trigger_confirmed=True,
            heat=0,
            parent=root,
        ),
    )["action_id"]
    tick(worker, gateway)
    answer(game, PLAYER, "tag_window", options=("pass",))
    receipts = [game.inspect(v, node)["receipt"] for v, node in ((PLAYER, root), (OTHER, child))]
    before = state(game)
    saved = restore(svc, game, worker, gateway, root)
    assert saved["descendants"] == 1 and not svc.saved(OTHER)
    with pytest.raises(WorkflowError, match="root actor"):
        svc.recover(OTHER, "not-root-owner", root, saved["revision"])
    svc.recover(PLAYER, "resume-chain", root, saved["revision"])
    tick(worker, gateway)
    assert state(game) == before and game.dice.calls == 2
    assert [
        game.inspect(v, node)["receipt"] for v, node in ((PLAYER, root), (OTHER, child))
    ] == receipts
    assert not game.choices(PLAYER)
    answer(game, OTHER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    answer(game, OTHER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The original escape succeeds")
    assert game.inspect(PLAYER, root)["state"] == game.inspect(OTHER, child)["state"] == "complete"
    assert game.dice.calls == 2


def test_diceless_order_parent_cannot_discard_a_known_child_roll(ledger):
    svc, game, worker, gateway = ready(ledger, (4, 5))
    root = game.issue_order(ADMIN, "actual-order", 900, 2, "Actual superior order")
    tick(worker, gateway)
    answer(game, PLAYER, "order_response", options=("disobey",))
    child = start(game, play="disobey_orders", parent=root["action_id"], order_id=root["order_id"])
    tick(worker, gateway)
    saved = restore(svc, game, worker, gateway, root["action_id"])
    assert saved["rolled"] and saved["descendants"] == 1
    with pytest.raises(WorkflowError, match="discarded"):
        svc.recover(
            PLAYER, "not-an-unrolled-chain", root["action_id"], saved["revision"], cancel=True
        )
    svc.recover(PLAYER, "resume-refusal", root["action_id"], saved["revision"])
    tick(worker, gateway)
    pass_tags(game)
    answer(game, PLAYER, "actor_disobey", options=("tag_heat",), number=1, text="Defiant")
    answer(game, ADMIN, "handler_disobey", flag=False)
    assert game.inspect(PLAYER, child)["state"] == "complete" and game.dice.calls == 1


def test_unrolled_cancellation_is_owned_and_allowed_while_paused_without_any_refund(ledger):
    svc, game, worker, gateway = ready(ledger)
    root = start(game)
    before = state(game)
    game.abort(ADMIN, "abort-before-any-dice", root)
    saved = svc.saved(PLAYER)[0]
    with pytest.raises(WorkflowError, match="Restore chat"):
        svc.recover(PLAYER, "too-soon", root, saved["revision"], cancel=True)
    tick(worker, gateway, 4)
    ledger.safety(OTHER, "pause-recovery", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.recover(PLAYER, "paused-resume", root, saved["revision"])
    outcome = svc.recover(PLAYER, "cancel-unrolled", root, saved["revision"], cancel=True)
    assert outcome["cancelled_unrolled"] and not outcome["receipt_preserved"]
    assert state(game) == before and game.dice.calls == 0 and not svc.saved(PLAYER)


def test_known_interruption_blocks_new_plays_world_mutation_and_scene_discard(ledger):
    svc, game, worker, gateway = ready(ledger)
    root = start(game)
    tick(worker, gateway)
    restore(svc, game, worker, gateway, root)
    with ledger.engine.connect() as c:
        assert game.pending_actions(c)
    with pytest.raises(WorkflowError, match="REQUIRED_RECOVERY"):
        start(game)
    with pytest.raises(WorkflowError, match="saved Play"):
        game.close_scene(ADMIN, "cannot-close-original-scene", 900)
    assert game.dice.calls == 1


def test_concurrent_same_recovery_restores_once_and_fresh_stale_command_fails(ledger):
    svc, game, worker, gateway = ready(ledger)
    root = start(game)
    tick(worker, gateway)
    saved = restore(svc, game, worker, gateway, root)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda _: svc.recover(PLAYER, "same-resume", root, saved["revision"]), range(2)
            )
        )
    assert outcomes[0] == outcomes[1]
    with pytest.raises(WorkflowError, match="STALE_RECOVERY"):
        svc.recover(PLAYER, "stale-new-resume", root, saved["revision"])
    tick(worker, gateway)
    assert game.dice.calls == 1 and len(game.choices(PLAYER)) == 1


@pytest.mark.parametrize("change", ("body", "choice", "source", "character", "member"))
def test_changed_actual_evidence_or_participant_blocks_resume_without_new_dice(ledger, change):
    svc, game, worker, gateway = ready(ledger)
    root = start(game)
    tick(worker, gateway)
    saved = restore(svc, game, worker, gateway, root)
    with ledger.transaction() as c:
        if change in ("body", "source"):
            action = game.action(c, root)
            if change == "body":
                action["data"]["prepared"]["context"] = "Forged context"
            else:
                action["data"]["shared_recovery"]["event"] = str(uuid4())
            game.save_action(c, action)
            saved["revision"] = action["revision"]
        elif change == "choice":
            c.execute(
                t.m2["m2_choices"]
                .update()
                .where(t.m2["m2_choices"].c.actor_id == "3")
                .values(body_json='{"changed": true}')
            )
        elif change == "character":
            c.execute(
                t.characters.update().where(t.characters.c.user_id == "3").values(id=str(uuid4()))
            )
        else:
            c.execute(t.members.update().where(t.members.c.user_id == "3").values(active=False))
    with pytest.raises(WorkflowError):
        svc.recover(PLAYER, "reject-changed-original", root, saved["revision"])
    assert game.dice.calls == 1 and game.inspect(PLAYER, root)["state"] == "aborted"


def test_recovery_event_failure_rolls_back_actions_choices_lock_and_retry(ledger, monkeypatch):
    svc, game, worker, gateway = ready(ledger)
    root = start(game)
    tick(worker, gateway)
    saved = restore(svc, game, worker, gateway, root)
    original = game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic interruption after restored rows")

    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        svc.recover(PLAYER, "retry-recovery-event", root, saved["revision"])
    assert svc.saved(PLAYER)[0] == saved and not game.choices(PLAYER)
    monkeypatch.setattr(game, "event", original)
    svc.recover(PLAYER, "retry-recovery-event", root, saved["revision"])
    tick(worker, gateway)
    assert game.dice.calls == 1


def test_native_inbox_and_choice_resume_use_owned_recovery_and_preserve_known_dice(ledger):
    from girlframe.discord_adapter.m2_ui import open_pending

    svc, game, worker, gateway = ready(ledger)
    root = start(game)
    tick(worker, gateway)
    restore(svc, game, worker, gateway, root)
    items = InboxService(ledger).items(PLAYER)
    assert any(x.task == "m3_shared_recovery" and x.identity == root for x in items)
    assert not any(x.task == "m3_shared_recovery" for x in InboxService(ledger).items(OTHER))

    async def run():
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        await open_pending(owner, game)
        picker = owner.edit_original_response.call_args.kwargs["view"]
        await picker.open_item(owner, "shared:" + root)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        assert dict(form.fields[0].options) == {"resume": "Resume the saved response chain"}
        form.values = {"operation": ("resume",)}
        await form.confirm.callback(current(2, 19201))
        assert form.completed

    asyncio.run(run())
    tick(worker, gateway)
    assert game.dice.calls == 1


def test_backup_rebuild_preserves_private_original_root_chain_and_resumes_without_new_dice(
    ledger, tmp_path
):
    svc, game, worker, gateway = ready(ledger)
    root = start(game)
    tick(worker, gateway)
    answer(game, PLAYER, "tag_window", options=("pass",))
    saved = restore(svc, game, worker, gateway, root)
    before = state(game)
    receipt = game.inspect(PLAYER, root)["receipt"]
    destination = tmp_path / "shared-recovery-backup.db"
    copy_database(Path(ledger.engine.url.database), destination)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(destination)))
    try:
        restored_store = OnboardingStore(engine, ledger.policy)
        restored_game = GameService(restored_store, dice=game.dice)
        restored_game.rebuild()
        restored = RecoveryService(restored_game)
        assert state(restored_game) == before and restored.saved(PLAYER) == [saved]
        restored.recover(PLAYER, "resume-from-private-backup", root, saved["revision"])
        tick(GameWorker(restored_game), gateway)
        assert restored_game.inspect(PLAYER, root)["receipt"] == receipt
        assert not restored_game.choices(PLAYER) and game.dice.calls == 1
        assert svc.saved(PLAYER) == [saved]  # The original DB was never switched.
    finally:
        engine.dispose()


def test_membership_policy_and_campaign_isolation_do_not_expose_or_resume_another_chain(ledger):
    from girlframe.services.read_only_bot import GuildViewer

    svc, game, worker, gateway = ready(ledger)
    root = start(game)
    tick(worker, gateway)
    saved = restore(svc, game, worker, gateway, root)
    for viewer in (OTHER, GuildViewer(2, 999, True, True), GuildViewer(2, 200, False, True)):
        with pytest.raises(WorkflowError):
            svc.recover(viewer, str(uuid4()), root, saved["revision"])
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    assert svc.saved(PLAYER) == [saved]
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        svc.recover(PLAYER, "revoked-resume", root, saved["revision"])
    ledger.policy = policy
    foreign = str(uuid4())
    with ledger.transaction() as c:
        c.execute(t.campaigns.insert().values(id=foreign, guild_id="999", revision=0))
        c.execute(
            t.members.insert().values(campaign_id=foreign, user_id="2", role="player", active=True)
        )
    other_policy = policy.model_copy(update={"campaign_id": foreign, "guild_id": 999})
    other = RecoveryService(GameService(OnboardingStore(ledger.engine, other_policy)))
    foreign_viewer = GuildViewer(2, 999, True, True)
    assert not other.saved(foreign_viewer)
    with pytest.raises(WorkflowError, match="Unknown action"):
        other.recover(foreign_viewer, "foreign-recovery", root, saved["revision"])
    assert game.dice.calls == 1


def test_legacy_abort_without_original_interruption_evidence_has_no_invented_recovery(ledger):
    from test_m2_game import setup_game

    game, worker, gateway, _ = setup_game(ledger)
    root = start(game)
    tick(worker, gateway)
    game.abort(ADMIN, "legacy-abort", root)
    tick(worker, gateway, 5)
    assert not RecoveryService(game).saved(PLAYER)
    with ledger.engine.connect() as c:
        assert "shared_recovery" not in game.action(c, root)["data"]


def test_abort_evidence_failure_keeps_original_action_and_pending_choices_atomic(
    ledger, monkeypatch
):
    svc, game, worker, gateway = ready(ledger)
    root = start(game)
    tick(worker, gateway)
    before = game.inspect(PLAYER, root)
    original = game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic abort-event failure")

    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        game.abort(ADMIN, "retry-abort", root)
    assert game.inspect(PLAYER, root) == before and not svc.saved(PLAYER)
    assert len(game.choices(PLAYER)) == 1
    with ledger.engine.connect() as c:
        assert (
            c.scalar(
                sa.select(t.commands.c.interaction_key).where(
                    t.commands.c.interaction_key == "retry-abort"
                )
            )
            is None
        )
    monkeypatch.setattr(game, "event", original)
    game.abort(ADMIN, "retry-abort", root)
    assert svc.saved(PLAYER)[0]["rolled"] and game.dice.calls == 1


def test_known_off_duty_interruption_also_blocks_world_changes_after_chat_is_restored(ledger):
    from test_off_duty_roll_service import active

    from girlframe.services.m3_play_support import resume
    from girlframe.services.m3_world import WorldService

    periods, game, worker, gateway, period = active(ledger)
    root = start(game, play="go_off_duty", off_duty_id=period)
    tick(worker, gateway)
    game.abort(ADMIN, "abort-known-off-duty", root)
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.pending_actions(c)
        with pytest.raises(WorkflowError, match="finish pending Plays"):
            WorldService(periods.missions)._state(c, state(game).revision)
    with pytest.raises(WorkflowError, match="REQUIRED_RECOVERY"):
        start(game)
    resume(game, PLAYER, "resume-actual-off-duty", root, game.inspect(PLAYER, root)["revision"])
    tick(worker, gateway)
    assert game.dice.calls == 1
