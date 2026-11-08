"""Native original physical facts, owned inbox review and read-only historical sources."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_physical_service import decide, propose, ready

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_physical import open_initial, open_review
from girlframe.services.inbox import InboxService
from girlframe.services.onboarding import WorkflowError


def test_native_locations_occupancy_and_separate_facilitator_review_are_owned_and_resumable(ledger):
    svc, game = ready(ledger)

    async def run():
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        await open_initial(owner, svc)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and not await form.interaction_check(current(3))
        fields = {x.key: x for x in form.fields}
        assert fields["girl_location"].options and len(fields["mode"].options) == 3
        assert not state(game).placements
        form.values.update(
            girl_location=("base0",),
            frame_location=("base0",),
            mode=("piloting",),
            account="PRIVATE_ACTUAL_OWN_INITIAL_FACTS",
            confirm=("yes",),
        )
        await form.confirm.callback(current(2, 55101))
        assert form.completed and not state(game).placements
        identity = svc.tasks(PLAYER)[0]["id"]
        await open_initial(owner, svc)
        resumed = owner.edit_original_response.call_args.kwargs["view"]
        choices = next(x.options for x in resumed.fields if x.key == "decision")
        assert dict(choices) == {"withdraw": "Withdraw my pending proposal"}
        await open_review(owner, svc, identity)
        assert not state(game).placements
        facilitator = current(1)
        await facilitator.response.defer(ephemeral=True)
        await open_review(facilitator, svc, identity)
        review = facilitator.edit_original_response.call_args.kwargs["view"]
        assert isinstance(review, NativeForm)
        assert not await review.interaction_check(current(2))
        review.values.update(
            decision=("accept",), account="PRIVATE_ACTUAL_FACILITATOR_CONFIRMATION"
        )
        await review.confirm.callback(current(1, 55102))
        assert review.completed and len(state(game).placements) == 1
        assert not svc.tasks(ADMIN) and not svc.tasks(PLAYER)
        await open_initial(owner, svc)
        assert "recorded physical facts" in owner.edit_original_response.call_args.kwargs["content"]
        await open_review(owner, svc, identity)
        assert "accepted" in owner.edit_original_response.call_args.kwargs["content"]

    asyncio.run(run())


def test_inbox_uses_original_participants_and_one_read_snapshot_without_leaking_account(ledger):
    svc, game = ready(ledger)
    identity = propose(svc)["id"]
    inbox = InboxService(ledger)
    owner = next(x for x in inbox.page(PLAYER, "waiting", "world").window if x.identity == identity)
    handler = next(x for x in inbox.page(ADMIN, "you", "world").window if x.identity == identity)
    assert owner.task == handler.task == "m3_physical"
    assert not owner.incoming and handler.incoming
    assert identity not in str(inbox.items(OTHER))
    assert "PRIVATE_OWN_ORIGINAL_PHYSICAL_FACTS" not in str(inbox.items(ADMIN))
    decide(svc, identity)
    history = next(
        x for x in inbox.page(PLAYER, "history", "world").window if x.identity == identity
    )
    assert history.task == "m3_physical" and history.primary == "View physical facts"
    assert history.state == "resolved" and not history.incoming


def test_saved_physical_views_and_inbox_survive_registry_unavailability_without_enabling_writes(
    ledger, monkeypatch, tmp_path
):
    svc, game = ready(ledger)
    identity = propose(svc)["id"]
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(tmp_path / "unavailable-registry.json"))
    assert svc.get(PLAYER, identity)["state"] == "pending"
    assert any(x.identity == identity for x in InboxService(ledger).items(PLAYER))
    with pytest.raises(WorkflowError, match="registry is unavailable"):
        decide(svc, identity)
    assert not state(game).placements


def test_departed_original_owner_and_non_integer_or_stale_reviews_cannot_place_a_body(ledger):
    svc, game = ready(ledger)
    identity = propose(svc)["id"]
    for revision in (True, 0, 2):
        with pytest.raises(WorkflowError, match="STALE_PLACEMENT"):
            decide(svc, identity, revision=revision)
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
            .values(active=False)
        )
    with pytest.raises(WorkflowError, match="must still be a campaign member"):
        decide(svc, identity)
    assert not state(game).placements and svc.get(ADMIN, identity)["state"] == "pending"


def test_stale_original_factual_preview_cannot_bind_a_changed_world_revision(ledger):
    svc, game = ready(ledger)
    data = svc.preview(PLAYER)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].heat += 1
        game.event(c, 3, "synthetic-world-change", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="STALE_PLACEMENT"):
        propose(svc, data=data)
    assert not svc.tasks(ADMIN) and not state(game).placements


def test_initial_position_task_is_owned_derived_and_disappears_on_real_proposal_or_disabled_scope(
    ledger,
):
    svc, game = ready(ledger)
    inbox = InboxService(ledger)
    tasks = [x for x in inbox.items(PLAYER) if x.task == "m3_physical_start"]
    assert len(tasks) == 1 and tasks[0].incoming
    assert tasks[0].identity == state(game).sheets["2"].character_id
    assert not any(x.identity == tasks[0].identity for x in inbox.items(OTHER))
    before = state(game)
    assert len([x for x in inbox.items(PLAYER) if x.task == "m3_physical_start"]) == 1
    assert state(game) == before
    propose(svc)
    assert not any(x.task == "m3_physical_start" for x in inbox.items(PLAYER))
    assert any(x.task == "m3_physical" for x in inbox.items(PLAYER))
    ledger.policy = ledger.policy.model_copy(update={"m3_approval": None})
    assert not any(x.task == "m3_physical_start" for x in inbox.items(OTHER))
