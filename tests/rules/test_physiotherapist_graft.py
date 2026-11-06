"""Actual paid graft, owned NPC Bond, real Off-Duty therapy and exact restoration."""

import asyncio
import copy
from uuid import uuid4

import pytest
import test_strain_effect_service
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate, prepared
from test_privileges import change
from test_strain_service import ready as strain_ready

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_physiotherapist import open_purchase, open_request
from girlframe.engine import m3_physiotherapist as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_physiotherapist import PhysiotherapistService
from girlframe.services.m3_privileges import PrivilegeService, purchase_proof
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_grafted_physiotherapist_owned_bond_scene_suspension_and_exact_treatment(
    ledger, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        test_strain_effect_service,
        "ready",
        lambda store, face: strain_ready(store, face=face, frame="WYVERN 0.4"),
    )
    cycle, game, period = prepared(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={
                    "beneath_private_choices": "affected_owner",
                    "privilege_restoration": "inflictor_condition_owner_restores",
                }
            )
        }
    )
    cycle.missions.access = Access(ledger)
    world = WorldService(cycle.missions)
    npc = ActorRef(kind="npc", entity="real-physiotherapist")
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Actual physiotherapist",
            jobs=("doctor",),
            detail="Knowledgeable about Void leakage",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    world.claim_npc(ADMIN, str(uuid4()), state(game).revision, npc.entity)
    with ledger.transaction() as c:
        actual = state(game)
        actual.order = (3, 2)
        actual.sheets["2"].permissions = 6
        target = next(x for x in actual.sheets["2"].assets if x.family == "girl")
        target.void = True
        target.damaged = True
        original = copy.deepcopy(target)
        game.event(c, 1, str(uuid4()), "synthetic.prior_therapy_resources", actual)
    service = PhysiotherapistService(game)
    preview = service.menu(PLAYER)
    assert preview["kind"] == "frame_grafting" and preview["price"] == 3
    before = state(game)
    for donor in (None, "WYVERN 0.4"):
        with pytest.raises(WorkflowError, match="Priestess donor"):
            service.buy(
                PLAYER,
                str(uuid4()),
                preview["revision"],
                npc.entity,
                "Actual donor relationship",
                donor,
            )
        assert state(game) == before

    async def actual_acquisition_and_bond():
        own = current(2, 992101)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, service)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "Frame Grafting" in form.text() and "3 Permissions" in form.text()
        form.values.update(
            donor=("CHANGELING",), npc=(npc.entity,), account="Actual donor relationship"
        )
        await form.confirm.callback(current(2, 992102))
        assert form.completed
        actual = state(game)
        actor = current_ref(actual, 2)
        assert depth(actual, actor, npc) == 0
        paid = rules.held(actual, actor)
        assert paid and paid.kind == "frame_grafting" and paid.donor_frame == "CHANGELING"
        assert actual.sheets["2"].permissions == 3
        assert service.buy(
            PLAYER,
            "992102",
            preview["revision"],
            npc.entity,
            "Actual donor relationship",
            "CHANGELING",
        ) == {"id": paid.id, "cost": 3}
        assert len(state(game).requisitions) == 1
        controlled = current(1, 992103)
        await controlled.response.defer(ephemeral=True)
        await open_request(controlled, service, paid.id)
        form = controlled.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="I accept my actual NPC's relationship and expertise")
        await form.confirm.callback(current(1, 992104))
        assert form.completed
        return paid

    paid = asyncio.run(actual_acquisition_and_bond())
    actor = paid.actor
    actual = state(game)
    assert depth(actual, actor, npc) == 1
    with ledger.engine.connect() as c:
        purchase_proof(c, ledger, paid)
    activate(cycle, game, period)
    # A real superior suspends the purchased treatment source; its existing Bond remains.
    worker, gateway = GameWorker(game), Gateway()
    game.dice.faces = (6, 6)
    social = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=2,
            heat=0,
            context="Actual confrontation",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("tag", "punish"),
        fields={"tag": "Actual discipline"},
        text="Actual discipline",
    )
    work = game.decision(OTHER, game.choices(OTHER)[0]["id"])["body"]["work_id"]
    discipline = PunishmentService(ledger)
    data = discipline.get(OTHER, work)
    assert {"id": paid.id, "name": "Void Physiotherapist"} in data["choices"]["requisitions"]
    discipline.apply(
        OTHER,
        "actual-therapy-revocation",
        work,
        data["revision"],
        data["game_revision"],
        Details(
            kind="revoked_privileges",
            requisition=paid.id,
            restoration="Resolve the actual condition",
        ),
    )
    assert game.inspect(OTHER, social)["state"] == "complete"
    tick(worker, gateway, 5)
    suspended = state(game)
    assert rules.held(suspended, actor) is None and depth(suspended, actor, npc) == 1
    data = service.get(PLAYER, paid.id)
    with pytest.raises(WorkflowError, match="Restore.*original paid"):
        service.respond(
            PLAYER,
            "blocked-therapy-scene",
            paid.id,
            data["revision"],
            data["game_revision"],
            operation="scene",
            account="Our actual Off-Duty therapy",
            channel=900,
            location="base0",
            asset=original.id,
        )
    preview = service.menu(PLAYER)
    assert preview["suspended"]
    with pytest.raises(WorkflowError, match="rather than buy twice"):
        service.buy(
            PLAYER,
            str(uuid4()),
            preview["revision"],
            npc.entity,
            "Cannot buy the suspended relationship twice",
            "CHANGELING",
        )
    assert state(game) == suspended
    with ledger.engine.connect() as c:
        row, value = service._source(c, suspended, paid.id)
        assert row["state"] == "resolved" and value.phase == "ready"
    gate = next(x for x in suspended.obligations if x.kind == "revoked_requisition")
    restoration = PrivilegeService(ledger)
    change(restoration, OTHER, gate.id, allow=True)
    change(restoration, PLAYER, gate.id, allow=False)
    restored = state(game)
    assert rules.held(restored, actor) == paid and depth(restored, actor, npc) == 1
    assert restored.requisitions == suspended.requisitions
    casts = CastService(ActorService(cycle.missions))
    cast = casts.view(ADMIN, 900)
    casts.change(
        ADMIN, str(uuid4()), 900, cast["game_revision"], cast["cast_revision"], "join", npc
    )
    data = service.get(PLAYER, paid.id)
    scene = service.respond(
        PLAYER,
        "actual-therapy-scene",
        paid.id,
        data["revision"],
        data["game_revision"],
        operation="scene",
        account="Our actual Off-Duty therapy",
        channel=900,
        location="base0",
        asset=original.id,
    )
    scene_id = scene["id"]
    assert next(x for x in state(game).sheets["2"].assets if x.id == original.id) == original

    treatment = dict(
        operation="treat",
        account="Actual NPC attendance and completed treatment",
        tag="Steadier after therapy",
    )
    data = service.get(ADMIN, scene_id)
    args = (ADMIN, "actual-therapy-treatment", scene_id, data["revision"], data["game_revision"])
    result = service.respond(*args, **treatment)
    assert service.respond(*args, **treatment) == result
    final = state(game)
    actual = next(x for x in final.sheets["2"].assets if x.id == original.id)
    assert actual == original.model_copy(update={"void": False})
    tags = [x for x in final.sheets["2"].tags if x.label == treatment["tag"]]
    assert len(tags) == 1 and tags[0].giver_actor == npc and tags[0].giver == 1
    assert final.sheets["2"].permissions == 3 and final.requisitions == restored.requisitions
    assert depth(final, actor, npc) == 1
    assert service.get(PLAYER, scene_id)["therapy"]["scene"]["acknowledgements"] == [1, 2]
    with ledger.engine.connect() as c:
        row, value = service._source(c, final, scene_id)
        assert (
            row["state"] == "resolved" and row["off_duty_id"] == period and value.phase == "closed"
        )
        assert not service._tasks(c, ADMIN)
