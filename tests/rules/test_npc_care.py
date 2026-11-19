"""Focused synthetic testing of the printed local NPC care moves."""

import asyncio

import pytest
from test_battle_service import prepared
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_npc_care import open_care
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Npc
from girlframe.engine.rules_registry import Registry
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_care import NpcCareService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("job,family", (("doctor", "girl"), ("mechanic", "frame")))
def test_local_npc_care_repairs_only_the_owned_accepted_asset(ledger, monkeypatch, job, family):
    actual_gate = Registry.require_available

    def synthetic_gate(registry, identity):
        if identity == "npc.npc." + job:
            return next(x for x in registry.entries if x.id == identity)
        return actual_gate(registry, identity)

    monkeypatch.setattr(Registry, "require_available", synthetic_gate)
    game, _, _, _, _, _ = prepared(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"world"}))
        )
    )
    staff = ActorRef(kind="npc", entity="ward-care")
    patient = current_ref(state(game), PLAYER.user_id)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            npcs=(
                Npc(
                    id=staff.entity,
                    name="Ward care",
                    jobs=(job,),
                    detail="Actual ward staff",
                    cell=(0, 0),
                    controller=ADMIN.user_id,
                    revealed=True,
                ),
            ),
        )
        row = next(x for x in canon.sheets["2"].assets if x.family == family)
        row.damaged, row.void = True, True
        game.event(c, ADMIN.user_id, "synthetic-npc-care-setup", "synthetic.damage", canon)
    cast = CastService(ActorService(MissionService(ledger)))
    change(cast, ADMIN, "join", staff)
    with ledger.engine.connect() as c:
        current_actor = resolve(state(game), patient, profiles(c, ledger.campaign_id))
    PhysicalService(ledger).operate(
        PLAYER,
        "npc-care-cockpit-exit",
        state(game).revision,
        CockpitAction(
            actor=patient,
            operation="exit",
            expected_position=current_actor.position_sha256,
            account="I leave the Frame beside the ward.",
            confirmed=True,
        ),
        channel=900,
    )
    service = NpcCareService(ledger)
    inbox = InboxService(ledger)

    def cards(viewer):
        return [x for x in inbox.items(viewer) if x.task == "m3_npc_care"]

    (offer_card,) = cards(ADMIN)
    assert cards(PLAYER) == cards(OTHER) == []
    data = service.get(ADMIN, offer_card.identity)
    assert "assets" not in data

    async def use_form(viewer, identity, interaction_id, values):
        interaction = current(viewer.user_id, interaction_id)
        await interaction.response.defer(ephemeral=True)
        await open_care(interaction, service, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        await form.confirm.callback(current(viewer.user_id, interaction_id + 1))
        assert form.completed

    asyncio.run(
        use_form(
            ADMIN,
            offer_card.identity,
            88600,
            dict(
                target=(patient.token,),
                account="I offer to repair this actual damage.",
            ),
        )
    )
    (recipient,) = cards(PLAYER)
    assert not cards(OTHER)
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(OTHER, recipient.identity)
    assert next(x for x in state(game).sheets["2"].assets if x.id == row.id).damaged
    ledger.engine.dispose()
    asyncio.run(use_form(PLAYER, recipient.identity, 88610, dict(care=(f"asset/{row.id}",))))
    fixed = next(x for x in state(game).sheets["2"].assets if x.id == row.id)
    assert not fixed.damaged and fixed.void and not cards(PLAYER)


def test_scientist_void_experiment_applies_the_original_asset_and_privately_holds_threshold(ledger):
    from test_harpy_flirt import submit_form
    from test_physical_operations import place
    from test_world_service import ready

    from girlframe.discord_adapter.inbox import InboxView
    from girlframe.services.m3_npc_care import _records
    from girlframe.services.m3_void import VoidService

    world, game = ready(ledger)
    scientist = ActorRef(kind="npc", entity="experiment-scientist")
    world.npc(
        ADMIN,
        "scientist-introduction",
        state(game).revision,
        Npc(
            id=scientist.entity,
            name="The local scientist",
            jobs=("scientist",),
            detail="The human GM's original local scientist.",
            cell=(0, 0),
            controller=ADMIN.user_id,
            revealed=True,
        ),
    )
    with ledger.transaction() as c:
        canon = place(state(game), PLAYER.user_id, mode="outside_frame")
        sheet = canon.sheets["2"]
        sheet.girl = "PRINCESS"
        sheet.girl_runtime = None
        assets = [x for x in sheet.assets if x.family == "girl"]
        for existing in assets[:-1]:
            existing.void = True
        asset = assets[-1].id
        game.event(c, ADMIN.user_id, "synthetic-original-void", "synthetic.position", canon)
    cast = CastService(ActorService(world.missions))
    change(cast, ADMIN, "join", scientist)
    patient = current_ref(state(game), PLAYER.user_id)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(
                    subsystems=approval.subsystems | {"plays"},
                    activity_specialist_rules=approval.activity_specialist_rules
                    | {"npc.npc.scientist"},
                )
            )
        )
    )
    inbox = InboxService(ledger)
    card = next(x for x in inbox.items(ADMIN) if x.task == "m3_npc_care")
    service = NpcCareService(ledger)
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_care(click, service, card.identity),
            {"target": (patient.token,), "account": "The scientist offers a specific experiment."},
            90600,
        )
    )
    before = state(game)
    assert next(x for x in before.sheets["2"].assets if x.id == asset).void is False
    notice = next(x for x in inbox.items(PLAYER) if x.task == "m3_npc_care")
    assert not any(x.identity == notice.identity for x in inbox.items(OTHER))

    async def original_patient(click):
        await InboxView(inbox, PLAYER.user_id).route(click, notice)

    asyncio.run(
        submit_form(
            PLAYER,
            original_patient,
            dict(care=(f"asset/{asset}",), alteration="My skin reflects the instruments."),
            90604,
        )
    )
    final = state(game)
    (case,) = _records(final)
    assert case.void_asset == asset and case.void_work
    assert next(x for x in final.sheets["2"].assets if x.id == asset).void
    ledger.engine.dispose()
    assert VoidService(ledger).get(PLAYER, case.void_work)["stage"] == "allured"
    with pytest.raises(WorkflowError):
        VoidService(ledger).get(OTHER, case.void_work)
