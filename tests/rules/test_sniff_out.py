"""Focused private discovery test of the printed Dopplegänger mid roll."""

import asyncio

import pytest
from test_battle_service import prepared
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state
from test_mission_ui import current
from test_world import gorgon

from girlframe.discord_adapter.m3_sniff_out import open_search
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_sniff_out import RULE, records
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Npc
from girlframe.engine.rules_registry import Registry
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_sniff_out import SniffOutService
from girlframe.services.onboarding import WorkflowError


def test_sniff_out_reveals_only_the_original_guise_after_owned_bait(ledger, monkeypatch):
    actual_gate = Registry.require_available

    def synthetic_gate(registry, identity):
        if identity == RULE:
            return next(x for x in registry.entries if x.id == identity)
        return actual_gate(registry, identity)

    monkeypatch.setattr(Registry, "require_available", synthetic_gate)
    game, _, _, _, _, _ = prepared(ledger)
    game.dice = Dice((3, 4))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"world"}))
        )
    )
    guise = ActorRef(kind="npc", entity="a-normal-broker")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            npcs=(
                Npc(
                    id=guise.entity,
                    name="The Broker",
                    controller=ADMIN.user_id,
                    cell=(0, 0),
                    jobs=("civilian",),
                    detail="A familiar face",
                    revealed=True,
                ),
            ),
            gorgons=(
                gorgon("erratic", "sealed-original", revealed=False, types=("doppleganger",)),
            ),
        )
        canon.sheets["2"].heat = 2
        game.event(c, ADMIN.user_id, "synthetic-concealed-body", "synthetic.world", canon)
    change(CastService(ActorService(MissionService(ledger))), ADMIN, "join", guise)
    search = SniffOutService(ledger, game)
    inbox = InboxService(ledger)

    def cards(viewer):
        return [x for x in inbox.items(viewer) if x.task == "m3_sniff_out"]

    assert cards(PLAYER) == cards(OTHER) == []
    start = next(
        x
        for x in cards(ADMIN)
        if search.get(ADMIN, x.identity)["hunter"] == state(game).sheets["2"].callsign
    )
    targets = search.get(ADMIN, start.identity)["targets"]
    answer = search.respond(
        ADMIN,
        "offer-original-search",
        start.identity,
        start.revision,
        "offer",
        selected=next(iter(targets)),
        account="An impossible shadow answered a familiar voice.",
    )
    (item,) = cards(PLAYER)
    identity = item.identity
    assert answer["id"] == identity
    initial = search.get(PLAYER, identity)
    assert not {"found", "targets", "name", "gorgon", "guise"} & initial.keys()
    with pytest.raises(WorkflowError, match="unavailable"):
        search.get(OTHER, identity)
    receipt = search.respond(
        PLAYER, "roll-sealed-search", identity, initial["revision"], "roll", heat=1
    )
    assert (
        search.respond(PLAYER, "roll-sealed-search", identity, initial["revision"], "roll", heat=1)
        == receipt
    )
    assert game.dice.calls == 1 and state(game).sheets["2"].heat == 1
    ledger.engine.dispose()

    async def bait():
        interaction = current(PLAYER.user_id, 89010)
        await interaction.response.defer(ephemeral=True)
        await open_search(interaction, search, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values["account"] = "I volunteer to wait where the voice first answered."
        await form.confirm.callback(current(PLAYER.user_id, 89011))
        assert form.completed

    asyncio.run(bait())
    assert "found" not in search.get(PLAYER, identity)
    hidden = records(state(game))[0]
    search.respond(
        ADMIN,
        "verify-original-drawn-out",
        identity,
        state(game).revision,
        "discover",
        account="The investigator confronts the guise and witnesses the concealed body answering.",
    )
    assert search.get(PLAYER, identity)["found"] == "The Broker"
    assert records(state(game))[0].gorgon == hidden.gorgon
    assert not state(game).world.gorgons[0].revealed
    assert not cards(OTHER)
