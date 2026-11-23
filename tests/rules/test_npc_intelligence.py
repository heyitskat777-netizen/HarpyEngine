"""The Intelligence Agent learns a verified hidden affiliation within the actual role."""

import asyncio

import pytest
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_world_service import ready, transfer_npc

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_npc_intelligence import open_inquiry
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_npc_intelligence import RULE, IntelligenceService, inquiries
from girlframe.services.onboarding import WorkflowError


def test_intelligence_is_verified_and_shared_only_with_the_original_agent(ledger):
    world, game = ready(ledger)
    faction = Faction(
        id="secret-cell",
        name="Synthetic Private Affiliation",
        kind="rebel",
        cells=((0, 0),),
    )
    world.faction(ADMIN, "hidden-faction", state(game).revision, faction)
    agent = ActorRef(kind="npc", entity="independent-agent")
    subject = ActorRef(kind="npc", entity="concealed-affiliation-subject")
    for role, jobs, membership in (
        (agent, ("intelligence_agent",), ()),
        (subject, ("base_personnel",), (faction.id,)),
    ):
        world.npc(
            ADMIN,
            "introduce-" + role.entity,
            state(game).revision,
            Npc(
                id=role.entity,
                name=role.entity,
                jobs=jobs,
                detail="An actual co-present original role.",
                cell=(0, 0),
                controller=ADMIN.user_id,
                revealed=True,
                secret_factions=membership,
            ),
        )
    transfer_npc(world, ADMIN, PLAYER, agent.entity)
    cast = CastService(ActorService(world.missions))
    change(cast, PLAYER, "join", agent)
    change(cast, ADMIN, "join", subject)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    subsystems=policy.subsystems | {"plays"},
                    activity_specialist_rules=policy.activity_specialist_rules | {RULE},
                )
            )
        )
    )
    service = IntelligenceService(game)
    menu = service.menu(PLAYER, 900, agent)
    assert menu["targets"] == {subject.token: subject.entity} and faction.name not in str(menu)
    asyncio.run(
        submit_form(
            PLAYER,
            lambda click: open_inquiry(click, service, 900, agent),
            {
                "target": (subject.token,),
                "account": "I inspect their concealed dispatch signature.",
            },
            90540,
        )
    )
    before = state(game)
    (case,) = inquiries(before)
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(PLAYER, case.id)
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(OTHER, case.id)
    inbox = InboxService(ledger)
    notice = next(x for x in inbox.items(ADMIN) if x.task == "m3_npc_intelligence")

    async def gm_inquiry(click):
        await InboxView(inbox, ADMIN.user_id).route(click, notice)

    asyncio.run(
        submit_form(
            ADMIN,
            gm_inquiry,
            {
                "fact": (f"faction/{faction.id}",),
                "finding": "A matching source confirms membership.",
            },
            90544,
        )
    )
    ledger.engine.dispose()
    assert service.get(PLAYER, case.id)["learned"] == faction.name
    assert not any(x.identity == case.id for x in inbox.items(OTHER))
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(OTHER, case.id)
    final = state(game)
    assert final.world == before.world and inquiries(final)[0].agent == agent
