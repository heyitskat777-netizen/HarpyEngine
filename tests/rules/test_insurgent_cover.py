"""Cover uses a real Off-Duty dependency, saved die and original evidence holder."""

import asyncio

import pytest
from test_insurgent_loyalty import create_insurgent
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, prepared
from test_strain_service import D6

from girlframe.discord_adapter.inbox import InboxView
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_insurgent_cover import effective, records
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_tags import HandlerTagService
from girlframe.services.m3_insurgent_cover import CoverService
from girlframe.services.onboarding import WorkflowError


def test_cover_holds_off_duty_and_only_original_holder_can_use_the_evidence(ledger):
    cycle, game, period = prepared(
        ledger, before_period=lambda game: create_insurgent(ledger, game)
    )
    identity = "cover:" + period
    die = D6(1)
    cover = CoverService(cycle.periods, die)
    inbox = InboxService(ledger)

    with pytest.raises(WorkflowError):
        activate(cycle, game, period)
    initial = state(game).revision
    with pytest.raises(WorkflowError, match="original Insurgent"):
        cover.roll(PLAYER, "cover-roll-wrong-owner", identity, initial)
    assert die.calls == 0
    receipt = cover.roll(ADMIN, "saved-cover-die", identity, initial)
    assert receipt["face"] == receipt["effective_face"] == 1
    assert cover.roll(ADMIN, "saved-cover-die", identity, initial) == receipt and die.calls == 1
    assert not any(x.identity == identity for x in inbox.items(PLAYER))
    ledger.engine.dispose()

    async def choose(viewer, sequence, **values):
        click = current(viewer.user_id, sequence)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(viewer) if x.identity == identity)
        await InboxView(inbox, viewer.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        sent = current(viewer.user_id, sequence + 1)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    subject = current_ref(state(game), 2)
    asyncio.run(choose(ADMIN, 48000, holder=(subject.token,)))
    assert cover.get(ADMIN, identity)["stage"] == "evidence"
    assert not any(x.identity == identity for x in inbox.items(OTHER))
    with pytest.raises(WorkflowError):
        activate(cycle, game, period)
    with pytest.raises(WorkflowError, match="original Girl"):
        cover.acquire(ADMIN, "not-the-finder", identity, state(game).revision, "Forged.")
    ledger.safety(OTHER, "pause-evidence", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        cover.acquire(PLAYER, "paused-evidence", identity, state(game).revision, "Hold.")
    ledger.safety(OTHER, "resume-evidence", ledger.status(OTHER)["revision"], pause=False)
    ledger.engine.dispose()
    submitted = state(game).revision
    account = "PRIVATE_FOUND_EVIDENCE"
    asyncio.run(choose(PLAYER, 48010, account=account))
    assert cover.acquire(PLAYER, "48011", identity, submitted, account)["state"] == "resolved"
    with pytest.raises(WorkflowError, match="STALE_COVER"):
        cover.acquire(PLAYER, "again-evidence", identity, submitted, account)
    final = state(game)
    (saved,) = records(final)
    assert saved.holder == subject and saved.rng_source == "test_injected"
    assert effective(final, saved.handler, 1) == 2
    tag = next(x for x in final.handler_tags if x.id == saved.tag)
    assert tag.observers == (2,) and tag.giver_actor == subject
    assert account not in str(cover.get(ADMIN, identity))
    assert activate(cycle, game, period)["phase"] == "active"

    tags = HandlerTagService(game)
    third_party = tags.view(OTHER, 900, current_ref(state(game), 3))
    assert not any(x["id"] == tag.id for x in third_party["tags"])
    for number in (1, 2):
        allowed = tags.view(PLAYER, 900, subject)
        assert next(x for x in allowed["tags"] if x["id"] == tag.id)["persistent"]
        tags.use(
            PLAYER,
            "show-evidence-" + str(number),
            900,
            subject,
            allowed["source_sha256"],
            tag.id,
            "attention",
            "An actual scoped request.",
        )
        assert any(x.id == tag.id for x in state(game).handler_tags)
    asyncio.run(choose(PLAYER, 48020, confirm=("yes",)))
    assert cover.get(PLAYER, identity)["stage"] == "lost"
    assert all(x.id != tag.id for x in state(game).handler_tags)
    assert all(x["id"] != tag.id for x in tags.view(PLAYER, 900, subject)["tags"])
