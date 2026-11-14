"""Native Quickchange retains the actual other character and Tag source type."""

import asyncio
from uuid import uuid4

import pytest
import test_strain_effect_service
from test_ankou import buy, current
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_off_duty_cycle import activate, prepared
from test_physical_operations import place
from test_strain_service import ready as strain_ready

from girlframe.discord_adapter.m3_ankou import open_ankou
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_access import Access
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_native_quickchange_uses_actual_owned_npc_tag_and_original_character(
    ledger, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        test_strain_effect_service,
        "ready",
        lambda store, face: strain_ready(store, face=face, frame=rules.FRAME),
    )
    cycle, game, period = prepared(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RELAY, *rules.REQUISITIONS))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    with ledger.transaction() as c:
        canon = place(state(game), 2, mode="outside_frame")
        canon.sheets["2"].permissions = 10
        game.event(c, 1, str(uuid4()), "synthetic.prior_quickchange_resources", canon)
    cycle.missions.access = Access(ledger)
    controls = AnkouService(game)
    buy(controls, rules.QUICKCHANGE)
    roles = NpcRoleService(WorldService(MissionService(ledger)))
    handler = HandlerPlayService(ledger)

    def give_tag(target, label):
        grant = handler.start(ADMIN, str(uuid4()), state(game).revision, (target,))["id"]
        handler.submit(
            ADMIN,
            str(uuid4()),
            grant,
            state(game).revision,
            "mess",
            Effect(
                kind="tag",
                account="Actual observed conduct gives this person a Tag",
                target=target,
                tag=label,
            ),
        )
        return grant + ":tag"

    peers = []
    tags = []
    for index, label in enumerate(("Actual first NPC Tag", "Actual second NPC Tag")):
        ref = ActorRef(kind="npc", entity=f"quickchange-peer-{index}")
        offered = roles.offer(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            Npc(
                id=ref.entity,
                name=f"Distinct actual peer {index}",
                jobs=("guard",),
                detail="A separately accepted living person",
                controller=2,
                cell=(0, 0),
                revealed=True,
            ),
        )
        roles.respond(PLAYER, str(uuid4()), offered["id"], state(game).revision, "accept")
        peers.append(ref)
        tags.append(give_tag(ref, label))
    private = roles.offer(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="undisclosed-peer",
            name="PRIVATE_UNKNOWN_PEER",
            jobs=("guard",),
            detail="An unobserved independent person",
            controller=3,
            cell=(5, 5),
        ),
    )
    roles.respond(OTHER, str(uuid4()), private["id"], state(game).revision, "accept")
    give_tag(ActorRef(kind="npc", entity="undisclosed-peer"), "PRIVATE_UNKNOWN_TAG")
    activate(cycle, game, period)
    menu = controls.menu(PLAYER, 900)
    options = [x for x in menu["disclosed"] if x["id"] in tags]
    assert len(options) == 2 and all(x["kind"] == "tag" for x in options)
    assert len({x["token"] for x in options}) == 2
    assert "PRIVATE_UNKNOWN" not in str(menu)
    chosen = next(x for x in options if x["person"] == peers[1].model_dump(mode="json"))
    before = state(game)
    erase = next(x.id for x in before.sheets["2"].identities if not x.protected and not x.paired)
    with pytest.raises(WorkflowError, match="genuine source-person disclosure"):
        controls.quickchange(
            PLAYER,
            str(uuid4()),
            before.revision,
            period,
            erase=erase,
            source_person=peers[1],
            source_identity=tags[1],
            account="Reject the incorrect resource type",
        )
    assert state(game) == before

    async def native():
        interaction = current()
        await interaction.response.defer(ephemeral=True)
        await open_ankou(interaction, controls)
        listing = interaction.edit_original_response.call_args.kwargs["view"]
        listing.values["operation"] = ("quickchange",)
        request = current()
        await listing.confirm.callback(request)
        form = request.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(
            period=(period,),
            erase=(erase,),
            resource=(chosen["token"],),
            account="I use this actual other character's Tag to rewrite myself",
        )
        submit = current()
        await form.confirm.callback(submit)
        assert form.completed, submit.edit_original_response.call_args_list

    asyncio.run(native())
    after = state(game)
    saved = rules.records(after, rules.Quickchange)
    assert len(saved) == 1
    value = saved[0]
    assert value.source_person == peers[1] and value.source_tag == tags[1]
    assert value.source_identity is None and value.label == "Actual second NPC Tag"
    assert value.erased == erase and value.period == period
    assert (
        next(x for x in after.sheets["2"].identities if x.id == value.written).name == value.label
    )
    assert after.world == before.world
    assert after.sheets["2"].heat == before.sheets["2"].heat
    assert after.sheets["2"].permissions == before.sheets["2"].permissions
    with pytest.raises(WorkflowError, match="already used"):
        controls.quickchange(
            PLAYER,
            str(uuid4()),
            after.revision,
            period,
            source_person=peers[0],
            source_tag=tags[0],
            account="No second use in the same period",
        )
    assert state(game) == after
