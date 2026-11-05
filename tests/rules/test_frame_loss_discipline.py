"""Final Frame removal cannot silently finish a Play that actually requires Defeat."""

import asyncio

import pytest
import sqlalchemy as sa
from test_beneath_discipline import pending
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_punishments import open_discipline
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import Placement
from girlframe.engine.m3_punishments import Details
from girlframe.services.inbox import InboxService
from girlframe.services.onboarding import WorkflowError


def final_removal(store, *, known_piloting=None):
    svc, game, worker, gateway, action, work = pending(store)
    with store.transaction() as c:
        canon = state(game)
        assets = [x for x in canon.sheets["3"].assets if x.family == "frame"]
        for asset in assets[1:]:
            asset.damaged = True
        if known_piloting is not None:
            character = canon.sheets["3"].character_id
            canon.placements.append(
                Placement(
                    actor=ActorRef(kind="pilot", entity="3", incarnation=character),
                    vessel_id="actual-body",
                    frame_instance="initial:" + character,
                    girl_cell=(0, 0),
                    frame_cell=(0, 0),
                    mode="piloting" if known_piloting else "outside_frame",
                    proposed_event="actual-owned-physical-proposal",
                    source_event="actual-physical-review",
                    account="Actual source physical placement",
                )
            )
        game.event(c, 1, "actual-prior-frame-damage", "synthetic.state", canon)
    details = Details(kind="frame_disassembly", asset=assets[0].id)
    data = svc.get(PLAYER, work)
    consult = svc.consult(
        PLAYER, "review-final-frame-removal", work, data["revision"], data["game_revision"], details
    )
    review = svc.get(ADMIN, consult["id"])
    svc.answer_consultation(
        ADMIN, "approve-final-frame-removal", consult["id"], review["revision"], True
    )
    data = svc.get(PLAYER, work)
    result = svc.apply(
        PLAYER,
        "remove-final-usable-frame-asset",
        work,
        data["revision"],
        data["game_revision"],
        details,
    )
    assert result["followups"] == 1
    assert game.inspect(PLAYER, action)["state"] == "awaiting_choices"
    table = t.m3["m3_required_work"]
    with store.engine.connect() as c:
        child = c.scalar(
            sa.select(table.c.id).where(
                table.c.campaign_id == store.campaign_id,
                table.c.kind == "punishment_frame_loss",
            )
        )
    return svc, game, action, child


@pytest.mark.parametrize("piloting,in_battle", [(False, False), (False, True), (True, False)])
def test_actual_non_defeat_context_finishes_the_owned_social_consequence(
    ledger, piloting, in_battle
):
    svc, game, action, identity = final_removal(ledger)
    data = svc.get(ADMIN, identity)
    result = svc.resolve_frame_loss(
        ADMIN,
        "actual-frame-loss-context",
        identity,
        data["revision"],
        data["game_revision"],
        piloting=piloting,
        in_battle=in_battle,
        evidence="The actual recorded loss context",
    )
    assert not result["defeat_required"]
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert (
        svc.resolve_frame_loss(
            ADMIN,
            "actual-frame-loss-context",
            identity,
            data["revision"],
            data["game_revision"],
            piloting=piloting,
            in_battle=in_battle,
            evidence="The actual recorded loss context",
        )
        == result
    )


def test_actual_battle_loss_keeps_defeat_pending_instead_of_falsely_releasing_chat(ledger):
    svc, game, action, identity = final_removal(ledger)
    data = svc.get(ADMIN, identity)
    with pytest.raises(WorkflowError):
        svc.resolve_frame_loss(
            OTHER,
            "not-the-handler",
            identity,
            data["revision"],
            data["game_revision"],
            piloting=True,
            in_battle=False,
            evidence="Cannot waive someone else's actual battle",
        )
    outcome = svc.resolve_frame_loss(
        ADMIN,
        "actual-battle-loss",
        identity,
        data["revision"],
        data["game_revision"],
        piloting=True,
        in_battle=True,
        evidence="Actual piloting and battle",
    )
    assert outcome["defeat_required"]
    assert game.inspect(PLAYER, action)["state"] == "awaiting_choices"
    table = t.m3["m3_required_work"]
    with ledger.engine.connect() as c:
        assert c.scalar(
            sa.select(table.c.id).where(
                table.c.campaign_id == ledger.campaign_id,
                table.c.kind == "defeat",
                table.c.state == "pending",
                table.c.owner_id == "3",
            )
        )
        assert game.lock(c, 900)["state"] == "held"


def test_native_frame_loss_review_is_handler_owned_and_appears_in_requests(ledger):
    svc, game, action, identity = final_removal(ledger)
    assert any(
        x.identity == identity and x.task == "m3_discipline"
        for x in InboxService(ledger).items(ADMIN)
    )

    async def run():
        handler = current(1, 19601)
        await handler.response.defer(ephemeral=True)
        await open_discipline(handler, svc, identity)
        form = handler.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2))
        form.values.update(
            piloting=("no",), in_battle=("no",), evidence="Actual out-of-battle disassembly"
        )
        await form.confirm.callback(current(1, 19602))
        assert form.completed

    asyncio.run(run())
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_known_source_placement_cannot_be_overridden_to_waive_defeat(ledger):
    svc, game, action, identity = final_removal(ledger, known_piloting=True)
    data = svc.get(ADMIN, identity)
    with pytest.raises(WorkflowError, match="source placement"):
        svc.resolve_frame_loss(
            ADMIN,
            "false-frame-context",
            identity,
            data["revision"],
            data["game_revision"],
            piloting=False,
            in_battle=True,
            evidence="Contradicts the source placement",
        )
    assert svc.get(ADMIN, identity)["state"] == "pending"
    assert game.inspect(PLAYER, action)["state"] == "awaiting_choices" and game.dice.calls == 1
