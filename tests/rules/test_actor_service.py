from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_world_service import ready as world_ready

from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store):
    world, game = world_ready(store)
    roles = NpcRoleService(world)
    proposal = roles.offer(
        ADMIN,
        "offer-secret-role",
        state(game).revision,
        Npc(
            id="secret-npc",
            name="PRIVATE_NPC_NAME",
            jobs=("guard",),
            detail="PRIVATE_NPC_DETAIL",
            controller=2,
            cell=(0, 0),
        ),
    )
    roles.respond(PLAYER, "accept-secret-role", proposal["id"], state(game).revision, "accept")
    return ActorService(world.missions), game


def pc_ref(svc, game):
    return ActorRef(kind="pilot", entity="2", incarnation=state(game).sheets["2"].character_id)


def legacy(svc, game):
    with svc.store.transaction() as c:
        canon = state(game)
        canon.sheets["2"].character_id = None
        game.event(c, 1, "legacy-source", "synthetic.legacy_actor", canon)


def test_owned_role_selector_distinguishes_same_human_roles_and_knowledge_is_actor_scoped(ledger):
    svc, game = ready(ledger)
    choices = svc.choices(PLAYER)
    assert {x["kind"] for x in choices["actors"]} == {"pilot", "npc"}
    assert len({x["token"] for x in choices["actors"]}) == 2 and not choices["stale"]
    assert "PRIVATE_NPC_NAME" in str(choices)
    pc = pc_ref(svc, game)
    assert "PRIVATE_NPC" not in str(svc.known(PLAYER, pc))
    npc = ActorRef(kind="npc", entity="secret-npc")
    known = svc.known(PLAYER, npc)
    assert "PRIVATE_NPC_NAME" in str(known)
    assert "identities" not in str(known) and "source_sha256" not in str(known)
    assert "PRIVATE_NPC" not in str(svc.choices(OTHER))
    with pytest.raises(WorkflowError):
        svc.inspect(OTHER, npc)
    with pytest.raises(WorkflowError):
        svc.known(OTHER, pc)
    assert svc.inspect(PLAYER, npc)["actor"]["rules"] == "npc"


def test_stale_own_pilot_profile_does_not_hide_a_separately_controlled_valid_npc(ledger):
    svc, game = ready(ledger)
    with ledger.transaction() as c:
        c.execute(
            t.characters.update()
            .where(t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2")
            .values(revision=t.characters.c.revision + 1)
        )
    result = svc.choices(PLAYER)
    assert len(result["stale"]) == 1 and result["stale"][0]["ref"]["kind"] == "pilot"
    assert len(result["actors"]) == 1 and result["actors"][0]["kind"] == "npc"
    assert (
        svc.inspect(PLAYER, ActorRef(kind="npc", entity="secret-npc"))["actor"]["controller"] == 2
    )


def test_legacy_binding_uses_immutable_actual_character_snapshot_and_preserves_all_resources(
    ledger,
):
    svc, game = ready(ledger)
    original_id = state(game).sheets["2"].character_id
    legacy(svc, game)
    before = state(game)
    result = svc.choices(PLAYER)
    assert result["legacy_binding_available"] and not result["stale"]
    saved = svc.bind_legacy(PLAYER, "bind-once", before.revision)
    assert svc.bind_legacy(PLAYER, "bind-once", before.revision) == saved
    after = state(game)
    assert after.sheets["2"].character_id == original_id
    assert after.sheets["2"].model_dump(exclude={"character_id", "revision"}) == before.sheets[
        "2"
    ].model_dump(exclude={"character_id", "revision"})
    assert after.order == before.order
    assert not svc.choices(PLAYER)["legacy_binding_available"]
    assert (
        svc.inspect(PLAYER, ActorRef.model_validate(saved["ref"]))["actor"]["label"]
        == after.sheets["2"].callsign
    )
    with pytest.raises(WorkflowError):
        svc.bind_legacy(OTHER, "cannot-bind-for-other", before.revision)


def test_new_character_with_same_human_and_revision_cannot_take_unbound_old_sheet(ledger):
    svc, game = ready(ledger)
    legacy(svc, game)
    before = state(game)
    with ledger.transaction() as c:
        c.execute(
            t.characters.update()
            .where(t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2")
            .values(id=str(uuid4()))
        )
    with pytest.raises(WorkflowError, match="SOURCE_BINDING_MISSING"):
        svc.bind_legacy(PLAYER, "cannot-borrow-old-resources", before.revision)
    assert state(game) == before


def test_legacy_binding_pause_rollback_and_policy_revocation_preserve_source(ledger, monkeypatch):
    svc, game = ready(ledger)
    legacy(svc, game)
    before = state(game)
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.bind_legacy(PLAYER, "retry", before.revision)
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    original = svc.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic after-event failure")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError):
        svc.bind_legacy(PLAYER, "retry", before.revision)
    assert state(game) == before
    monkeypatch.setattr(svc.game, "event", original)
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError, match="REVIEW_PENDING"):
        svc.bind_legacy(PLAYER, "retry", before.revision)
    ledger.policy = policy
    svc.bind_legacy(PLAYER, "retry", before.revision)
    assert state(game).sheets["2"].character_id is not None


def replace_profile_id(store, owner):
    with store.transaction() as c:
        c.execute(
            t.characters.update()
            .where(
                t.characters.c.campaign_id == store.campaign_id,
                t.characters.c.user_id == str(owner),
            )
            .values(id=str(uuid4()))
        )


def test_legacy_play_api_rejects_same_revision_new_character_before_reservation_or_dice(ledger):
    from test_m2_game import start

    _, game = ready(ledger)
    before = state(game)
    replace_profile_id(ledger, 2)
    with pytest.raises(WorkflowError, match="STALE_CHARACTER"):
        start(game)
    assert state(game) == before and game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"])) == 0


def test_pending_unrolled_action_cannot_consume_resources_for_a_changed_character(ledger):
    import asyncio

    from test_m2_game import Gateway, start

    from girlframe.delivery.m2_worker import GameWorker

    _, game = ready(ledger)
    action = start(game)
    worker, gateway = GameWorker(game), Gateway()
    job = worker.claim("m2_locks", ("acquiring",))
    asyncio.run(worker.acquire(job, gateway))
    before = state(game)
    replace_profile_id(ledger, 2)
    with pytest.raises(WorkflowError, match="STALE_CHARACTER"):
        game.roll(PLAYER, "cannot-roll-new-body", action)
    assert state(game) == before and game.dice.calls == 0
    assert game.inspect(PLAYER, action)["receipt"] is None


def test_known_roll_and_private_decision_do_not_move_to_replacement_participant(ledger):
    from test_m2_game import Gateway, answer, start, tick

    from girlframe.delivery.m2_worker import GameWorker

    _, game = ready(ledger)
    action = start(game)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, action)["receipt"]
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "tag_window")
    before = state(game)
    replace_profile_id(ledger, 3)
    with pytest.raises(WorkflowError, match="STALE_CHARACTER"):
        game.decision(OTHER, choice["id"])
    with pytest.raises(WorkflowError, match="STALE_CHARACTER"):
        answer(game, OTHER, "tag_window", options=("pass",))
    assert state(game) == before and game.inspect(PLAYER, action)["receipt"] == receipt
    assert game.dice.calls == 1


def test_saved_canonical_choices_remain_available_after_same_character_draft_revision(ledger):
    from test_m2_game import Gateway, answer, start, tick

    from girlframe.delivery.m2_worker import GameWorker

    _, game = ready(ledger)
    action = start(game)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    with ledger.transaction() as c:
        c.execute(
            t.characters.update()
            .where(t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "3")
            .values(revision=t.characters.c.revision + 1)
        )
    answer(game, OTHER, "tag_window", options=("pass",))
    assert game.inspect(PLAYER, action)["receipt"] and game.dice.calls == 1


def test_legacy_known_roll_proves_original_generation_after_metadata_binding_and_resume(ledger):
    from test_m2_game import Gateway, pass_tags, start, tick
    from test_off_duty_cycle import activate, prepared

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.services.m3_play_support import resume

    cycle, game, period = prepared(ledger)
    activate(cycle, game, period)
    actors = ActorService(cycle.missions)
    legacy(actors, game)
    action = start(game, play="go_off_duty", off_duty_id=period)
    with ledger.transaction() as c:
        saved = game.action(c, action)
        saved["data"].pop("character_ids")
        game.save_action(c, saved)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt and game.dice.calls == 1
    game.abort(ADMIN, "abort-legacy-roll", action)
    tick(worker, gateway, 5)
    actors.bind_legacy(PLAYER, "bind-after-safe-abort", state(game).revision)
    resume(game, PLAYER, "resume-original-roll", action, game.inspect(PLAYER, action)["revision"])
    tick(worker, gateway, 2)
    pass_tags(game)
    tick(worker, gateway, 5)
    assert game.dice.calls == 1 and game.inspect(PLAYER, action)["receipt"] == receipt
    assert game.inspect(PLAYER, action)["state"] == "complete"
