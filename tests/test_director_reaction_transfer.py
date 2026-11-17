"""NPC control transfer cannot transfer an earlier controller's private reaction draft."""

import pytest
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_director_worldbuilding import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.director_reactions import ReactionProposal
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.director_reactions import DirectorReactionService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.onboarding import WorkflowError

CANARY = "PRIVATE_ORIGINAL_CONTROLLER_REACTION_CANARY"


def test_actual_npc_transfer_never_inherits_old_private_reaction_or_inbox(routed):
    observer, context, scene, game, dice = routed
    world = ready(routed).world
    npc_roles = NpcRoleService(world)
    invitation = npc_roles.offer(
        ADMIN,
        "offer-reaction-npc",
        state(game).revision,
        Npc(
            id="reaction-transfer-npc",
            name="A maintenance contact",
            jobs=("mechanic",),
            detail="Keeps careful maintenance notes.",
            controller=PLAYER.user_id,
            cell=(0, 0),
        ),
    )
    npc_roles.respond(
        PLAYER, "accept-reaction-npc", invitation["id"], state(game).revision, "accept"
    )
    actor = ActorRef(kind="npc", entity="reaction-transfer-npc")
    cast = CastService(ActorService(world.missions))
    current = cast.view(PLAYER, 900)
    cast.change(
        PLAYER,
        "join-reaction-npc",
        900,
        current["game_revision"],
        current["cast_revision"],
        "join",
        actor,
    )
    _, source = send(
        observer,
        scene,
        "reaction-question",
        text="May I ask about your notes?",
        fictional_channel="comms",
    )
    reactions = DirectorReactionService(context)
    opened = reactions.open(ADMIN, "reaction-open", scene, actor, source.source_id)
    proposed = reactions.propose(
        ADMIN,
        "reaction-propose",
        scene,
        opened["id"],
        ReactionProposal(
            request_id=opened["id"],
            kind="DIALOGUE",
            text=CANARY,
            rationale="The original controller must review their own private staged wording.",
        ),
    )
    assert CANARY in str(reactions.owner_review(PLAYER, scene, proposed["id"]))
    assert proposed["id"] in {item["id"] for item in reactions.pending(PLAYER, scene)}
    transfer = npc_roles.offer_transfer(
        PLAYER, "transfer-reaction-npc", state(game).revision, actor.entity, OTHER.user_id
    )
    npc_roles.respond(
        OTHER, "accept-reaction-transfer", transfer["id"], state(game).revision, "accept"
    )
    # Explicitly restore current casting for the replacement controller too;
    # protection must hold after a legitimate role handover, not just a stale cast.
    current = cast.view(PLAYER, 900)
    cast.change(
        PLAYER,
        "withdraw-previous-reaction-role",
        900,
        current["game_revision"],
        current["cast_revision"],
        "withdraw",
        actor,
    )
    current = cast.view(OTHER, 900)
    cast.change(
        OTHER,
        "join-replacement-reaction-role",
        900,
        current["game_revision"],
        current["cast_revision"],
        "join",
        actor,
    )
    for viewer in (PLAYER, OTHER):
        with pytest.raises(WorkflowError, match="REACTION_NOT_OWNED"):
            reactions.owner_review(viewer, scene, proposed["id"])
        assert proposed["id"] not in {item["id"] for item in reactions.pending(viewer, scene)}
        with pytest.raises(WorkflowError, match="REACTION_NOT_OWNED"):
            reactions.review(
                viewer,
                "cannot-inherit-reaction:" + str(viewer.user_id),
                scene,
                proposed["id"],
                "approve",
                "The original controller binding must remain frozen.",
            )
    assert CANARY not in str(InboxService(observer.store).page(OTHER))
    assert CANARY not in str(DirectorSessionService(context).work(OTHER, scene))
    assert CANARY in str(reactions.private(ADMIN, scene, proposed["id"]))
    assert dice.calls == 0
