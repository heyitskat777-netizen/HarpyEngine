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
from girlframe.discord_adapter.bonds import ContextModal, DecisionView, ProposalView, proposal_text
from girlframe.engine.bonds import PROMPTS, BondProposal, starting_kind, starting_role
from girlframe.engine.drafts import DraftInput
from girlframe.services.bonds import BondService
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
    return BondService(ledger)


def propose(service, key="proposal", context="SHARED_PRIVATE_CANARY"):
    prepared = service.prepare(PLAYER, OTHER.user_id)
    return service.propose(
        PLAYER,
        key,
        prepared["source_revision"],
        prepared["target_revision"],
        BondProposal(target_id=OTHER.user_id, prompt=0, context=context),
    )


@pytest.mark.parametrize("girl", PROMPTS)
def test_starting_branch_and_source_depth(ledger, girl):
    service = ready(ledger, girl)
    if girl == "NEWGIRL":
        with pytest.raises(WorkflowError, match="UNSUPPORTED_RULE"):
            propose(service)
        assert service.list(PLAYER) == []
        return
    result = propose(service)
    row = service.get(OTHER, result["id"])
    assert starting_kind(girl) == ("Intense" if girl == "BONDED" else "Personal")
    assert starting_role(girl) == {"NEWGIRL": "Mentor", "BONDED": "Pair"}.get(girl, "Girl")
    assert row["state"] == "pending" and row["girl_playbook"] == girl
    assert ("Jailbroken" in proposal_text(row)) == (girl == "AM")


def test_two_party_decisions_replay_history_and_privacy(ledger):
    service = ready(ledger)
    result = propose(service)
    assert propose(service) == result
    assert service.get(PLAYER, result["id"])["context"] == "SHARED_PRIVATE_CANARY"
    seed(ledger, ADMIN)
    for operation in [
        lambda: service.get(ADMIN, result["id"]),
        lambda: service.decide(PLAYER, "forged", result["id"], 1, "accept"),
    ]:
        with pytest.raises(WorkflowError):
            operation()
    assert service.list(ADMIN) == []
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        propose(service, context="Changed")
    accepted = service.decide(OTHER, "accept", result["id"], 1, "accept")
    assert accepted["state"] == "accepted"
    assert service.decide(OTHER, "accept", result["id"], 1, "accept") == accepted
    assert service.decide(PLAYER, "withdraw", result["id"], 2, "withdraw")["state"] == "withdrawn"
    with pytest.raises(WorkflowError):
        service.decide(OTHER, "late", result["id"], 1, "accept")
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.bond_revisions)) == 3
        for _table, column in [
            (t.events, t.events.c.payload_json),
            (t.commands, t.commands.c.outcome_json),
        ]:
            assert all(
                "SHARED_PRIVATE_CANARY" not in x for x in c.execute(sa.select(column)).scalars()
            )
    assert "SHARED_PRIVATE_CANARY" not in str(ledger.public_export())
    for action in (t.bond_revisions.update().values(context="changed"), t.bond_revisions.delete()):
        with ledger.engine.begin() as c:
            with pytest.raises(IntegrityError):
                c.execute(action)
    assert ledger.draft(PLAYER)["status"] == "draft_rules_unverified"


def test_profile_staleness_revocation_and_isolation(ledger):
    service = ready(ledger)
    result = propose(service)
    ledger.save_draft(
        OTHER,
        "edit",
        1,
        DraftInput(callsign="UPDATED", girl_playbook="ALPHA", frame_playbook="JANUS-B"),
    )
    assert service.get(OTHER, result["id"])["stale"]
    with pytest.raises(WorkflowError, match="STALE_PROFILE"):
        service.decide(OTHER, "stale", result["id"], 1, "accept")
    service.decide(OTHER, "decline", result["id"], 1, "decline")
    fresh = propose(service, "fresh")
    with ledger.engine.begin() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.user_id == str(PLAYER.user_id))
            .values(active=False)
        )
    assert service.get(OTHER, fresh["id"])["stale"]
    with pytest.raises(WorkflowError):
        propose(service, "fresh")
    with pytest.raises(WorkflowError):
        service.decide(OTHER, "stale-2", fresh["id"], 1, "accept")
    other = OnboardingStore(
        ledger.engine, ledger.policy.model_copy(update={"guild_id": 300, "campaign_id": uuid4()})
    )
    viewer = GuildViewer(2, 300, True, False)
    seed(other, viewer)
    assert BondService(other).list(viewer) == []
    with pytest.raises(WorkflowError):
        BondService(other).get(viewer, fresh["id"])
    with pytest.raises(WorkflowError):
        service.get(viewer, fresh["id"])


def test_concurrent_decisions_atomic_failure_and_restart_backup(ledger, monkeypatch, tmp_path):
    from pathlib import Path

    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database

    service = ready(ledger)
    original = ledger._audit

    def fail(*a, **kw):
        original(*a, **kw)
        raise RuntimeError("Synthetic failure after event insertion")

    with monkeypatch.context() as patch:
        patch.setattr(ledger, "_audit", fail)
        with pytest.raises(RuntimeError):
            propose(service)
    assert service.list(PLAYER) == []
    result = propose(service)
    with pytest.raises(WorkflowError):
        propose(service, "second")
    with pytest.raises(WorkflowError):
        service.prepare(PLAYER, PLAYER.user_id)

    def decide(choice):
        try:
            return service.decide(OTHER, choice, result["id"], 1, choice)
        except WorkflowError as e:
            return str(e)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(decide, ("accept", "decline")))
    assert sum(isinstance(x, dict) for x in results) == 1
    assert any("STALE_REVISION" in x for x in results if isinstance(x, str))
    path = tmp_path / "bond-backup.db"
    copy_database(Path(ledger.engine.url.database), path)
    engine = create_database_engine(Settings(database_url=f"sqlite:///{path}"))
    try:
        restored = BondService(OnboardingStore(engine, ledger.policy))
        assert restored.get(PLAYER, result["id"]) == service.get(PLAYER, result["id"])
    finally:
        engine.dispose()


def test_private_ui_review_and_recipient_accept(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service = ready(ledger)

    def request(viewer, identity):
        interaction = MagicMock()
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = viewer.user_id
        interaction.user.guild_permissions = discord.Permissions.none()
        interaction.guild_id, interaction.id = viewer.guild_id, identity
        interaction.response.is_done.return_value = True
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        return interaction

    async def run():
        view = ProposalView(
            service, PLAYER.user_id, OTHER.user_id, service.prepare(PLAYER, OTHER.user_id)
        )
        assert not await view.interaction_check(request(OTHER, 10))
        view.prompt = 0
        modal = ContextModal(view)
        modal.context._value = "SHARED_UI_CANARY"
        review = request(PLAYER, 11)
        await modal.on_submit(review)
        confirm = review.edit_original_response.call_args.kwargs["view"]
        assert "SHARED\\_UI\\_CANARY" in review.edit_original_response.call_args.kwargs["content"]
        await confirm.confirm.callback(request(PLAYER, 12))
        row = service.list(OTHER)[0]
        decisions = DecisionView(service, OTHER.user_id, row)
        assert not decisions.accept.disabled and decisions.withdraw.disabled
        actor = DecisionView(service, PLAYER.user_id, row)
        assert actor.accept.disabled and not actor.withdraw.disabled
        await decisions.accept.callback(request(OTHER, 13))
        assert service.get(PLAYER, row["id"])["state"] == "accepted"
        assert not DecisionView(
            service, OTHER.user_id, service.get(OTHER, row["id"])
        ).withdraw.disabled
        assert "SHARED_UI_CANARY" not in json.dumps(ledger.list_events(PLAYER))

    asyncio.run(run())


def test_recipient_withdrawal_and_revoked_replay(ledger):
    service = ready(ledger)
    proposal = propose(service)
    result = service.decide(OTHER, "accept", proposal["id"], 1, "accept")
    assert result["state"] == "accepted"
    assert (
        service.decide(OTHER, "withdraw-own-consent", proposal["id"], 2, "withdraw")["state"]
        == "withdrawn"
    )
    with ledger.engine.begin() as connection:
        connection.execute(
            t.members.update().where(t.members.c.user_id == str(OTHER.user_id)).values(active=False)
        )
    with pytest.raises(WorkflowError):
        service.decide(OTHER, "accept", proposal["id"], 1, "accept")
    assert service.get(PLAYER, proposal["id"])["state"] == "withdrawn"
    assert service.get(PLAYER, proposal["id"])["stale"]
    with pytest.raises(WorkflowError):
        service.prepare(PLAYER, 999)


def test_private_pagination_cursor_has_no_duplicates(ledger):
    service = ready(ledger)
    for i in range(21):
        row = propose(service, "propose-" + str(i))
        service.decide(OTHER, "decline-" + str(i), row["id"], 1, "decline")
    first = service.list(PLAYER)
    second = service.list(PLAYER, first[-1]["id"])
    assert len(first) == 20 and len(second) == 1
    assert len({row["id"] for row in first + second}) == 21
    assert {row["id"] for row in service.list(OTHER)} == {row["id"] for row in first}
