"""Actual native body captivity and canonical Execution yield one source-bound Reign effect."""

import asyncio
from uuid import uuid4

import pytest
from test_enforcement_initiative import ready
from test_enforcer_requisitions import approved
from test_handler_creation import agree, complete, save
from test_handler_ordinary import session_native
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_mission_ui import current
from test_reign_terror import native
from test_strain_service import D6

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_punishments import open_details
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary_rules
from girlframe.engine import m3_reign_terror as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_enforcer import INITIATIVE
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService
from girlframe.services.m3_handler_pr import HandlerPRService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_reign_terror import ReignTerrorService, prove_pc_execution
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError


def test_actual_native_prisoner_execution_then_one_owned_reign_effect_and_history(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger, game, tmp_path, monkeypatch, extra=(ordinary_rules.RULE, rules.RULE, INITIATIVE)
    )
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=ledger.policy.m3_approval.model_copy(
                update=dict(
                    subsystems=ledger.policy.m3_approval.subsystems
                    | {"world", "strain", "playbooks"}
                )
            ),
            owner_m3_rulings=ledger.policy.owner_m3_rulings.model_copy(
                update=dict(handler_creation="owned_shared_choices_preserve_existing")
            ),
        )
    )
    creation = HandlerCreationService(ledger)
    save(creation, complete(creation, "Scientist"))
    agree(creation)
    data = creation.view(ADMIN)
    creation.activate(ADMIN, str(uuid4()), data["revision"], data["game_revision"], True)
    ordinary = HandlerOrdinaryService(ledger)
    session_native(ordinary, "Actual captivity and Execution Session", 45000)
    pr = HandlerPRService(ledger)
    event = pr.plan(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "Actual Foundation fundraiser",
        "Real presentation and original Girl's public interview",
        (current_ref(state(game), 2),),
    )["id"]
    pr.activity(
        ADMIN,
        str(uuid4()),
        event,
        state(game).revision,
        "I actually host the public presentation",
        hosting=True,
    )
    pr.activity(
        PLAYER,
        str(uuid4()),
        event,
        state(game).revision,
        "My original Girl actually performs the public interview",
    )
    pr.submit_result(
        ADMIN, str(uuid4()), event, state(game).revision, "Actual media event is complete"
    )
    pr.resolve(
        ADMIN,
        str(uuid4()),
        event,
        state(game).revision,
        True,
        "The actual hosted Foundation event succeeded",
    )
    reign = ReignTerrorService(ledger, game)
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")
    native(
        reign, award=(award.id,), account="Actual held advancement buys Reign before any Execution"
    )
    receipt = rules.acquisitions(state(game))[0]
    physical = PhysicalService(ledger)
    cell = next(x.cell for x in state(game).world.locations if x.kind == "base")
    for viewer in (PLAYER, OTHER):
        data = physical.preview(viewer)
        proposed = physical.propose(
            viewer,
            str(uuid4()),
            data["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(data["actor"]),
                frame_instance=data["frame_instance"],
                girl_cell=cell,
                frame_cell=cell,
                mode="outside_frame",
                account="Actual original body and Frame at this Foundation Base",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN,
            str(uuid4()),
            proposed["id"],
            1,
            "accept",
            "Actual known original bodies outside their Frames",
        )
    missions = MissionService(ledger)
    strain = StrainService(OffDutyService(missions), dice=D6(1))
    strain.configure(
        ADMIN, str(uuid4()), state(game).revision, "disaster_management", frozenset({"rebellion"})
    )
    offered = missions.offer(
        ADMIN, str(uuid4()), "Actual inspection mission before discipline", (2, 3)
    )
    missions.respond(PLAYER, str(uuid4()), offered["id"], 1, "accept")
    missions.respond(OTHER, str(uuid4()), offered["id"], 2, "accept")
    missions.start(ADMIN, str(uuid4()), offered["id"], 3)
    ended = missions.end(ADMIN, str(uuid4()), offered["id"], 4, False)
    punishment = PunishmentService(ledger)
    work = next(x["id"] for x in missions.get(ADMIN, ended["id"])["work"] if x["subject"] == 3)
    subject = current_ref(state(game), 3)
    capture = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="enforcement_initiative",
            heat=0,
            target_actor=subject,
            context="My original Enforcer takes actual bodily hold of this original Girl",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, capture)["state"] == "complete"
    grip = next(x for x in state(game).enforcer_grasps if x.target == subject)
    assert grip.held and grip.contact == "body" and is_helpless(state(game), subject, grip.actor)
    with pytest.raises(WorkflowError, match="completed execution"):
        reign.claim_pc_execution(
            ADMIN,
            str(uuid4()),
            grip.source_event,
            state(game).revision,
            "rebellion_low",
            "Unfinished death cannot grant anything",
        )
    assert not rules.pc_claims(state(game)) and state(game).strain.levels["rebellion"] == "high"

    presence_id = "reign-pc-presence:" + work
    with pytest.raises(WorkflowError, match="Only the original Handler"):
        reign.prepare_pc_execution_presence(
            OTHER, str(uuid4()), work, state(game).revision, "Cannot report another person's body"
        )
    native(
        reign,
        identity=presence_id,
        account="My original Handler is at this Foundation Base beside the original held captive",
    )
    with pytest.raises(WorkflowError, match="unknown initial position"):
        reign.prepare_pc_execution_presence(
            ADMIN, str(uuid4()), work, state(game).revision, "Cannot reset an existing position"
        )

    async def execute():
        own = current(1, 45010)
        await own.response.defer(ephemeral=True)
        await open_details(own, punishment, work, "execution")
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values["confirm"] = ("yes",)
        await form.confirm.callback(current(1, 45011))
        assert form.completed

    asyncio.run(execute())
    actual = state(game)
    archive = next(x for x in actual.career_archives if x.actor == subject)
    assert archive.ending == "execution" and "3" not in actual.sheets
    released = next(x for x in actual.enforcer_grasps if x.id == grip.id)
    assert not released.held and released.release_event == archive.source_event
    with ledger.engine.connect() as c:
        proof = prove_pc_execution(game, c, actual, archive.source_event)
    assert proof.acquisition == receipt.id and proof.grasp == grip.id and len(proof.works) == 2
    with pytest.raises(WorkflowError, match="exactly one"):
        reign.claim_pc_execution(
            OTHER,
            str(uuid4()),
            archive.source_event,
            actual.revision,
            "rebellion_low",
            "The subject cannot answer as the Handler",
        )
    args = {}

    async def claim():
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(ADMIN)
            if x.task == "m3_reign_terror"
            and x.identity == "reign-pc-source:" + archive.source_event
        )
        assert item.incoming
        own = current(1, 45020)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        account = "I choose actual Rebellion Low from this completed original captive's Execution"
        form.values.update(choice=("rebellion_low",), account=account)
        args.update(revision=actual.revision, account=account)
        await form.confirm.callback(current(1, 45021))
        assert form.completed

    asyncio.run(claim())
    claim_value = rules.pc_claims(state(game))[0]
    assert claim_value.execution_event == archive.source_event and claim_value.archive == archive.id
    assert strain.get(ADMIN)["strain"]["levels"]["rebellion"] == "low"
    before = state(game).model_dump_json()
    reign.claim_pc_execution(
        ADMIN, "45021", archive.source_event, args["revision"], "rebellion_low", args["account"]
    )
    assert state(game).model_dump_json() == before
    with pytest.raises(WorkflowError, match="exactly one"):
        reign.claim_pc_execution(
            ADMIN,
            str(uuid4()),
            archive.source_event,
            state(game).revision,
            "girl_tag",
            "Cannot claim another bundled cause",
            target=current_ref(state(game), 2),
            label="No duplicate effect",
        )
    assert len(rules.pc_claims(state(game))) == 1 and len(state(game).career_archives) == 1
    assert len(claim_value.works) == 2 and game.dice.calls == 1

    async def history():
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(OTHER)
            if x.task == "m3_reign_terror" and x.identity == claim_value.id
        )
        assert not item.incoming
        own = current(3, 45030)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 3).route(own, item)
        assert "Original execution archive" in str(own.edit_original_response.call_args)

    asyncio.run(history())
