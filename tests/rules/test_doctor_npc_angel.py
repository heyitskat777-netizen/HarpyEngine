"""Printed p71 Metal Angel: an actual NPC survives Attack and receives next-period care."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_doctor_npc_care import npc_patient
from test_doctor_runtime import acquire
from test_gorgon_runtime import candidate_source_gate as candidate_source_gate
from test_gorgon_service import selection
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain import facts
from test_strain_service import D6
from test_world import gorgon

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_doctor import open_care, open_procedure
from girlframe.engine import m3_doctor as rules
from girlframe.engine.m3_actor_bonds import is_helpless, make_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_doctor_care import CareService
from girlframe.services.m3_gorgon import GorgonService
from girlframe.services.m3_gorgon_play import GorgonPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def next_period(store, game):
    """Use the existing recorded world, real Strain choices and activation."""
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"strain"}}
            )
        }
    )
    strain = StrainService(OffDutyService(MissionService(store)), dice=D6())
    strain.configure(ADMIN, str(uuid4()), state(game).revision, "business_as_usual", frozenset())
    identity = strain.periods.begin(ADMIN, str(uuid4()))["id"]
    strain.periods.credit(
        PLAYER, str(uuid4()), identity, 1, state(game).revision, None, "No prior credit given"
    )
    strain.prepare(ADMIN, str(uuid4()), identity, 2, state(game).revision, facts(no_girl_void=True))
    for track, face, column, choice in (
        (
            "void",
            1,
            1,
            Choice(
                rule_id="strain.void.low.1.1",
                account="A real threat approaches from the map edge",
                gorgon=gorgon("directed", "new", (10, 0)),
            ),
        ),
        (
            "rebellion",
            1,
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="A real group appears",
                target="city0",
                faction=Faction(
                    id="group",
                    name="Local group",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Local dissent",
                ),
            ),
        ),
        (
            "budget",
            5,
            2,
            Choice(
                rule_id="strain.budget.low.5.2", account="Rooms are reassigned", rooms=((2, 3),)
            ),
        ),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        EffectService(strain).apply(
            ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice
        )
    activate(CycleService(strain.periods), game, identity)
    return identity


def actual_gorgon_play(store, game, patient):
    actor = ActorRef(kind="gorgon", entity="hunter")
    cast = CastService(ActorService(MissionService(store)))
    view = cast.view(ADMIN, 900)
    cast.change(
        ADMIN, str(uuid4()), 900, view["game_revision"], view["cast_revision"], "join", actor
    )
    service = GorgonPlayService(game)
    data = service.preview(ADMIN, 900)
    attacker = next(x for x in data["actors"] if x["ref"] == actor.model_dump(mode="json"))
    target = next(x for x in data["actors"] if x["ref"] == patient.model_dump(mode="json"))
    action = service.begin(
        ADMIN,
        str(uuid4()),
        900,
        data["revision"],
        Declaration(
            kind="attack",
            actor=actor,
            target=patient,
            assets=(attacker["assets"][0]["id"],),
            actor_sha256=attacker["source_sha256"],
            target_sha256=target["source_sha256"],
            account="Actual Gorgon Attack on this original patient",
            reach_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    with store.engine.connect() as c:
        started = game.action(c, action)["data"]["gorgon_play"]["started"]
    if not started:
        game.roll(ADMIN, str(uuid4()), action)
    with store.engine.connect() as c:
        capability = any(x["kind"] == "gorgon_asset_capability" for x in game.pending(c, action))
    if capability:
        answer(
            game,
            ADMIN,
            "gorgon_asset_capability",
            flag=True,
            text="Actual source judge confirms this Attack capability and reach",
        )
    tick(worker, gateway, 5)
    with store.engine.connect() as c:
        saved = game.action(c, action)
        assert saved["state"] == "complete" and not game.pending(c, action)
        assert game.lock(c, 900)["state"] == "released"
        assert saved["data"]["gorgon_play"]["fatal_prevented"]
        assert not saved["data"]["gorgon_play"].get("fatal_event")
    return action


def test_native_npc_metal_angel_preserves_real_attack_and_recovers_next_off_duty(
    ledger, tmp_path, monkeypatch
):
    source, game, patient = npc_patient(ledger, tmp_path, monkeypatch)
    acquire(game, rules.ANGEL)
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = update(
            actual.world, gorgons=(*actual.world.gorgons, gorgon("erratic", "hunter"))
        )
        # Existing bodily harm is a fixture, not an invented result of prevention.
        event = str(uuid4())
        actual = make_helpless(actual, patient, ActorRef(kind="gorgon", entity="hunter"), event)
        for sheet in actual.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.prior_patient_harm", actual, event_id=event)
    calls = game.dice.calls

    async def propose_and_confirm():
        interaction = current(2, 998811)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_procedure(interaction, source, source.menu(PLAYER, 900), "angel")
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(target=(patient.token,), account="PRIVATE_ANGEL actual ongoing care")
        submit = current(2, 998812)
        await form.confirm.callback(submit)
        assert form.completed
        await form.confirm.callback(submit)
        care = rules.values(state(game), "doctor_care", rules.Care)
        assert len(care) == 1 and care[0].angel and care[0].phase == "proposal"
        identity = care[0].id
        assert rules.saving_care(state(game), patient) is None
        item = next(x for x in InboxService(ledger).items(OTHER) if x.identity == identity)
        assert item.task == "m3_doctor_care" and item.incoming
        with pytest.raises(WorkflowError):
            CareService(game).get(ADMIN, identity)
        with pytest.raises(WorkflowError):
            CareService(game).confirm(
                PLAYER, str(uuid4()), identity, state(game).revision, "Cannot answer for patient"
            )
        confirmation = current(3, 998813)
        await confirmation.response.defer(ephemeral=True)
        await open_care(confirmation, source, identity)
        form = confirmation.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="PRIVATE_PATIENT I confirm actual received care")
        submit = current(3, 998814)
        await form.confirm.callback(submit)
        assert form.completed
        await form.confirm.callback(submit)
        return identity

    identity = asyncio.run(propose_and_confirm())
    care = CareService(game)
    assert care.get(OTHER, identity)["care"]["phase"] == "active"
    attacks = GorgonService(WorldService(MissionService(ledger)))
    data, attack = selection(attacks)
    assert attack.target == patient
    before = state(game)
    key = str(uuid4())
    result = attacks.attack(ADMIN, key, data["game_revision"], attack)
    assert result["outcome"] == "npc_kept_alive"
    assert attacks.attack(ADMIN, key, data["game_revision"], attack) == result
    actual = state(game)
    assert next(x for x in actual.world.npcs if x.id == patient.entity).alive
    assert actual.sheets == before.sheets and actual.world == before.world
    assert actual.scene_casts == before.scene_casts and is_helpless(actual, patient)
    prevention = [x for x in actual.facts if x.get("kind") == "doctor_prevented_death"]
    assert len(prevention) == 1 and prevention[0]["care"] == identity
    assert prevention[0]["event"] == result["id"]
    assert attacks.history(ADMIN) == [dict(id=result["id"], attack=attack.model_dump(mode="json"))]
    # The current saved-Play route uses the same genuine prevention source.
    action = actual_gorgon_play(ledger, game, patient)
    actual = state(game)
    assert actual.sheets == before.sheets and actual.world == before.world
    assert len([x for x in actual.facts if x.get("kind") == "doctor_prevented_death"]) == 2
    assert any(
        x.get("kind") == "gorgon_attack_npc_kept_alive" and x.get("action") == action
        for x in actual.facts
    )
    assert any(patient == role.actor for cast in actual.scene_casts for role in cast.roles)
    period = next_period(ledger, game)
    assert care.get(OTHER, identity)["care"]["period"] == period
    before_recovery = state(game)

    async def recover():
        for user, number in ((2, 998815), (3, 998817)):
            interaction = current(user, number)
            await interaction.response.defer(ephemeral=True)
            await open_care(interaction, source, identity)
            form = interaction.edit_original_response.call_args.kwargs["view"]
            form.values.update(account="PRIVATE_RECOVERY actual care throughout this Off-Duty")
            submit = current(user, number + 1)
            await form.confirm.callback(submit)
            assert form.completed
            await form.confirm.callback(submit)
            assert is_helpless(state(game), patient) == (user == 2)

    asyncio.run(recover())
    actual = state(game)
    assert care.get(OTHER, identity)["care"]["phase"] == "complete"
    assert actual.sheets == before_recovery.sheets and actual.world == before_recovery.world
    recovered = [x for x in actual.facts if x.get("kind") == "doctor_npc_recovered"]
    assert len(recovered) == 1 and recovered[0]["care"] == identity
    assert recovered[0]["period"] == period and game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    assert game.rebuild() > 0 and state(game) == actual


def test_protected_npc_cannot_die_through_an_unadapted_producer(ledger, tmp_path, monkeypatch):
    _, game, patient = npc_patient(ledger, tmp_path, monkeypatch)
    acquire(game, rules.ANGEL)
    care = CareService(game)
    identity = care.propose(
        PLAYER, str(uuid4()), state(game).revision, 900, patient, "Actual care", angel=True
    )["id"]
    care.confirm(OTHER, str(uuid4()), identity, state(game).revision, "Actual care received")
    before = state(game)
    with pytest.raises(WorkflowError, match="protected NPC death producer"):
        with ledger.transaction() as c:
            actual = state(game)
            actual.world = update(
                actual.world,
                npcs=tuple(
                    x.model_copy(update=dict(alive=False)) if x.id == patient.entity else x
                    for x in actual.world.npcs
                ),
            )
            game.event(c, 1, str(uuid4()), "synthetic.unadapted_lethal_consequence", actual)
    assert state(game) == before
