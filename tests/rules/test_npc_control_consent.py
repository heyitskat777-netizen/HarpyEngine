"""Bounded NPC handover: both humans consent, authority stays campaign-scoped."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_npc_roles import director
from test_world_service import ready, transfer_npc

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_npc_roles import open_invitation
from girlframe.discord_adapter.m3_world import open_npc_role
from girlframe.engine import m3_npc_roles as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Npc, World
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def prepared(store):
    world, game = ready(store)
    npc = Npc(
        id="existing-npc",
        name="PRIVATE_NAME",
        detail="PRIVATE_DETAIL",
        jobs=("civilian",),
        controller=1,
        cell=(0, 0),
        revealed=True,
    )
    world.npc(ADMIN, "introduce-existing", state(game).revision, npc)
    return world, game, NpcRoleService(world), npc


def offer(roles, game, recipient=PLAYER, controller=ADMIN):
    return roles.offer_transfer(
        controller, str(uuid4()), state(game).revision, "existing-npc", recipient.user_id
    )["id"]


def test_transfer_requires_both_humans_and_preserves_actor_history_replay_and_rebuild(ledger):
    world, game, roles, npc = prepared(ledger)
    before = state(game)
    with pytest.raises(WorkflowError, match="current controller"):
        world.claim_npc(PLAYER, "takeover", before.revision, npc.id)
    with pytest.raises(WorkflowError, match="current controller"):
        roles.offer_transfer(PLAYER, "forged-offer", before.revision, npc.id, 3)
    with pytest.raises(WorkflowError):
        roles.offer(
            ADMIN,
            "duplicate-introduction",
            before.revision,
            npc.model_copy(update={"controller": 2}),
        )
    assert state(game) == before and not world.control_options(PLAYER)["npcs"]
    identity = offer(roles, game)
    assert state(game).world.npcs == before.world.npcs
    assert set(roles.get(PLAYER, identity)["npc"]) == {"id", "name", "jobs", "detail", "controller"}
    with pytest.raises(WorkflowError):
        roles.get(OTHER, identity)
    assert all(x.identity != identity for x in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError, match="invited human"):
        roles.respond(ADMIN, "accept-for-player", identity, state(game).revision, "accept")
    revision = state(game).revision
    result = roles.respond(PLAYER, "actual-accept", identity, revision, "accept")
    after = state(game)
    assert after.world.npcs == (npc.model_copy(update={"controller": 2}),)
    assert roles.respond(PLAYER, "actual-accept", identity, revision, "accept") == result
    assert state(game) == after
    with pytest.raises(WorkflowError, match="current controller"):
        world.claim_npc(ADMIN, "handler-takeback", after.revision, npc.id)
    actors = ActorService(world.missions)
    actor = ActorRef(kind="npc", entity=npc.id)
    assert actor.model_dump(mode="json") in [x["ref"] for x in actors.choices(PLAYER)["actors"]]
    assert actor.model_dump(mode="json") not in [x["ref"] for x in actors.choices(ADMIN)["actors"]]
    with pytest.raises(WorkflowError, match="another human"):
        actors.inspect(ADMIN, actor)
    assert actors.inspect(PLAYER, actor)["actor"]["controller"] == 2
    assert not world.control_options(ADMIN)["npcs"]
    assert World.model_validate_json(after.world.model_dump_json()) == after.world
    game.rebuild()
    assert state(game) == after
    with ledger.engine.connect() as c:
        events = list(c.execute(sa.select(t.events.c.kind, t.events.c.payload_json)))
        assert "PRIVATE_" not in str(events)
        claims = [
            json.loads(payload) for kind, payload in events if kind == "m3.npc_control_claimed"
        ]
        assert len(claims) == 1 and claims[0]["invitation_id"] == identity


def test_decline_withdraw_changed_npc_and_superseded_offer_never_grant_control(ledger):
    world, game, roles, npc = prepared(ledger)
    declined = offer(roles, game)
    roles.respond(PLAYER, "decline", declined, state(game).revision, "decline")
    withdrawn = offer(roles, game)
    roles.respond(ADMIN, "withdraw", withdrawn, state(game).revision, "withdraw")
    assert state(game).world.npcs == (npc,)
    stale = offer(roles, game)
    with ledger.transaction() as c:
        changed = state(game)
        changed.world = update(changed.world, npcs=(npc.model_copy(update={"detail": "Changed"}),))
        game.event(c, 1, "actual-npc-change", "synthetic.actual_npc_change", changed)
    with pytest.raises(WorkflowError, match="STALE_NPC_TRANSFER"):
        roles.respond(PLAYER, "stale-details", stale, state(game).revision, "accept")
    roles.respond(ADMIN, "withdraw-stale", stale, state(game).revision, "withdraw")
    competing = offer(roles, game, OTHER)
    transfer_npc(world, ADMIN, PLAYER, npc.id)
    assert roles.get(OTHER, competing)["state"] == "withdrawn"
    transfer_npc(world, PLAYER, ADMIN, npc.id)
    # Returning to the same original controller cannot resurrect an old offer.
    before = state(game)
    with pytest.raises(WorkflowError, match="pending"):
        roles.respond(OTHER, "replay-old-offer", competing, before.revision, "accept")
    assert state(game) == before


def test_transfer_keeps_membership_guild_pause_release_and_stale_revision_guards(ledger):
    world, game, roles, npc = prepared(ledger)
    for outsider in (GuildViewer(1, 201, True, True), GuildViewer(99, 200, True, True)):
        with pytest.raises(WorkflowError):
            roles.offer_transfer(outsider, str(uuid4()), state(game).revision, npc.id, 2)
    with pytest.raises(WorkflowError, match="current member"):
        roles.offer_transfer(ADMIN, "unknown-recipient", state(game).revision, npc.id, 99)
    identity = offer(roles, game)
    before = state(game)
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        roles.respond(PLAYER, "old-form", identity, before.revision - 1, "accept")
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        roles.respond(PLAYER, "paused", identity, before.revision, "accept")
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        roles.respond(PLAYER, "not-released", identity, before.revision, "accept")
    ledger.policy = policy
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "1")
            .values(active=False)
        )
    with pytest.raises(WorkflowError, match="original controller"):
        roles.respond(PLAYER, "revoked-owner", identity, before.revision, "accept")
    assert state(game) == before
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "1")
            .values(active=True)
        )
    result = roles.respond(PLAYER, "accepted", identity, before.revision, "accept")
    assert result["state"] == "accepted"
    after = state(game)
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
            .values(active=False)
        )
    with pytest.raises(WorkflowError):
        roles.respond(PLAYER, "accepted", identity, before.revision, "accept")
    assert state(game) == after


def test_director_separation_survives_transfer_and_new_unclaimed_invitation_stays_valid(ledger):
    world, game = ready(ledger)
    roles = NpcRoleService(world)
    introduced = roles.offer(ADMIN, "new-director", state(game).revision, director())
    assert not state(game).world.npcs  # Unaccepted introduction is not an unowned canonical NPC.
    roles.respond(PLAYER, "new-director-accept", introduced["id"], state(game).revision, "accept")
    before = state(game)
    with pytest.raises(WorkflowError, match="different human"):
        roles.offer_transfer(PLAYER, "director-to-handler", before.revision, "director", 1)
    # A changed Handler is checked again by the reducer at acceptance.
    proposed = rules.offer_transfer(before.world, 2, "director", 3, "transfer", "source")
    with pytest.raises(ValueError, match="different human"):
        rules.respond(proposed, 3, 3, "transfer", "accept", "reply")
    transfer_npc(world, PLAYER, OTHER, "director")
    assert state(game).world.npcs[0].controller == 3


def test_native_npc_transfer_is_an_offer_until_the_invitee_accepts(ledger):
    world, game, roles, npc = prepared(ledger)

    async def run():
        owner = current(1, 99100)
        await owner.response.defer(ephemeral=True)
        await open_npc_role(owner, world, bond=False)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2))
        form.values["npc"] = (npc.id,)
        form.values["recipient"] = ("2",)
        await form.confirm.callback(current(1, 99101))
        assert form.completed and state(game).world.npcs[0].controller == 1
        invitation = state(game).world.npc_role_offers[0]
        assert any(x.identity == invitation.id for x in InboxService(ledger).items(PLAYER))
        incoming = current(2, 99102)
        await incoming.response.defer(ephemeral=True)
        await open_invitation(incoming, roles, invitation.id)
        answer = incoming.edit_original_response.call_args.kwargs["view"]
        assert not await answer.interaction_check(current(1))
        answer.values["decision"] = ("accept",)
        await answer.confirm.callback(current(2, 99103))
        assert answer.completed and state(game).world.npcs[0].controller == 2

    asyncio.run(run())


def test_transfer_rolls_back_after_event_failure_and_can_withdraw_after_recipient_leaves(
    ledger, monkeypatch
):
    world, game, roles, npc = prepared(ledger)
    identity = offer(roles, game)
    before = state(game)
    original = roles.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic transfer persistence failure")

    monkeypatch.setattr(roles.game, "event", fail)
    with pytest.raises(RuntimeError, match="synthetic"):
        roles.respond(PLAYER, "rollback-transfer", identity, before.revision, "accept")
    assert state(game) == before
    monkeypatch.setattr(roles.game, "event", original)
    roles.respond(PLAYER, "rollback-transfer", identity, before.revision, "accept")
    identity = offer(roles, game, OTHER, PLAYER)
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "3")
            .values(active=False)
        )
    before = state(game)
    with pytest.raises(WorkflowError):
        roles.respond(OTHER, "departed-recipient", identity, before.revision, "accept")
    assert state(game) == before
    roles.respond(PLAYER, "withdraw-departed", identity, before.revision, "withdraw")
    assert state(game).world.npcs[0] == npc.model_copy(update={"controller": 2})
    assert roles.get(PLAYER, identity)["state"] == "withdrawn"
