"""Actual owned factual proposal and separate original facilitator review."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, start, state, tick
from test_world_service import ready as world_ready

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


def ready(store):
    world, game = world_ready(store)
    return PhysicalService(world.store), game


def propose(svc, key=None, *, data=None):
    data = data or svc.preview(PLAYER)
    return svc.propose(
        PLAYER,
        key or str(uuid4()),
        data["game_revision"],
        InitialPlacement(
            actor=ActorRef.model_validate(data["actor"]),
            frame_instance=data["frame_instance"],
            girl_cell=(0, 0),
            frame_cell=(0, 0),
            mode="piloting",
            account="PRIVATE_OWN_ORIGINAL_PHYSICAL_FACTS",
            facts_confirmed=True,
        ),
    )


def decide(svc, identity, key=None, *, viewer=ADMIN, action="accept", revision=1):
    return svc.decide(
        viewer, key or str(uuid4()), identity, revision, action, "PRIVATE_ACTUAL_OWN_REVIEW"
    )


def test_actual_owner_proposal_changes_no_canon_until_actual_facilitator_review_then_rebuilds_once(
    ledger,
):
    svc, game = ready(ledger)
    before = state(game)
    view = svc.preview(PLAYER)
    result = propose(svc, "original-facts", data=view)
    assert propose(svc, "original-facts", data=view) == result
    assert state(game) == before and not svc.preview(PLAYER)["placement"]
    identity = result["id"]
    assert svc.tasks(ADMIN)[0]["incoming"] and not svc.tasks(PLAYER)[0]["incoming"]
    assert not svc.tasks(OTHER)
    with pytest.raises(WorkflowError):
        svc.get(OTHER, identity)
    with pytest.raises(WorkflowError):
        decide(svc, identity, viewer=PLAYER)
    accepted = decide(svc, identity, "accept-original-facts")
    assert decide(svc, identity, "accept-original-facts") == accepted
    after = state(game)
    assert len(after.placements) == 1 and after.sheets == before.sheets
    assert after.world == before.world and after.bonds == before.bonds
    place = after.placements[0]
    assert place.actor.incarnation == before.sheets["2"].character_id
    assert place.vessel_id == "vessel:" + identity and place.vessel_id != place.actor.incarnation
    assert not svc.tasks(PLAYER) and not svc.tasks(ADMIN)
    assert svc.get(PLAYER, identity)["review"]["decision"] == "accepted"
    with ledger.engine.connect() as c:
        sources = list(
            c.execute(
                sa.select(t.events.c.id, t.events.c.kind, t.events.c.payload_json).where(
                    t.events.c.kind.in_(
                        ("m3.initial_placement_proposed", "m3.initial_placement_reviewed")
                    )
                )
            ).mappings()
        )
        assert len(sources) == 2 and "PRIVATE" not in str(sources)
        assert {x["id"] for x in sources} == {place.proposed_event, place.source_event}
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_outbox"])) == 0
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    assert game.rebuild() > 0 and state(game) == after
    assert svc.preview(PLAYER)["placement"] == place.model_dump(mode="json")
    with pytest.raises(WorkflowError, match="cannot reset or move"):
        propose(svc)


def test_duplicate_pending_source_and_wrong_actor_cannot_propose_a_second_body(ledger):
    svc, game = ready(ledger)
    data = svc.preview(PLAYER)
    identity = propose(svc)["id"]
    with pytest.raises(WorkflowError, match="existing original"):
        propose(svc)
    pick = InitialPlacement(
        actor=ActorRef.model_validate(data["actor"]),
        frame_instance=data["frame_instance"],
        girl_cell=(0, 0),
        frame_cell=(0, 0),
        mode="inside_frame",
        account="Actual occupancy",
        facts_confirmed=True,
    )
    with pytest.raises(WorkflowError, match="your own original"):
        svc.propose(OTHER, "not-your-body", data["game_revision"], pick)
    assert len(svc.tasks(PLAYER)) == 1 and svc.get(PLAYER, identity)["state"] == "pending"
    assert not state(game).placements


@pytest.mark.parametrize("action,viewer", (("decline", ADMIN), ("withdraw", PLAYER)))
def test_real_decline_or_owner_withdrawal_is_ooc_during_pause_without_placing_anyone(
    ledger, action, viewer
):
    svc, game = ready(ledger)
    before = state(game)
    ledger.safety(OTHER, "pause-physical", ledger.status(OTHER)["revision"], pause=True)
    identity = propose(svc)["id"]
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        decide(svc, identity)
    rejected = decide(svc, identity, viewer=viewer, action=action)
    assert rejected["decision"] in ("declined", "withdrawn")
    assert state(game) == before and not svc.tasks(ADMIN)
    assert svc.get(PLAYER, identity)["state"] == "resolved"


def test_pending_and_unrestored_chat_block_confirmation_but_preserve_owned_facts(ledger):
    svc, game = ready(ledger)
    identity = propose(svc)["id"]
    action = start(game)
    with pytest.raises(WorkflowError, match="pending Plays"):
        decide(svc, identity)
    game.abort(ADMIN, "abort-before-placement", action)
    with pytest.raises(WorkflowError, match="restore chat"):
        decide(svc, identity)
    assert not state(game).placements
    tick(GameWorker(game), Gateway(), 5)
    assert decide(svc, identity)["decision"] == "accepted"


@pytest.mark.parametrize("change", ("frame", "character", "profile_only"))
def test_actual_character_and_frame_are_bound_but_a_same_character_draft_edit_does_not_erase_facts(
    ledger, change
):
    svc, game = ready(ledger)
    identity = propose(svc)["id"]
    with ledger.transaction() as c:
        if change == "frame":
            canon = state(game)
            canon.sheets["2"].frame_runtime = FrameRuntime(
                id="new-frame", generation=1, source_work="synthetic-frame-replacement"
            )
            game.event(c, 1, "synthetic-new-frame", "synthetic.frame", canon)
        else:
            c.execute(
                t.characters.update()
                .where(
                    t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2"
                )
                .values(
                    **(
                        {"id": "new-character"}
                        if change == "character"
                        else {"revision": t.characters.c.revision + 1}
                    )
                )
            )
    if change == "profile_only":
        assert decide(svc, identity)["decision"] == "accepted"
    else:
        with pytest.raises(WorkflowError):
            decide(svc, identity)
        assert not state(game).placements
        assert svc.get(PLAYER, identity)["state"] == "pending"


def test_transaction_failure_after_physical_event_rolls_back_body_work_and_command(
    ledger, monkeypatch
):
    svc, game = ready(ledger)
    identity = propose(svc)["id"]
    before = state(game)
    original = svc.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure after physical event")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError):
        decide(svc, identity, "retry-physical")
    assert state(game) == before and svc.get(PLAYER, identity)["revision"] == 1
    with ledger.engine.connect() as c:
        assert not c.scalar(
            sa.select(t.commands.c.interaction_key).where(
                t.commands.c.interaction_key == "retry-physical"
            )
        )
    monkeypatch.setattr(svc.game, "event", original)
    assert decide(svc, identity, "retry-physical")["decision"] == "accepted"


def test_concurrent_reviews_commit_one_actual_body_and_policy_revocation_blocks_cached_replay(
    ledger,
):
    svc, game = ready(ledger)
    identity = propose(svc)["id"]

    def attempt(key):
        try:
            return decide(svc, identity, key)
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ("first-physical", "second-physical")))
    assert sum(x is not None for x in outcomes) == 1 and len(state(game).placements) == 1
    before = state(game)
    ledger.policy = ledger.policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        decide(svc, identity, "first-physical")
    assert state(game) == before


def test_changed_handler_loses_the_original_review_and_view_authority(ledger):
    from girlframe.services.handler_setup import HandlerService

    svc, game = ready(ledger)
    identity = propose(svc)["id"]
    handler = HandlerService(ledger)
    revision = handler.appointment_preview(ADMIN)["revision"]
    handler.appoint(ADMIN, "change-handler", revision, 3)
    assert not svc.tasks(ADMIN)
    with pytest.raises(WorkflowError):
        svc.get(ADMIN, identity)
    with pytest.raises(WorkflowError):
        decide(svc, identity)
    assert not state(game).placements


def test_actual_backup_and_restored_canonical_rebuild_preserve_original_vessel_and_review(
    ledger, tmp_path
):
    from pathlib import Path

    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database
    from girlframe.services.onboarding import OnboardingStore

    svc, game = ready(ledger)
    identity = propose(svc)["id"]
    receipt = decide(svc, identity, "accepted-before-backup")
    original = state(game)
    destination = tmp_path / "physical-backup.db"
    copy_database(Path(ledger.engine.url.database), destination)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(destination)))
    try:
        restored = PhysicalService(OnboardingStore(engine, ledger.policy))
        assert restored.get(PLAYER, identity) == svc.get(PLAYER, identity)
        assert decide(restored, identity, "accepted-before-backup") == receipt
        assert state(restored.game) == original
        assert restored.game.rebuild() > 0 and state(restored.game) == original
    finally:
        engine.dispose()


def test_other_campaign_cannot_read_or_confirm_original_physical_sources(ledger):
    from girlframe.services.onboarding import OnboardingStore
    from girlframe.services.read_only_bot import GuildViewer

    svc, game = ready(ledger)
    identity = propose(svc)["id"]
    store = OnboardingStore(
        ledger.engine, ledger.policy.model_copy(update={"campaign_id": uuid4(), "guild_id": 201})
    )
    viewer = GuildViewer(2, 201, True, False)
    store.join(viewer, "other-campaign-member")
    other = PhysicalService(store)
    assert not other.tasks(viewer)
    with pytest.raises(WorkflowError, match="Unknown physical setup"):
        other.get(viewer, identity)
    with pytest.raises(WorkflowError):
        other.decide(viewer, "other-placement-review", identity, 1, "accept", "Not that campaign")
    assert not state(game).placements and svc.get(PLAYER, identity)["state"] == "pending"


def test_owned_proposal_failure_after_work_insertion_leaves_no_false_source_and_retries(
    ledger, monkeypatch
):
    import girlframe.services.m3_physical as module

    svc, game = ready(ledger)
    before = state(game)
    data = svc.preview(PLAYER)
    original = module.related

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure after physical proposal work")

    monkeypatch.setattr(module, "related", fail)
    with pytest.raises(RuntimeError):
        propose(svc, "proposal-retry", data=data)
    assert state(game) == before and not svc.tasks(ADMIN)
    with ledger.engine.connect() as c:
        assert not c.scalar(
            sa.select(t.events.c.id).where(t.events.c.kind == "m3.initial_placement_proposed")
        )
        assert not c.scalar(
            sa.select(t.commands.c.interaction_key).where(
                t.commands.c.interaction_key == "proposal-retry"
            )
        )
    monkeypatch.setattr(module, "related", original)
    assert propose(svc, "proposal-retry", data=data)["revision"] == 1


def test_known_actor_roll_after_abort_and_chat_restoration_still_blocks_physical_confirmation(
    ledger,
):
    from test_actor_play_service import begin
    from test_actor_play_service import ready as actor_ready

    plays, game, cast, ref, director = actor_ready(ledger)
    svc = PhysicalService(ledger)
    identity = propose(svc)["id"]
    action = begin(plays, ref)
    tick(GameWorker(game), Gateway())
    assert game.dice.calls == 1
    game.abort(ADMIN, "known-physical-abort", action)
    tick(GameWorker(game), Gateway(), 5)
    with pytest.raises(WorkflowError, match="pending Plays"):
        decide(svc, identity)
    assert not state(game).placements and game.dice.calls == 1


@pytest.mark.parametrize(
    "field,value",
    (
        ("campaign_id", "other"),
        ("owner_id", "3"),
        ("subject_id", "3"),
        ("campaign_context", False),
        ("state", "resolved"),
    ),
)
def test_physical_source_proof_rejects_wrong_campaign_owner_subject_context_or_outcome(
    ledger, field, value
):
    svc, game = ready(ledger)
    identity = propose(svc)["id"]
    with ledger.engine.connect() as c:
        row = svc._row(c, identity)
        row[field] = value
        with pytest.raises(WorkflowError, match="SOURCE_PLACEMENT_MISSING"):
            svc._review(c, row)
    assert not state(game).placements
