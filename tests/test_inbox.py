import asyncio
import json
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import discord
import pytest
import sqlalchemy as sa
from test_handler_setup import ready as handler_ready
from test_ledger import ADMIN, OTHER, PLAYER, seed
from test_ledger import ledger as ledger_fixture
from test_pair_assets import ready as pair_ready
from test_shared_setup import mentor_ready

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import CourtRecipient, InboxView
from girlframe.engine.bonds import BondProposal
from girlframe.engine.creation import AssetChoice
from girlframe.engine.drafts import DraftInput
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.pair_assets import PairNames
from girlframe.engine.shared_setup import CallsignChoice, CourtChoice
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.inbox import InboxService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.shared_setup import SharedSetupService

ledger = ledger_fixture


def mixed(ledger):
    seed(ledger)
    seed(ledger, OTHER, notes="PRIVATE_OTHER_NOTES")
    ledger.save_draft(
        OTHER,
        "queen",
        1,
        DraftInput(
            callsign="OTHER",
            girl_playbook="ALPHA",
            frame_playbook="THE RED QUEEN",
            notes="PRIVATE_OTHER_NOTES",
        ),
    )
    bonds = BondService(ledger)
    bond = bonds.propose(
        PLAYER,
        "bond",
        1,
        2,
        BondProposal(target_id=OTHER.user_id, prompt=0, context="Shared bond context"),
    )
    shared = SharedSetupService(ledger)
    request = shared.propose(
        OTHER,
        "court",
        PLAYER.user_id,
        "court",
        shared.prepare(OTHER, PLAYER.user_id, "court"),
        CourtChoice(role="The Knight"),
    )
    return InboxService(ledger), bond, request


def test_mixed_source_counts_roles_history_and_exact_replay(ledger):
    service, bond, shared = mixed(ledger)
    page = service.page(PLAYER)
    assert page.counts == {"pending": 2, "you": 1, "waiting": 1, "history": 0}
    assert page.item.source == "shared" and page.item.incoming
    assert service.page(PLAYER, "waiting").item.identity == bond["id"]
    assert service.page(PLAYER, "pending", "court").counts["pending"] == 1
    assert service.page(PLAYER, "pending", "bonds").counts["waiting"] == 1
    with pytest.raises(WorkflowError):
        service.decide(PLAYER, "forged", service.page(PLAYER, "waiting").item, "accept")
    item = page.item
    service.decide(PLAYER, "accept", item, "accept")
    service.decide(PLAYER, "accept", item, "accept")
    assert service.page(PLAYER).counts == {"pending": 1, "you": 0, "waiting": 1, "history": 1}
    assert service.page(PLAYER, "history").item.identity == shared["id"]
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.shared_setup_revisions)) == 2
    seed(ledger, ADMIN)
    assert service.page(ADMIN).total == 0
    with pytest.raises(WorkflowError):
        service.decide(ADMIN, "admin-forge", item, "accept")
    assert "PRIVATE_OTHER_NOTES" not in json.dumps([asdict(x) for x in service.items(PLAYER)])


def test_inbox_counts_beyond_individual_twenty_item_limits(ledger):
    service, bond, shared = mixed(ledger)
    for number in range(21):
        actor = GuildViewer(100 + number, 200, True, False)
        seed(ledger, actor)
        service.bonds.propose(
            actor, "request-" + str(number), 1, 1, BondProposal(target_id=PLAYER.user_id, prompt=0)
        )
    assert len(service.bonds.list(PLAYER)) == 20
    page = service.page(PLAYER)
    assert page.total == 23 and page.counts["you"] == 22
    keys = {service.page(PLAYER, index=i).item.key for i in range(page.total)}
    assert len(keys) == 23
    assert service.page(PLAYER, index=999).index == 22
    assert service.page(PLAYER, index=-2).index == 0


def test_nomination_and_callsign_tasks_deduplicate_downstream_requests(ledger):
    handler = handler_ready(ledger, "NEWGIRL")
    handler.mentor(
        ADMIN,
        "nominate",
        1,
        PilotRef(user_id=PLAYER.user_id, character_revision=2),
        PilotRef(user_id=OTHER.user_id, character_revision=1),
    )
    service = InboxService(ledger)
    first = service.page(PLAYER)
    assert first.item.task == "mentor_start"
    old = first.item
    row = service.bonds.propose(
        PLAYER, "mentor-bond", 2, 1, BondProposal(target_id=OTHER.user_id, prompt=0)
    )
    assert service.page(PLAYER).counts["waiting"] == 1
    assert not any(x.task == "mentor_start" for x in service.items(PLAYER))
    with pytest.raises(WorkflowError):
        service.current(PLAYER, old.key, old.revision)
    service.bonds.decide(OTHER, "accept-bond", row["id"], 1, "accept")
    task = service.page(OTHER).item
    assert task.task == "callsign" and task.target == PLAYER.user_id
    choice = service.shared.propose(
        OTHER,
        "name",
        PLAYER.user_id,
        "callsign",
        service.shared.prepare(OTHER, PLAYER.user_id, "callsign"),
        CallsignChoice(callsign="NAME"),
    )
    assert not any(x.task == "callsign" for x in service.items(OTHER))
    assert service.page(OTHER, "waiting").item.identity == choice["id"]


def test_pair_names_and_owner_descriptions_are_different_private_tasks(ledger):
    pair, bonds, identity = pair_ready(ledger)
    service = InboxService(ledger)
    assert service.page(OTHER).item.task == "pair"
    assert not any(x.task == "describe" for x in service.items(OTHER))
    names = ("Radio Implant", "Magnetic Bands")
    pair.choose(OTHER, "choose", identity, 2, 0, PairNames(names=names))
    assert service.page(OTHER).total == 0
    task = service.page(PLAYER).item
    assert task.task == "describe"
    creation = CreationService(ledger)
    progress = creation.get(PLAYER)
    draft = progress.draft.model_copy(
        update={
            "pair_asset_descriptions": tuple(
                AssetChoice(name=x, description="PRIVATE_OWNER_DESCRIPTION") for x in names
            )
        }
    )
    creation.save(PLAYER, "describe", 0, 2, draft, expected_pair_token=progress.pair_choice.token)
    assert service.page(PLAYER).total == 0
    assert "PRIVATE_OWNER_DESCRIPTION" not in json.dumps([asdict(x) for x in service.items(OTHER)])


def test_court_task_disappears_when_request_exists_and_returns_after_decline(ledger):
    service, bond, request = mixed(ledger)
    assert not any(x.task == "court" for x in service.items(OTHER))
    service.shared.decide(PLAYER, "decline", request["id"], 1, "decline")
    assert service.page(OTHER, category="court").item.task == "court"
    assert service.page(OTHER).item.target is None


def test_stale_versions_revoked_membership_and_campaign_isolation(ledger):
    service, bond, request = mixed(ledger)
    before = service.page(PLAYER).item
    ledger.save_draft(
        OTHER,
        "change-profile",
        2,
        DraftInput(callsign="OTHER", girl_playbook="ALPHA", frame_playbook="THE RED QUEEN"),
    )
    stale = service.page(PLAYER).item
    assert stale.stale
    assert service.page(PLAYER).counts["waiting"] == 0
    assert service.page(PLAYER).counts["you"] == 2
    with pytest.raises(WorkflowError):
        service.decide(PLAYER, "stale-accept", before, "accept")
    other = OnboardingStore(
        ledger.engine, ledger.policy.model_copy(update={"campaign_id": uuid4(), "guild_id": 300})
    )
    actor = GuildViewer(2, 300, True, False)
    seed(other, actor)
    assert InboxService(other).page(actor).total == 0
    with pytest.raises(WorkflowError):
        service.page(actor)
    with ledger.engine.begin() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.user_id == str(PLAYER.user_id))
            .values(active=False)
        )
    with pytest.raises(WorkflowError):
        service.page(PLAYER)


def request(viewer, key, custom_id=None):
    result = MagicMock()
    result.user = MagicMock(spec=discord.Member)
    result.user.id = viewer.user_id
    result.user.guild_permissions = discord.Permissions(administrator=viewer.is_administrator)
    result.guild_id, result.id = viewer.guild_id, key
    result.data = {"custom_id": custom_id}
    result.response.defer = AsyncMock()
    result.response.edit_message = AsyncMock()
    result.edit_original_response = AsyncMock()
    return result


def test_guided_view_mutations_rapid_click_guard_filters_refresh_and_close(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service, bond, shared = mixed(ledger)

    async def run():
        view = InboxView(service, PLAYER.user_id)
        view.overview = False
        await view.present(request(PLAYER, 1))
        assert not await view.interaction_check(request(OTHER, 2))
        assert view.primary.label == "Accept setup" and view.primary in view.children
        assert not view.primary.disabled
        original_id = view.primary.custom_id
        await view.primary.callback(request(PLAYER, 3, original_id))
        assert service.page(PLAYER).counts["history"] == 1
        assert view.primary not in view.children
        assert view.secondary not in view.children
        assert view.overview
        # A second click from the old panel cannot approve whatever is shown next.
        await view.primary.callback(request(PLAYER, 4, original_id))
        assert service.bonds.get(PLAYER, bond["id"])["state"] == "pending"
        assert service.page(PLAYER).counts["history"] == 1
        await view.history.callback(request(PLAYER, 5))
        assert view.page.item.identity == shared["id"]
        await view.refresh.callback(request(PLAYER, 6))
        await view.close.callback(request(PLAYER, 7))
        assert service.page(PLAYER).counts["pending"] == 1
        reopened = InboxView(service, PLAYER.user_id)
        await reopened.present(request(PLAYER, 8))
        assert reopened.page.item.identity == bond["id"]
        assert "PRIVATE_OTHER_NOTES" not in json.dumps(reopened.embed().to_dict())
        assert len(reopened.to_components()) <= 5

    asyncio.run(run())


def test_stale_accept_disabled_and_court_task_opens_authorized_recipient_picker(
    ledger, monkeypatch
):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service, bond, row = mixed(ledger)
    service.shared.decide(PLAYER, "decline", row["id"], 1, "decline")

    async def run():
        view = InboxView(service, OTHER.user_id)
        view.overview = False
        view.category = "court"
        await view.present(request(OTHER, 10))
        assert view.page.item.task == "court"
        source = request(OTHER, 11, view.primary.custom_id)
        await view.primary.callback(source)
        picker = source.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, CourtRecipient)
        assert not await picker.interaction_check(request(PLAYER, 12))
        selector = next(x for x in picker.children if isinstance(x, discord.ui.UserSelect))
        member = MagicMock(spec=discord.Member)
        member.id = PLAYER.user_id
        selector._values = [member]
        selected = request(OTHER, 13)
        await selector.callback(selected)
        child = selected.edit_original_response.call_args.kwargs["view"]
        assert child.kind == "court" and child.target == PLAYER.user_id
        assert any(
            isinstance(x, discord.ui.Button) and x.label == "Back to requests"
            for x in child.children
        )
        # The picker opened a form, not a saved allocation/request.
        assert service.page(OTHER, category="court").item.task == "court"
        ledger.save_draft(
            PLAYER,
            "changed",
            1,
            DraftInput(callsign="PLAYER", girl_playbook="AM", frame_playbook="JANUS-B"),
        )
        inbound = InboxView(service, OTHER.user_id)
        inbound.overview = False
        await inbound.present(request(OTHER, 14))
        # Pending Bond is now stale, but declining remains available.
        inbound.category = "bonds"
        await inbound.present(request(OTHER, 15))
        assert inbound.primary.disabled and inbound.secondary.label == "Decline"

    asyncio.run(run())


def test_inbox_navigation_has_separate_budget_without_weakening_mutations():
    from girlframe.discord_adapter.onboarding import allow_action

    assert all(allow_action(987654, 876543, "inbox_read", now=100) for _ in range(20))
    assert not allow_action(987654, 876543, "inbox_read", now=100)
    assert all(allow_action(987654, 876543, "metadata", now=100) for _ in range(3))
    assert not allow_action(987654, 876543, "metadata", now=100)
    assert allow_action(987654, 876543, "inbox_read", now=111)


def test_old_accept_button_cannot_approve_the_next_incoming_request(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service, bond, shared = mixed(ledger)
    peer = GuildViewer(4, 200, True, False)
    seed(ledger, peer)
    service.bonds.propose(
        peer, "second-incoming", 1, 1, BondProposal(target_id=PLAYER.user_id, prompt=0)
    )

    async def run():
        view = InboxView(service, PLAYER.user_id)
        view.overview = False
        await view.present(request(PLAYER, 100))
        assert view.page.item.source == "bond" and view.page.item.incoming
        old = view.primary.custom_id
        await view.primary.callback(request(PLAYER, 101, old))
        assert view.page.item.identity == shared["id"] and view.page.item.incoming
        assert not view.primary.disabled
        await view.primary.callback(request(PLAYER, 102, old))
        assert service.shared.get(PLAYER, shared["id"])["state"] == "pending"
        assert service.page(PLAYER).counts["history"] == 1

    asyncio.run(run())


@pytest.mark.parametrize("route", ["mentor_start", "callsign", "pair", "describe"])
def test_guided_task_routes_and_back_keep_existing_service_boundaries(ledger, monkeypatch, route):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    if route == "mentor_start":
        handler = handler_ready(ledger, "NEWGIRL")
        handler.mentor(
            ADMIN,
            "nominate",
            1,
            PilotRef(user_id=PLAYER.user_id, character_revision=2),
            PilotRef(user_id=OTHER.user_id, character_revision=1),
        )
        actor = PLAYER
    elif route == "callsign":
        mentor_ready(ledger)
        actor = OTHER
    else:
        pair, bonds, identity = pair_ready(ledger)
        actor = OTHER
        if route == "describe":
            pair.choose(
                OTHER,
                "choose",
                identity,
                2,
                0,
                PairNames(names=("Radio Implant", "Magnetic Bands")),
            )
            actor = PLAYER
    service = InboxService(ledger)

    async def run():
        view = InboxView(service, actor.user_id)
        view.overview = False
        await view.present(request(actor, 201))
        assert view.page.item.task == route
        click = request(actor, 202, view.primary.custom_id)
        await view.primary.callback(click)
        data = click.edit_original_response.call_args.kwargs
        child = data["view"]
        assert data["embed"] is None
        back = next(
            x
            for x in child.children
            if isinstance(x, discord.ui.Button) and x.label == "Back to requests"
        )
        assert len(child.to_components()) <= 5
        await back.callback(request(actor, 203))
        assert view.page.item.task == route
        # Opening and returning never completes a task or sends a proposal.
        assert service.page(actor).item.task == route

    asyncio.run(run())


def test_recommended_overview_opens_version_bound_review_and_returns(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding
    from girlframe.discord_adapter.inbox import RequestSelect

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service, bond, shared = mixed(ledger)

    async def run():
        view = InboxView(service, PLAYER.user_id)
        await view.present(request(PLAYER, 301))
        assert view.overview and view.primary not in view.children
        assert view.embed().title == "Your requests"
        assert len(view.page.window) == 2
        select = next(x for x in view.children if isinstance(x, RequestSelect))
        select._values = ["shared:" + shared["id"]]
        await select.callback(request(PLAYER, 302))
        assert not view.overview and view.page.item.identity == shared["id"]
        assert view.primary in view.children and view.back in view.children
        assert any(x.name == "What this action changes" for x in view.embed().fields)
        assert len(view.to_components()) <= 5
        await view.back.callback(request(PLAYER, 303))
        assert view.overview
        # A menu from an older overview cannot silently select a different record.
        stale_select = next(x for x in view.children if isinstance(x, RequestSelect))
        stale_select._values = ["shared:" + shared["id"]]
        service.shared.decide(OTHER, "withdraw-old", shared["id"], 1, "withdraw")
        stale = request(PLAYER, 304)
        await stale_select.callback(stale)
        assert view.overview and view.primary not in view.children
        assert "changed" in stale.edit_original_response.call_args.kwargs["embed"].description
        assert service.bonds.get(PLAYER, bond["id"])["state"] == "pending"

    asyncio.run(run())


def test_overview_pages_five_requests_with_native_next_previous(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding
    from girlframe.discord_adapter.inbox import RequestSelect

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    seed(ledger)
    service = InboxService(ledger)
    for i in range(7):
        peer = GuildViewer(100 + i, 200, True, False)
        seed(ledger, peer)
        service.bonds.propose(
            peer, "request-" + str(i), 1, 1, BondProposal(target_id=PLAYER.user_id, prompt=0)
        )

    async def run():
        view = InboxView(service, PLAYER.user_id)
        await view.present(request(PLAYER, 401))
        first = [x.key for x in view.page.window]
        assert len(first) == 5 and view.page.total == 7
        await view.next.callback(request(PLAYER, 402))
        assert view.overview and view.page.index == 5 and len(view.page.window) == 2
        assert set(first).isdisjoint(x.key for x in view.page.window)
        assert view.next.disabled and not view.previous.disabled
        menu = next(x for x in view.children if isinstance(x, RequestSelect))
        menu._values = [view.page.window[-1].key]
        await menu.callback(request(PLAYER, 403))
        assert not view.overview and view.page.index == 6
        await view.back.callback(request(PLAYER, 404))
        assert view.overview and view.page.index == 5
        await view.previous.callback(request(PLAYER, 405))
        assert view.page.index == 0

    asyncio.run(run())
