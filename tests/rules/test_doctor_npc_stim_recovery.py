"""Actual Nanobot care relieves one NPC Stim effect without erasing its drug source."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change as cast_change
from test_doctor_npc_nanobot import roll_nanobot, setup
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_mission_ui import current
from test_stim_sex import choose

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_doctor import open_choice
from girlframe.engine import m3_doctor as doctor
from girlframe.engine import m3_dose_up as dose
from girlframe.engine import m3_stim_sex as stim
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_doctor import DoctorService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_stim_sex import SexService, _drug, prove_effect
from girlframe.services.onboarding import WorkflowError


def test_real_npc_nanobot_relief_preserves_stim_drug_other_effect_and_expiry(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, patient, _ = setup(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(doctor.NANO, doctor.TRACK, dose.RULE, dose.SELF_RULE, stim.RULE),
    )
    # setup already used its CastService under the earlier synthetic registry.
    # Recreate it after adding Stim's scoped approval, rather than reuse that
    # service's cached old registry against the new exact approval digest.
    casts = CastService(ActorService(MissionService(ledger)))
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
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "The original NPC controller confirms actual voluntary interaction",
        npc_contact_account="The original human bodies are in real contact here, outside Frames",
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
    choose(game, ADMIN, "stim_sex_effects", ("bond",), native=True)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 8)
    before = state(game)
    drug = next(x for x in stim.records(before, stim.Drug) if x.target == patient)
    effect = next(x for x in stim.records(before, stim.Effect) if x.kind == "helpless")
    original_effects = stim.records(before, stim.Effect)
    original_tags = actor_tags(before, patient)
    assert is_helpless(before, patient) and stim.active(before, drug)
    controller_sheet = before.sheets["3"].model_copy(deep=True)
    game.dice.faces = (4, 4)
    # Zero spent Heat isolates the supported removal/expiry path. Positive
    # mandatory awards remain pending (test_doctor_npc_nanobot).
    treatment = roll_nanobot(game, patient, 0)
    tick(worker, gateway, 3)
    pass_tags(game)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "doctor_nanobot_benefits")
    effect_id = "stim_helpless:" + effect.id
    detail = game.decision(PLAYER, choice["id"])["doctor"]
    assert effect_id in {x["id"] for x in detail["effects"]}

    async def care():
        own = current(2, 997501)
        await own.response.defer(ephemeral=True)
        await open_choice(own, DoctorService(game), choice["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(choices=("remove",), effect=(effect_id,))
        await form.confirm.callback(current(2, 997502))
        assert form.completed
        assert is_helpless(state(game), patient)
        response = next(x for x in game.choices(ADMIN) if x["kind"] == "doctor_patient")
        with pytest.raises(WorkflowError):
            game.respond(
                OTHER,
                str(uuid4()),
                response["id"],
                response["revision"],
                ChoiceAnswer(options=("confirm",)),
            )
        assert is_helpless(state(game), patient)
        original = current(1, 997503)
        await original.response.defer(ephemeral=True)
        await open_choice(original, DoctorService(game), response["id"])
        form = original.edit_original_response.call_args.kwargs["view"]
        form.values.update(confirm=("confirm",))
        submitted = current(1, 997504)
        await form.confirm.callback(submitted)
        assert form.completed
        await form.confirm.callback(submitted)

    asyncio.run(care())
    relieved = state(game)
    assert not is_helpless(relieved, patient) and stim.active(relieved, drug)
    assert actor_tags(relieved, patient) == original_tags
    assert stim.records(relieved, stim.Effect) == original_effects
    recoveries = stim.records(relieved, stim.HelplessRecovery)
    assert len(recoveries) == 1
    assert recoveries[0].effect == effect.id and recoveries[0].drug == drug.id
    assert recoveries[0].doctor_action == treatment and recoveries[0].target == patient
    assert relieved.sheets["2"].heat == before.sheets["2"].heat
    assert relieved.sheets["2"].obsolescence_marked == 1 and game.dice.calls == 2
    assert relieved.sheets["3"] == controller_sheet and patient.entity not in relieved.sheets
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
            assert drug.tag in actor_tags(state(game), patient)
            game.bind_scene(ADMIN, str(uuid4()), 900)
            for human in (ADMIN, PLAYER, OTHER):
                game.join_scene(human, str(uuid4()), 900)
            cast_change(casts, ADMIN, "join", patient)
    final = state(game)
    assert drug.tag not in actor_tags(final, patient)
    assert any(x.label == "Still noticeable" for x in actor_tags(final, patient))
    with ledger.engine.connect() as c:
        assert prove_effect(game, c, final, effect.id) == effect
        assert _drug(game, c, final, drug.id) == drug
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    assert "PRIVATE_" not in str(gateway.messages)
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    assert game.rebuild() > 0 and state(game) == final
