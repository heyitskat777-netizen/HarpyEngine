"""NPC possession offers affect the actual custodian through the owned native choice."""

import asyncio

import pytest
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_physical_operations import place
from test_world_service import ready

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_npc_handover import open_handover
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_items import ItemService, prove_transfer
from girlframe.services.m3_npc_handover import NpcHandoverService, records
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("job", ["fan", "patron", "smuggler"])
def test_actual_npc_possession_changes_hands_only_after_original_girl_chooses(ledger, job):
    world, game = ready(ledger)
    npc = ActorRef(kind="npc", entity="original-local-npc")
    world.npc(
        ADMIN,
        "local-npc-job",
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Local contact",
            jobs=(job,),
            detail="The NPC is actually in this square.",
            cell=(0, 0),
            controller=ADMIN.user_id,
        ),
    )
    with ledger.transaction() as c:
        canon = place(state(game), PLAYER.user_id, mode="outside_frame")
        game.event(c, ADMIN.user_id, "local-possession-scene", "synthetic.position", canon)
    cast = CastService(ActorService(world.missions))
    change(cast, ADMIN, "join", npc)
    girl = current_ref(state(game), PLAYER.user_id)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    subsystems=policy.subsystems | {"plays", "discipline"},
                    activity_specialist_rules=policy.activity_specialist_rules | {f"npc.npc.{job}"},
                )
            )
        )
    )
    donor, recipient = (girl, npc) if job == "fan" else (npc, girl)
    possession = ItemService(game)
    proposed = possession.propose(
        PLAYER if job == "fan" else ADMIN,
        "establish-custody",
        donor,
        "Actual folded photograph",
        "An existing ordinary object, carried by its original owner.",
    )
    item = possession.confirm(
        ADMIN,
        "prove-possession",
        proposed["id"],
        1,
        exists=True,
        account="I confirm who already held this specific object.",
    )["item"]
    original = state(game)
    service = NpcHandoverService(game)
    assert len(service.menu(ADMIN, 900, npc, job)["items"]) == (0 if job == "fan" else 1)
    values = dict(
        target=(girl.token,),
        account={
            "fan": "The NPC tries to take something personal.",
            "patron": "The NPC gives her the keepsake she asked for.",
            "smuggler": "The human GM establishes that these photographs are restricted.",
        }[job],
    )
    if job != "fan":
        values["item"] = (item,)
    asyncio.run(
        submit_form(
            ADMIN, lambda click: open_handover(click, service, 900, npc, job), values, 90500
        )
    )
    saved = state(game)
    offer = records(saved)[0]
    assert saved.held_items == original.held_items and not saved.item_transfers
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(OTHER, offer.id)
    inbox = InboxService(ledger)
    notice = next(x for x in inbox.items(PLAYER) if x.task == "m3_npc_handover")
    assert notice.identity == offer.id

    async def private_choice(click):
        await InboxView(inbox, PLAYER.user_id).route(click, notice)

    asyncio.run(submit_form(PLAYER, private_choice, {"choice": (f"item/{item}",)}, 90504))
    final = state(game)
    assert final.held_items[0].holder == recipient
    assert final.sheets == original.sheets
    transfer = records(final)[0].transferred
    with ledger.engine.connect() as c:
        _, _, proof = prove_transfer(c, game, transfer)
    assert (proof.source, proof.recipient, proof.item) == (donor, recipient, item)
    assert proof.source_kind == "npc_job_handover"
    assert service.respond(PLAYER, "90506", offer.id, saved.revision, item)["transfer"] == transfer
