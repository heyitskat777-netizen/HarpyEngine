import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import discord
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from test_ledger import ADMIN, OTHER, PLAYER, seed
from test_ledger import ledger as ledger_fixture

from girlframe.database import tables as t
from girlframe.discord_adapter.shared_setup import CallsignModal, ChoiceView, RequestView
from girlframe.engine.bonds import BondProposal
from girlframe.engine.drafts import DraftInput
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.shared_setup import AM_ROLES, CallsignChoice, CourtChoice
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.shared_setup import SharedSetupService

ledger = ledger_fixture


def court_ready(ledger):
    seed(ledger)
    seed(ledger, OTHER)
    ledger.save_draft(
        PLAYER,
        "red-queen",
        1,
        DraftInput(
            callsign="SYNTH",
            girl_playbook="MOCKINGBIRD",
            frame_playbook="THE RED QUEEN",
            notes="PRIVATE_SOURCE_CANARY",
        ),
    )
    return SharedSetupService(ledger)


def court(service, key="court", role="The Queen"):
    prepared = service.prepare(PLAYER, OTHER.user_id, "court")
    return service.propose(PLAYER, key, OTHER.user_id, "court", prepared, CourtChoice(role=role))


def mentor_ready(ledger):
    seed(ledger)
    seed(ledger, OTHER)
    ledger.save_draft(
        PLAYER,
        "newgirl",
        1,
        DraftInput(
            callsign="PLACEHOLDER",
            girl_playbook="NEWGIRL",
            frame_playbook="JANUS-B",
            notes="PRIVATE_NEWGIRL_CANARY",
        ),
    )
    ledger.join(ADMIN, "handler-join")
    handler = HandlerService(ledger)
    handler.appoint(ADMIN, "appoint", 0, ADMIN.user_id)
    handler.mentor(
        ADMIN,
        "mentor",
        1,
        PilotRef(user_id=PLAYER.user_id, character_revision=2),
        PilotRef(user_id=OTHER.user_id, character_revision=1),
    )
    bonds = BondService(ledger)
    row = bonds.propose(
        PLAYER, "mentor-bond", 2, 1, BondProposal(target_id=OTHER.user_id, prompt=0)
    )
    bonds.decide(OTHER, "bond-accept", row["id"], 1, "accept")
    return SharedSetupService(ledger), handler, bonds, row["id"]


@pytest.mark.parametrize("role", AM_ROLES)
def test_court_all_roles_exact_four_one_and_owner_provenance(ledger, role):
    service = court_ready(ledger)
    creation = CreationService(ledger)
    old = creation.get(PLAYER)
    row = court(service, role=role)
    assert creation.get(PLAYER).shared_choices == ()
    service.decide(OTHER, "accept", row["id"], 1, "accept")
    current = creation.get(PLAYER)
    choice = current.shared_choices[0]
    assert choice.kind == "court" and choice.value == role
    assert list(choice.allocation.values()).count(PLAYER.user_id) == 4
    assert list(choice.allocation.values()).count(OTHER.user_id) == 1
    assert choice.allocation[role] == OTHER.user_id
    assert current.draft.shared_tokens == (choice.token,)
    with pytest.raises(WorkflowError, match="STALE_SETUP"):
        creation.save(PLAYER, "stale-form", 0, 2, old.draft)
    creation.save(PLAYER, "current-form", 0, 2, current.draft)
    with ledger.engine.connect() as connection:
        body = json.loads(connection.scalar(sa.select(t.creation_drafts.c.body_json)))
        assert body["shared_tokens"] == [choice.token]
    assert "PRIVATE_SOURCE_CANARY" not in json.dumps(service.get(OTHER, row["id"]))


def test_court_invalid_source_recipient_choices_and_private_admin_denial(ledger):
    service = court_ready(ledger)
    seed(ledger, ADMIN)
    with pytest.raises(ValueError):
        CourtChoice(role="Invented")
    with pytest.raises(ValueError):
        CourtChoice(role="The Queen", second_role="The Knight")
    for actor, target in [(OTHER, PLAYER.user_id), (PLAYER, PLAYER.user_id), (PLAYER, 999)]:
        with pytest.raises(WorkflowError):
            service.prepare(actor, target, "court")
    row = court(service)
    with pytest.raises(WorkflowError):
        service.get(ADMIN, row["id"])
    assert service.list(ADMIN) == []
    with pytest.raises(WorkflowError):
        service.decide(PLAYER, "self-accept", row["id"], 1, "accept")
    with pytest.raises(WorkflowError):
        court(service, key="duplicate")
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        court(service, role="The Doll")


def test_shared_decline_withdraw_replay_and_revocation(ledger):
    service = court_ready(ledger)
    row = court(service)
    assert row == court(service)
    result = service.decide(OTHER, "accept", row["id"], 1, "accept")
    assert result == service.decide(OTHER, "accept", row["id"], 1, "accept")
    service.decide(PLAYER, "withdraw", row["id"], 2, "withdraw")
    assert CreationService(ledger).get(PLAYER).shared_choices == ()
    with pytest.raises(WorkflowError):
        service.decide(OTHER, "accept", row["id"], 1, "accept")
    second = court(service, "second")
    assert service.decide(OTHER, "decline", second["id"], 1, "decline")["state"] == "declined"
    third = court(service, "third")
    with ledger.engine.begin() as connection:
        connection.execute(
            t.members.update().where(t.members.c.user_id == str(OTHER.user_id)).values(active=False)
        )
    with pytest.raises(WorkflowError):
        service.decide(OTHER, "revoked", third["id"], 1, "accept")
    assert service.get(PLAYER, third["id"])["stale"]


def test_mentor_callsign_authority_mutual_agreement_and_assignment_staleness(ledger):
    service, handler, bonds, identity = mentor_ready(ledger)
    with pytest.raises(WorkflowError):
        service.prepare(PLAYER, OTHER.user_id, "callsign")
    for name in ("", "BAD\nNAME", "x" * 33):
        with pytest.raises(ValueError):
            CallsignChoice(callsign=name)
    prepared = service.prepare(OTHER, PLAYER.user_id, "callsign")
    row = service.propose(
        OTHER, "name", PLAYER.user_id, "callsign", prepared, CallsignChoice(callsign="SORROW")
    )
    with pytest.raises(WorkflowError):
        service.decide(OTHER, "self-accept", row["id"], 1, "accept")
    service.decide(PLAYER, "name-accept", row["id"], 1, "accept")
    saved = CreationService(ledger).get(PLAYER)
    assert saved.shared_choices[0].value == "SORROW"
    assert ledger.draft(PLAYER)["callsign"] == "PLACEHOLDER"
    assert "PRIVATE_NEWGIRL_CANARY" not in json.dumps(service.get(OTHER, row["id"]))
    handler.mentor(
        ADMIN,
        "reassign",
        2,
        PilotRef(user_id=PLAYER.user_id, character_revision=2),
        PilotRef(user_id=OTHER.user_id, character_revision=1),
    )
    assert CreationService(ledger).get(PLAYER).shared_choices == ()
    assert service.get(PLAYER, row["id"])["stale"]
    with pytest.raises(WorkflowError):
        service.decide(PLAYER, "name-accept", row["id"], 1, "accept")
    with pytest.raises(WorkflowError):
        service.propose(
            OTHER, "name", PLAYER.user_id, "callsign", prepared, CallsignChoice(callsign="SORROW")
        )


def test_effective_status_mentor_override_handler_and_stale_order(ledger):
    service, handler, bonds, identity = mentor_ready(ledger)
    order = (
        PilotRef(user_id=PLAYER.user_id, character_revision=2),
        PilotRef(user_id=OTHER.user_id, character_revision=1),
    )
    handler.rank(ADMIN, "order", 2, order)
    assert service.effective_status(OTHER, PLAYER.user_id) == {
        "higher": True,
        "basis": "Mentor exception",
    }
    assert service.effective_status(PLAYER, OTHER.user_id) == {
        "higher": False,
        "basis": "Mentor exception",
    }
    assert service.effective_status(ADMIN, PLAYER.user_id)["higher"] is True
    bonds.decide(PLAYER, "withdraw-bond", identity, 2, "withdraw")
    assert service.effective_status(OTHER, PLAYER.user_id) == {
        "higher": False,
        "basis": "starting Status",
    }
    ledger.save_draft(
        OTHER,
        "changed",
        1,
        DraftInput(callsign="OTHER", girl_playbook="ALPHA", frame_playbook="JANUS-B"),
    )
    assert service.effective_status(PLAYER, OTHER.user_id)["higher"] is None


def test_shared_rollback_concurrency_history_backup_and_isolation(ledger, monkeypatch, tmp_path):
    from pathlib import Path

    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database

    service = court_ready(ledger)
    original = ledger._audit

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Synthetic failure after event")

    with monkeypatch.context() as patch:
        patch.setattr(ledger, "_audit", fail)
        with pytest.raises(RuntimeError):
            court(service)
    assert service.list(PLAYER) == []
    row = court(service)

    def decide(decision):
        try:
            return service.decide(OTHER, decision, row["id"], 1, decision)
        except WorkflowError as error:
            return str(error)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(decide, ("accept", "decline")))
    assert sum(isinstance(x, dict) for x in results) == 1
    assert len(service.list(OTHER)) == 1
    for mutation in (
        t.shared_setup_revisions.delete(),
        t.shared_setup_revisions.update().values(choice_json="{}"),
    ):
        with ledger.engine.begin() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(mutation)
    with ledger.engine.connect() as connection:
        assert all(
            "role" not in text
            for text in connection.execute(sa.select(t.events.c.payload_json)).scalars()
        )
    path = tmp_path / "shared-backup.db"
    copy_database(Path(ledger.engine.url.database), path)
    engine = create_database_engine(Settings(database_url=f"sqlite:///{path}"))
    try:
        assert SharedSetupService(OnboardingStore(engine, ledger.policy)).get(
            PLAYER, row["id"]
        ) == service.get(PLAYER, row["id"])
    finally:
        engine.dispose()
    other = OnboardingStore(
        ledger.engine, ledger.policy.model_copy(update={"guild_id": 300, "campaign_id": uuid4()})
    )
    viewer = GuildViewer(2, 300, True, False)
    seed(other, viewer)
    assert SharedSetupService(other).list(viewer) == []
    with pytest.raises(WorkflowError):
        SharedSetupService(other).get(viewer, row["id"])


def test_native_court_and_callsign_requests(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service = court_ready(ledger)

    def request(viewer, key):
        interaction = MagicMock()
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = viewer.user_id
        interaction.user.guild_permissions = discord.Permissions.none()
        interaction.guild_id, interaction.id = 200, key
        interaction.response.is_done.return_value = True
        interaction.response.defer = AsyncMock()
        interaction.response.edit_message = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        return interaction

    async def run():
        view = ChoiceView(
            service,
            PLAYER.user_id,
            OTHER.user_id,
            "court",
            service.prepare(PLAYER, OTHER.user_id, "court"),
        )
        assert not await view.interaction_check(request(OTHER, 1))
        select = next(x for x in view.children if isinstance(x, discord.ui.Select))
        select._values = ["The Queen"]
        await select.callback(request(PLAYER, 2))
        await view.confirm.callback(request(PLAYER, 3))
        row = service.list(OTHER)[0]
        recipient = RequestView(service, OTHER.user_id, row)
        assert not recipient.accept.disabled
        assert RequestView(service, PLAYER.user_id, row).accept.disabled
        await recipient.accept.callback(request(OTHER, 4))
        assert (
            CreationService(ledger).get(PLAYER).shared_choices[0].allocation["The Queen"]
            == OTHER.user_id
        )
        # A modal checks owner and rejects an older form after another input changed.
        name_view = ChoiceView(service, PLAYER.user_id, OTHER.user_id, "callsign", {})
        form = CallsignModal(name_view)
        form.callsign._value = "SYNTHETIC_NAME"
        name_view.generation += 1
        stale = request(PLAYER, 5)
        await form.on_submit(stale)
        assert "Choice changed" in stale.edit_original_response.call_args.kwargs["content"]
        assert name_view.choice is None

    asyncio.run(run())


def test_native_mentor_name_and_private_builder_provenance(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service, handler, bonds, identity = mentor_ready(ledger)

    def request(viewer, key):
        interaction = MagicMock()
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = viewer.user_id
        interaction.user.guild_permissions = discord.Permissions.none()
        interaction.guild_id, interaction.id = 200, key
        interaction.response.is_done.return_value = True
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        return interaction

    async def run():
        view = ChoiceView(
            service,
            OTHER.user_id,
            PLAYER.user_id,
            "callsign",
            service.prepare(OTHER, PLAYER.user_id, "callsign"),
        )
        modal = CallsignModal(view)
        modal.callsign._value = "PRIVATE_NAME_CANARY"
        await modal.on_submit(request(OTHER, 301))
        assert view.choice.callsign == "PRIVATE_NAME_CANARY"
        await view.confirm.callback(request(OTHER, 302))
        row = service.list(PLAYER)[0]
        recipient = RequestView(service, PLAYER.user_id, row)
        await recipient.accept.callback(request(PLAYER, 303))
        creation = CreationService(ledger)
        current = creation.get(PLAYER)
        assert current.shared_choices[0].value == "PRIVATE_NAME_CANARY"
        with pytest.raises(WorkflowError, match="STALE_SETUP"):
            creation.save(
                PLAYER,
                "forged-token",
                0,
                2,
                current.draft.model_copy(update={"shared_tokens": ("callsign:fake",)}),
            )
        creation.save(PLAYER, "name-provenance", 0, 2, current.draft)
        assert ledger.draft(PLAYER)["callsign"] == "PLACEHOLDER"
        assert "PRIVATE_NAME_CANARY" not in json.dumps(ledger.public_export())
        assert "PRIVATE_NAME_CANARY" not in json.dumps(ledger.list_events(PLAYER))

    asyncio.run(run())


def test_setup_request_pagination_and_profile_change(ledger):
    service = court_ready(ledger)
    for index in range(21):
        row = court(service, key="court-" + str(index))
        service.decide(OTHER, "decline-" + str(index), row["id"], 1, "decline")
    first = service.list(PLAYER)
    second = service.list(PLAYER, first[-1]["id"])
    assert len(first) == 20 and len(second) == 1
    assert len({x["id"] for x in first + second}) == 21
    row = court(service, key="last")
    ledger.save_draft(
        OTHER,
        "profile",
        1,
        DraftInput(callsign="OTHER", girl_playbook="ALPHA", frame_playbook="JANUS-B"),
    )
    assert service.get(PLAYER, row["id"])["stale"]
    with pytest.raises(WorkflowError):
        service.decide(OTHER, "stale-accept", row["id"], 1, "accept")
