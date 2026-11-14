"""A real player Nanobot treatment ends only its selected original Stim effect."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_stim_sex import choose
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_doctor import open_choice, open_roll
from girlframe.engine import m3_doctor as doctor
from girlframe.engine import m3_dose_up as dose
from girlframe.engine import m3_stim_sex as stim
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.m3_doctor import DoctorService
from girlframe.services.m3_stim_sex import SexService, _drug, prove_effect
from girlframe.services.onboarding import WorkflowError


def test_native_player_nanobot_relief_preserves_stim_source_other_effects_and_expiry(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="STIM-BLISSED", frame=doctor.BOOK)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(doctor.NANO, doctor.TRACK, dose.RULE, dose.SELF_RULE, stim.RULE),
    )
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"world", "playbooks"}}
            )
        }
    )
    with ledger.transaction() as c:
        before = state(game)
        before.world = initial()
        before = place(before, 2, mode="outside_frame")
        before = place(before, 3, mode="outside_frame")
        before.sheets["2"].heat = 3
        game.event(c, 1, str(uuid4()), "synthetic.original_doctor_context", before)
    worker, gateway = GameWorker(game), Gateway()
    patient = current_ref(state(game), 3)
    source = SexService(game)
    identity = source.invite(
        PLAYER,
        str(uuid4()),
        900,
        patient,
        state(game).revision,
        "PRIVATE_STIM_SOURCE Our actual voluntary original encounter",
    )["id"]
    source.respond(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "PRIVATE_STIM_CONFIRM My own actual voluntary source",
    )
    game.dice.faces = (6, 6)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=stim.PLAY,
            source_work=identity,
            target_actor=patient,
            heat=1,
            context="PRIVATE_STIM_CONTACT Actual owned encounter",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    choose(game, PLAYER, "stim_sex_drug", ("quick",), native=True)
    choose(game, PLAYER, "stim_sex_drug", ("calm",), native=True)
    choose(
        game, PLAYER, "stim_sex_effects", ("helpless", "tag"), tag="Still noticeable", native=True
    )
    choose(game, OTHER, "stim_sex_effects", ("bond",), native=True)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 8)
    before = state(game)
    drug = next(x for x in stim.records(before, stim.Drug) if x.target == patient)
    effect = next(x for x in stim.records(before, stim.Effect) if x.kind == "helpless")
    original_effects = stim.records(before, stim.Effect)
    original_tags = before.sheets["3"].tags
    assert is_helpless(before, patient) and stim.active(before, drug)
    game.dice.faces = (3, 4)

    async def begin_treatment():
        own = current(2, 998501)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_roll(own, DoctorService(game))
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("nanobot_injection",),
            target=(patient.token,),
            heat=("1",),
            account="PRIVATE_NANOBOT_SOURCE Actual injection of my original patient",
        )
        await form.confirm.callback(current(2, 998502))
        assert form.completed

    asyncio.run(begin_treatment())
    tick(worker, gateway, 3)
    pass_tags(game)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "doctor_nanobot_benefits")
    detail = game.decision(PLAYER, choice["id"])["doctor"]
    selected = "stim_helpless:" + effect.id
    assert selected in {x["id"] for x in detail["effects"]}
    assert "helpless" not in {x["id"] for x in detail["effects"]}
    saved = state(game)
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("remove",), fields={"effect": "helpless"}),
        )
    assert state(game) == saved

    async def care():
        own = current(2, 998503)
        await own.response.defer(ephemeral=True)
        await open_choice(own, DoctorService(game), choice["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(choices=("remove",), effect=(selected,))
        submitted = current(2, 998504)
        await form.confirm.callback(submitted)
        assert form.completed
        await form.confirm.callback(submitted)
        assert not is_helpless(state(game), patient)
        response = next(x for x in game.choices(OTHER) if x["kind"] == "doctor_patient")
        with pytest.raises(WorkflowError):
            game.respond(
                PLAYER,
                str(uuid4()),
                response["id"],
                response["revision"],
                ChoiceAnswer(),
            )
        patient_view = current(3, 998505)
        await patient_view.response.defer(ephemeral=True)
        await open_choice(patient_view, DoctorService(game), response["id"])
        form = patient_view.edit_original_response.call_args.kwargs["view"]
        form.values.update(none=("none",))
        await form.confirm.callback(current(3, 998506))
        assert form.completed

    asyncio.run(care())
    relieved = state(game)
    assert not is_helpless(relieved, patient) and stim.active(relieved, drug)
    assert relieved.sheets["3"].tags == original_tags
    assert stim.records(relieved, stim.Effect) == original_effects
    recoveries = stim.records(relieved, stim.HelplessRecovery)
    assert len(recoveries) == 1
    treatment = recoveries[0].doctor_action
    assert recoveries[0].effect == effect.id and recoveries[0].drug == drug.id
    assert recoveries[0].effect_event == effect.event and recoveries[0].target == patient
    assert relieved.sheets["2"].heat == before.sheets["2"].heat - 1
    assert relieved.sheets["3"].heat == before.sheets["3"].heat + 1
    assert relieved.sheets["2"].obsolescence_marked == 1 and game.dice.calls == 2
    assert game.inspect(PLAYER, treatment)["state"] == "complete"
    with ledger.engine.connect() as c:
        assert prove_effect(game, c, relieved, effect.id) == effect
        assert _drug(game, c, relieved, drug.id) == drug
    tick(worker, gateway, 8)
    for number in (1, 2):
        game.close_scene(ADMIN, str(uuid4()), 900)
        assert stim.expired(state(game), drug.id) == (number == 2)
        assert not is_helpless(state(game), patient)
        if number == 1:
            assert drug.tag in state(game).sheets["3"].tags
            game.bind_scene(ADMIN, str(uuid4()), 900)
            for human in (ADMIN, PLAYER, OTHER):
                game.join_scene(human, str(uuid4()), 900)
    final = state(game)
    assert drug.tag not in final.sheets["3"].tags
    assert any(x.label == "Still noticeable" for x in final.sheets["3"].tags)
    with ledger.engine.connect() as c:
        assert prove_effect(game, c, final, effect.id) == effect
        assert _drug(game, c, final, drug.id) == drug
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    assert "PRIVATE_" not in str(gateway.messages)
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    assert game.rebuild() > 0 and state(game) == final
