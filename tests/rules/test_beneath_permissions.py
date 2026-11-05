"""Original setter consent is explicit, private and does not erase the affected Tag."""

import asyncio
from uuid import uuid4

import pytest
from test_beneath_service import rolled
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state
from test_mission_ui import current

from girlframe.discord_adapter.m3_tag_permissions import open_permission
from girlframe.engine import m3_beneath as rules
from girlframe.services.inbox import InboxService
from girlframe.services.m3_tag_permissions import PermissionService
from girlframe.services.onboarding import WorkflowError


def locked(store):
    game, worker, gateway, identity = rolled(store, (6, 6))
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("tag", "lock_tag"),
        fields={"tag": "PRIVATE_LOCKED_TAG", "locked_tag": "new"},
        text="Actual confrontation",
    )
    gate = next(x for x in state(game).obligations if x.kind == "tag_rejection_permission")
    return PermissionService(store), game, worker, gateway, gate.id


def test_only_original_setter_can_grant_and_tag_is_not_erased_or_spoken_for(ledger):
    svc, game, _, _, identity = locked(ledger)
    data = svc.get(PLAYER, identity)
    tag = state(game).sheets["3"].tags[-1]
    assert data["can_consent"] and svc.get(OTHER, identity)["active"]
    with pytest.raises(WorkflowError):
        svc.get(ADMIN, identity)
    with pytest.raises(WorkflowError):
        svc.grant(OTHER, "wrong-owner", identity, data["source_sha256"], True)
    result = svc.grant(PLAYER, "grant-once", identity, data["source_sha256"], True)
    assert svc.grant(PLAYER, "grant-once", identity, data["source_sha256"], True) == result
    assert not rules.rejection_blocked(state(game), 3, tag.id)
    assert state(game).sheets["3"].tags[-1] == tag
    assert game.dice.calls == 1 and not tag.rejection_pending


def test_native_permission_and_inbox_are_owned_and_resumable(ledger):
    svc, game, _, _, identity = locked(ledger)
    inbox = InboxService(ledger)
    assert any(
        x.identity == identity and x.task == "m3_tag_permission" and x.incoming
        for x in inbox.items(PLAYER)
    )
    assert any(x.identity == identity and not x.incoming for x in inbox.items(OTHER))
    assert not any(x.identity == identity for x in inbox.items(ADMIN))
    assert "PRIVATE_LOCKED_TAG" not in str(inbox.items(PLAYER))

    async def run():
        owner = current(2, 17001)
        await owner.response.defer(ephemeral=True)
        await open_permission(owner, svc, identity)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values["confirm"] = ("yes",)
        await form.confirm.callback(current(2, 17002))
        assert form.completed and svc.get(OTHER, identity)["allowed"]

    asyncio.run(run())


def test_permission_history_survives_missing_registry_and_pause_but_cannot_mutate(
    ledger, monkeypatch, tmp_path
):
    svc, game, _, _, identity = locked(ledger)
    ledger.safety(OTHER, "pause-permission", ledger.status(OTHER)["revision"], pause=True)
    data = svc.get(PLAYER, identity)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.grant(PLAYER, "paused-consent", identity, data["source_sha256"], True)
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(tmp_path / "missing.json"))
    assert svc.get(OTHER, identity)["active"]
    assert any(x.identity == identity for x in InboxService(ledger).items(PLAYER))
    with pytest.raises(WorkflowError, match="registry is unavailable"):
        svc.grant(PLAYER, "unapproved-consent", identity, data["source_sha256"], True)


def test_changed_original_characters_and_forged_gate_cannot_transfer_permission(ledger):
    svc, game, _, _, identity = locked(ledger)
    data = svc.get(PLAYER, identity)
    with ledger.transaction() as c:
        canon = state(game)
        gate = next(x for x in canon.obligations if x.id == identity)
        gate.details["owner_character"] = str(uuid4())
        game.event(c, 1, "synthetic-forged-gate", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="SOURCE_TAG_PERMISSION_MISSING"):
        svc.get(PLAYER, identity)
    with pytest.raises(WorkflowError, match="SOURCE_TAG_PERMISSION_MISSING"):
        svc.grant(PLAYER, "forged-consent", identity, data["source_sha256"], True)
