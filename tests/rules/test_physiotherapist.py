"""One actual paid NPC Bond and native Off-Duty scene, Tag and nondestructive removal."""

import asyncio
import copy
from uuid import uuid4

import test_strain_effect_service
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, prepared
from test_strain_service import ready as strain_ready

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_physiotherapist import open_purchase, open_request
from girlframe.engine import m3_physiotherapist as rules
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_physiotherapist import PhysiotherapistService
from girlframe.services.m3_world import WorldService


def test_native_paid_physiotherapist_bond_actual_scene_tag_and_void_removal(
    ledger, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        test_strain_effect_service,
        "ready",
        lambda store, face: strain_ready(store, face=face, frame="CONSUME"),
    )
    cycle, game, period = prepared(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    cycle.missions.access = Access(ledger)
    world = WorldService(cycle.missions)
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="real-physiotherapist",
            name="Actual Void physiotherapist",
            jobs=("doctor",),
            detail="Knowledgeable about Void leakage",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    world.claim_npc(ADMIN, str(uuid4()), state(game).revision, "real-physiotherapist")
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 2
        target = next(x for x in actual.sheets["2"].assets if x.family == "girl")
        target.void = True
        target.damaged = True
        original = copy.deepcopy(target)
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_therapy_resources", actual)
    service = PhysiotherapistService(game)

    async def purchase_and_owned_acceptance():
        own = current(2, 999701)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_purchase(own, service)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            npc=("real-physiotherapist",),
            account="My actual relationship with this knowledgeable physiotherapist",
        )
        confirmation = current(2, 999702)
        await form.confirm.callback(confirmation)
        assert form.completed
        identity = service.menu(PLAYER)["requests"][0]
        actual = state(game)
        assert (
            depth(
                actual, current_ref(actual, 2), ActorRef(kind="npc", entity="real-physiotherapist")
            )
            == 0
        )
        npc = current(1, 999703)
        await npc.response.defer(ephemeral=True)
        await open_request(npc, service, identity)
        form = npc.edit_original_response.call_args.kwargs["view"]
        assert "My actual relationship" in form.text()
        form.values.update(
            account="As the actual NPC controller I accept this Personal Bond and expertise"
        )
        await form.confirm.callback(current(1, 999704))
        assert form.completed
        return identity

    identity = asyncio.run(purchase_and_owned_acceptance())
    actual = state(game)
    assert actual.sheets["2"].permissions == 0
    assert (
        depth(actual, current_ref(actual, 2), ActorRef(kind="npc", entity="real-physiotherapist"))
        == 1
    )
    activate(cycle, game, period)
    casts = CastService(ActorService(cycle.missions))
    data = casts.view(ADMIN, 900)
    casts.change(
        ADMIN,
        str(uuid4()),
        900,
        data["game_revision"],
        data["cast_revision"],
        "join",
        ActorRef(kind="npc", entity="real-physiotherapist"),
    )

    async def actual_scene_and_treatment():
        own = current(2, 999705)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_request(own, service, identity)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            location=("base0",),
            asset=(original.id,),
            account="We actually meet at the Base for an Off-Duty physiotherapy scene",
        )
        await form.confirm.callback(current(2, 999706))
        assert form.completed
        assert next(x for x in state(game).sheets["2"].assets if x.id == original.id).void
        with ledger.engine.connect() as c:
            scene_id = service._tasks(c, ADMIN)[0]["id"]
        npc = current(1, 999707)
        npc.channel_id = 901
        await npc.response.defer(ephemeral=True)
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(ADMIN)
            if x.task == "m3_physiotherapist" and x.identity == scene_id
        )
        await InboxView(inbox, 1).route(npc, item)
        form = npc.edit_original_response.call_args.kwargs["view"]
        assert original.name in form.text()
        form.values.update(
            tag="Steadier after therapy",
            account="My NPC actually attended and removed the requested Void "
            "without destroying the Asset",
        )
        await form.confirm.callback(current(1, 999708))
        assert form.completed
        assert npc.channel_id == 901
        return scene_id

    identity = asyncio.run(actual_scene_and_treatment())
    final = state(game)
    asset = next(x for x in final.sheets["2"].assets if x.id == original.id)
    assert asset == original.model_copy(update={"void": False})
    tag = next(x for x in final.sheets["2"].tags if x.label == "Steadier after therapy")
    assert tag.giver == 1 and tag.giver_actor == ActorRef(kind="npc", entity="real-physiotherapist")
    data = service.get(PLAYER, identity)
    assert data["therapy"]["phase"] == "closed"
    assert data["therapy"]["scene"]["acknowledgements"] == [1, 2]
    assert data["therapy"]["period"] == period
    with ledger.engine.connect() as c:
        row, _ = service._source(c, final, identity)
        assert row["state"] == "resolved" and row["off_duty_id"] == period
        assert not service._tasks(c, ADMIN)
