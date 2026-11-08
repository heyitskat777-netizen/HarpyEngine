import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import discord
import pytest
from sqlalchemy.exc import IntegrityError
from test_creation import selected
from test_ledger import ADMIN, OTHER, PLAYER, seed
from test_ledger import ledger as ledger_fixture

from girlframe.database import tables as t
from girlframe.discord_adapter.creation import CreationView
from girlframe.discord_adapter.handler_setup import ConfirmSetup, RankView
from girlframe.discord_adapter.npc_bonds import NpcModal, NpcView
from girlframe.engine.bonds import BondProposal
from girlframe.engine.creation import CreationDraft
from girlframe.engine.drafts import DraftInput
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.npc_bonds import NPC_ROLES, NpcBond
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

ledger = ledger_fixture


def ready(ledger, girl="MOCKINGBIRD"):
    seed(ledger)
    seed(ledger, OTHER)
    if girl != "MOCKINGBIRD":
        ledger.save_draft(
            PLAYER,
            "girl",
            1,
            DraftInput(callsign="SYNTH", girl_playbook=girl, frame_playbook="JANUS-B"),
        )
    ledger.join(ADMIN, "join-handler")
    service = HandlerService(ledger)
    service.appoint(ADMIN, "appoint", 0, ADMIN.user_id)
    return service


def refs(service):
    prepared = service.roster(ADMIN)
    return prepared, tuple(
        PilotRef(user_id=user, character_revision=data["revision"])
        for user, data in prepared["pilots"].items()
    )


@pytest.mark.parametrize("girl", NPC_ROLES)
def test_npc_choice_branches_optional_feelings_and_legacy(girl):
    complete = selected(girl)
    assert len(NPC_ROLES[girl]) == 4
    assert not any("NPC" in requirement for requirement in complete.missing())
    old = complete.model_dump(mode="json", exclude={"npc_bonds"})
    restored = CreationDraft.model_validate_json(json.dumps(old))
    assert any("NPC" in x for x in restored.missing())
    assert restored.npc_bonds == ()
    if girl == "OLDGEN":
        assert any(
            "two NPC" in x
            for x in complete.model_copy(update={"npc_bonds": (NpcBond(slot=0),)}).missing()
        )
    for values in [
        (NpcBond(slot=0), NpcBond(slot=0)),
        (NpcBond(slot=0), NpcBond(slot=1), NpcBond(slot=2)),
    ]:
        with pytest.raises(ValueError):
            CreationDraft.model_validate(complete.model_dump() | {"npc_bonds": values})
    with pytest.raises(ValueError):
        NpcBond(slot=4)


def test_appointment_authority_and_revocation_including_replay(ledger):
    service = ready(ledger)
    prepared, order = refs(service)
    with pytest.raises(WorkflowError):
        service.appoint(PLAYER, "forge-admin", 1, PLAYER.user_id)
    with pytest.raises(WorkflowError):
        service.rank(PLAYER, "forge-handler", 1, order)
    with pytest.raises(WorkflowError):
        service.appoint(ADMIN, "not-joined", 1, 999)
    ranked = service.rank(ADMIN, "rank", 1, order)
    assert ranked == service.rank(ADMIN, "rank", 1, order)
    assert not service.view(PLAYER)["status_stale"]
    service.appoint(ADMIN, "revoke", 2, None)
    with pytest.raises(WorkflowError):
        service.rank(ADMIN, "rank", 1, order)
    assert service.view(PLAYER)["status_order"] == []
    with ledger.engine.begin() as connection:
        connection.execute(
            t.members.update().where(t.members.c.user_id == str(ADMIN.user_id)).values(active=False)
        )
    with pytest.raises(WorkflowError):
        service.roster(ADMIN)


def test_status_roster_princess_revision_and_unique_ranks(ledger):
    service = ready(ledger, "PRINCESS")
    prepared, order = refs(service)
    with pytest.raises(WorkflowError, match="Princess"):
        service.rank(ADMIN, "wrong-ace", 1, tuple(reversed(order)))
    with pytest.raises(WorkflowError):
        service.rank(ADMIN, "duplicates", 1, (order[0], order[0]))
    assert service.rank(ADMIN, "correct", 1, order)["revision"] == 2
    assert [x["user_id"] for x in service.view(OTHER)["status_order"]] == [
        PLAYER.user_id,
        OTHER.user_id,
    ]
    ledger.save_draft(
        OTHER,
        "profile-update",
        1,
        DraftInput(callsign="OTHER", girl_playbook="PRINCESS", frame_playbook="JANUS-B"),
    )
    assert service.view(PLAYER)["status_stale"]
    with pytest.raises(WorkflowError, match="STALE_PROFILE"):
        service.rank(ADMIN, "old-profile", 2, order)
    _, current = refs(service)
    with pytest.raises(WorkflowError, match="multiple Princesses"):
        service.rank(ADMIN, "two-princesses", 2, current)


def test_handler_mentor_nomination_mutual_setup_and_reassignment(ledger):
    service = ready(ledger, "NEWGIRL")
    prepared, order = refs(service)
    source, mentor = order
    bonds = BondService(ledger)
    with pytest.raises(WorkflowError, match="UNSUPPORTED_RULE"):
        bonds.prepare(PLAYER, OTHER.user_id)
    service.mentor(ADMIN, "mentor", 1, source, mentor)
    assert service.view(PLAYER)["mentors"][0]["mentor"]["user_id"] == OTHER.user_id
    prepared = bonds.prepare(PLAYER, OTHER.user_id)
    proposal = bonds.propose(
        PLAYER,
        "mentor-proposal",
        prepared["source_revision"],
        prepared["target_revision"],
        BondProposal(target_id=OTHER.user_id, prompt=0),
    )
    assert bonds.decide(OTHER, "mentor-accept", proposal["id"], 1, "accept")["state"] == "accepted"
    assert ledger.draft(PLAYER)["callsign"] == "SYNTH"
    # Even reassignment to the same person creates a fresh nomination token.
    service.mentor(ADMIN, "mentor-again", 2, source, mentor)
    assert bonds.get(PLAYER, proposal["id"])["stale"]
    assert service.view(PLAYER)["mentors"][0]["stale"] is False
    assert len(service.view(ADMIN)["mentors"]) == 1
    # An unrelated member/administrator gets no private Mentor roster override.
    extra = GuildViewer(4, 200, True, True)
    seed(ledger, extra)
    assert service.view(extra)["mentors"] == []
    service.appoint(ADMIN, "handler-revoke", 3, None)
    with pytest.raises(WorkflowError, match="UNSUPPORTED_RULE"):
        bonds.prepare(PLAYER, OTHER.user_id)
    with pytest.raises(WorkflowError):
        service.mentor(ADMIN, "mentor", 1, source, mentor)


def test_setup_transaction_rollback_concurrency_immutability_and_backup(
    ledger, monkeypatch, tmp_path
):
    from pathlib import Path

    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database

    service = ready(ledger)
    prepared, order = refs(service)
    original = ledger._audit

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Synthetic failure")

    with monkeypatch.context() as patch:
        patch.setattr(ledger, "_audit", fail)
        with pytest.raises(RuntimeError):
            service.rank(ADMIN, "rank", 1, order)
    assert service.view(PLAYER)["revision"] == 1

    def rank(key):
        try:
            return service.rank(ADMIN, key, 1, order)
        except WorkflowError as error:
            return str(error)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(rank, ("rank-a", "rank-b")))
    assert sum(isinstance(x, dict) for x in results) == 1
    assert any("STALE_REVISION" in x for x in results if isinstance(x, str))
    for mutation in (t.setup_revisions.delete(), t.setup_revisions.update().values(body_json="{}")):
        with ledger.engine.begin() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(mutation)
    path = tmp_path / "setup-backup.db"
    copy_database(Path(ledger.engine.url.database), path)
    engine = create_database_engine(Settings(database_url=f"sqlite:///{path}"))
    try:
        assert HandlerService(OnboardingStore(engine, ledger.policy)).view(PLAYER) == service.view(
            PLAYER
        )
    finally:
        engine.dispose()
    other = OnboardingStore(
        ledger.engine, ledger.policy.model_copy(update={"guild_id": 300, "campaign_id": uuid4()})
    )
    viewer = GuildViewer(2, 300, True, False)
    seed(other, viewer)
    assert HandlerService(other).view(viewer)["handler_id"] is None
    with pytest.raises(WorkflowError):
        service.view(viewer)


def test_npc_native_controls_private_save_and_stale_form(ledger):
    seed(ledger)
    service = CreationService(ledger)

    async def run():
        parent = CreationView(service, PLAYER.user_id, service.get(PLAYER))
        parent.update(**selected().model_dump(mode="json"))
        view = NpcView(parent)
        assert len(view.children) == 3
        modal = NpcModal(parent)
        modal.fields[0]._value = "Synthetic NPC"
        modal.fields[1]._value = "PRIVATE_NPC_CANARY"
        request = MagicMock()
        request.user = MagicMock(spec=discord.Member)
        request.user.id = PLAYER.user_id
        request.user.guild_permissions = discord.Permissions.none()
        request.guild_id = 200
        request.response.is_done.return_value = True
        request.edit_original_response = AsyncMock()
        await modal.on_submit(request)
        service.save(PLAYER, "npc-save", 0, parent.progress.character_revision, parent.draft)
        assert (
            CreationService(OnboardingStore(ledger.engine, ledger.policy))
            .get(PLAYER)
            .draft.npc_bonds[0]
            .feelings
            == "PRIVATE_NPC_CANARY"
        )
        assert "PRIVATE_NPC_CANARY" not in json.dumps(ledger.public_export())
        assert "PRIVATE_NPC_CANARY" not in json.dumps(ledger.list_events(PLAYER))
        stale = NpcModal(parent)
        parent.update(npc_bonds=[])
        await stale.on_submit(request)
        assert "Choices changed" in request.edit_original_response.call_args.kwargs["content"]
        request.user.id = OTHER.user_id
        assert not await view.interaction_check(request)

    asyncio.run(run())


def test_setup_native_review_confirm_and_owner_guards(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *args, **kwargs: True)
    service = ready(ledger)

    def request(viewer, identity):
        interaction = MagicMock()
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = viewer.user_id
        interaction.user.guild_permissions = discord.Permissions(
            administrator=viewer.is_administrator
        )
        interaction.guild_id, interaction.id = 200, identity
        interaction.response.is_done.return_value = True
        interaction.response.defer = AsyncMock()
        interaction.response.edit_message = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        return interaction

    async def run():
        view = RankView(service, ADMIN.user_id, service.roster(ADMIN))
        assert not await view.interaction_check(request(PLAYER, 200))
        assert view.confirm.disabled
        for user in (PLAYER.user_id, OTHER.user_id):
            selector = next(x for x in view.children if isinstance(x, discord.ui.Select))
            selector._values = [str(user)]
            await selector.callback(request(ADMIN, 201))
        await view.review.callback(request(ADMIN, 202))
        assert not view.confirm.disabled
        confirm = request(ADMIN, 203)

        async def edit_during_ack(**kwargs):
            view.order.reverse()
            view.reviewed = False

        confirm.response.defer = AsyncMock(side_effect=edit_during_ack)
        await view.confirm.callback(confirm)
        assert [x["user_id"] for x in service.view(PLAYER)["status_order"]] == [
            PLAYER.user_id,
            OTHER.user_id,
        ]
        revoke = ConfirmSetup(
            service,
            ADMIN.user_id,
            lambda actor, key: service.appoint(actor, key, 2, None),
            admin=True,
        )
        await revoke.confirm.callback(request(ADMIN, 204))
        assert service.view(PLAYER)["handler_id"] is None

    asyncio.run(run())


def test_migration_preserves_existing_0005_proposals(tmp_path, monkeypatch):
    import sqlite3

    from alembic import command
    from alembic.config import Config
    from test_ledger import ROOT

    path = tmp_path / "old-0005.db"
    monkeypatch.setenv("GIRLFRAME_DATABASE_URL", f"sqlite:///{path}")
    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "0005")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("INSERT INTO campaigns(id,guild_id) VALUES('campaign','200')")
        for user in ("2", "3"):
            connection.execute(
                "INSERT INTO campaign_members(campaign_id,user_id,role) "
                "VALUES('campaign',?,'player')",
                (user,),
            )
            connection.execute(
                "INSERT INTO characters VALUES('campaign',?,?,1,'{}','{}')",
                (user, "synthetic-" + user),
            )
        connection.execute(
            "INSERT INTO events(campaign_id,seq,command_key,actor_id,kind,"
            "payload_json,id,created_utc) "
            "VALUES('campaign',1,'synthetic','2','character.bond_proposed','{}','event','2026-01-01')"
        )
        connection.execute(
            "INSERT INTO creation_bond_revisions VALUES('campaign','proposal',1,'2','3',1,1,"
            "'MOCKINGBIRD',0,'PRIVATE_OLD_CONTEXT','pending','event')"
        )
        before = connection.execute("SELECT * FROM creation_bond_revisions").fetchone()
        columns = [
            row[1] for row in connection.execute("PRAGMA table_info(creation_bond_revisions)")
        ]
    command.upgrade(config, "head")
    command.check(config)
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT " + ",".join(columns) + " FROM creation_bond_revisions"
            ).fetchone()
            == before
        )
        assert connection.execute(
            "SELECT mentor_assignment_id FROM creation_bond_revisions"
        ).fetchone() == (None,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_handler_account_is_outside_starting_pilot_bond_roster(ledger):
    seed(ledger)
    seed(ledger, OTHER)
    seed(ledger, ADMIN)
    bonds = BondService(ledger)
    assert bonds.prepare(PLAYER, ADMIN.user_id)["source_revision"] == 1
    proposal = bonds.propose(
        PLAYER, "before-appointment", 1, 1, BondProposal(target_id=ADMIN.user_id, prompt=0)
    )
    service = HandlerService(ledger)
    service.appoint(ADMIN, "appoint", 0, ADMIN.user_id)
    assert ADMIN.user_id not in service.roster(ADMIN)["pilots"]
    assert bonds.get(PLAYER, proposal["id"])["stale"]
    with pytest.raises(WorkflowError):
        bonds.prepare(PLAYER, ADMIN.user_id)
    with pytest.raises(WorkflowError):
        bonds.prepare(ADMIN, OTHER.user_id)
    with pytest.raises(WorkflowError, match="STALE_PROFILE"):
        bonds.decide(ADMIN, "accept-as-handler", proposal["id"], 1, "accept")
