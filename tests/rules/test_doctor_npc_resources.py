"""Three genuine NPC Nanobot results and held legacy recovery; synthetic policy only."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_doctor_npc_nanobot import roll_nanobot, setup
from test_dose_up import native_choice
from test_items import carried_asset, transfer
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_doctor import open_choice, open_roll
from girlframe.discord_adapter.m3_npc_resources import open_npc_resources
from girlframe.engine import m3_dose_up as dose_rules
from girlframe.engine import m3_npc_resources as resources
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_items import mechanical_assets
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.services.m3_doctor import DoctorService
from girlframe.services.m3_dose_up import DoseUpService
from girlframe.services.m3_npc_resources import NpcResourcesService, prove
from girlframe.services.onboarding import WorkflowError


def setup_equipment(game, patient):
    """Existing damaged Girl equipment, factual carried proof, actual transfer to NPC."""
    with game.store.transaction() as c:
        canon = state(game)
        chosen = tuple(x.id for x in canon.sheets["3"].assets if x.family == "girl")[:2]
        assert len(chosen) == 2
        for asset in canon.sheets["3"].assets:
            if asset.id in chosen:
                asset.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.prior_actual_equipment_damage", canon)
    actual = []
    for identity in chosen:
        asset = next(x for x in state(game).sheets["3"].assets if x.id == identity)
        carried_asset(game, OTHER, asset)
        actual.append(transfer(game, current_ref(state(game), 3), patient, "asset:" + identity))
    assert len(mechanical_assets(state(game), patient)) == 2
    return tuple(x.id for x in actual)


def record_native(game, patient):
    source = NpcResourcesService(game)

    async def record():
        first = current(1, int(uuid4().int % 1000000000))
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await open_npc_resources(first, source, patient)
        count = first.edit_original_response.call_args.kwargs["view"]
        count.values.update(count=("1",))
        second = current(1, int(uuid4().int % 1000000000))
        await count.confirm.callback(second)
        form = second.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            heat="2",
            name_0="Keeps promises",
            marked_0=("yes",),
            account="PRIVATE_WITNESSED_FACTS This original NPC has two Heat "
            "and her established marked Identity; no Girl sheet is granted",
        )
        submit = current(1, int(uuid4().int % 1000000000))
        await form.confirm.callback(submit)
        assert form.completed
        await form.confirm.callback(submit)

    asyncio.run(record())
    return source.view(ADMIN, patient)["resources"]


def begin_native(game, worker, gateway, patient, faces, heat):
    game.dice.faces = faces

    async def begin():
        interaction = current(2, int(uuid4().int % 1000000000))
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_roll(interaction, DoctorService(game))
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("nanobot_injection",),
            target=(patient.token,),
            heat=(str(heat),),
            account="PRIVATE_TREATMENT I inject this original reachable NPC",
        )
        await form.confirm.callback(current(2, int(uuid4().int % 1000000000)))
        assert form.completed

    asyncio.run(begin())
    with game.store.engine.connect() as c:
        table = t.m2["m2_actions"]
        identity = c.scalar(
            sa.select(table.c.id).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.state.not_in(("complete", "aborted")),
            )
        )
    tick(worker, gateway, 3)
    pass_tags(game)
    return identity


def choice_native(game, viewer, kind, **values):
    row = next(x for x in game.choices(viewer) if x["kind"] == kind)

    assert not game.decision(viewer, row["id"])["doctor"].get("unsupported")

    async def choose():
        interaction = current(viewer.user_id, int(uuid4().int % 1000000000))
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, DoctorService(game), row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submit = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(submit)
        assert form.completed, submit.edit_original_response.call_args_list
        await form.confirm.callback(submit)

    asyncio.run(choose())
    return row


def dose_tag(game, worker, gateway, patient):
    source = DoseUpService(game.store, game)
    contact = source.record_contact(
        PLAYER,
        str(uuid4()),
        900,
        patient,
        state(game).revision,
        "Actual original body reaches the exposed vein",
    )["id"]
    game.dice.faces = (6, 6)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=dose_rules.PLAY,
            target_actor=patient,
            source_work=contact,
            heat=1,
            context="Real original NPC physiology",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    native_choice(game, PLAYER, ("quick", "calm"))
    native_choice(game, ADMIN, ("sense",))
    tick(worker, gateway, 8)
    return next(
        x
        for x in dose_rules.records(state(game), dose_rules.NpcDrugTag)
        if x.dose == action and x.component == "quick"
    )


def test_npc_nanobot_low_repairs_real_carried_asset_and_reopens_private_source(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, patient, _ = setup(ledger, tmp_path, monkeypatch)
    items = setup_equipment(game, patient)
    before_setup = state(game)
    with pytest.raises(WorkflowError):
        NpcResourcesService(game).record(
            OTHER,
            str(uuid4()),
            before_setup.revision,
            900,
            patient,
            2,
            (("Keeps promises", True),),
            "Not the original appointed factual witness",
        )
    assert state(game) == before_setup
    saved = record_native(game, patient)
    with pytest.raises(WorkflowError, match="STALE_NPC_RESOURCES"):
        NpcResourcesService(game).record(
            ADMIN,
            str(uuid4()),
            before_setup.revision,
            900,
            patient,
            99,
            (),
            "A stale setup cannot replace the original source",
        )
    before = state(game)
    action = begin_native(game, worker, gateway, patient, (2, 3), 0)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "doctor_patient")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=items[:1])
        )
    choice_native(game, ADMIN, "doctor_patient", assets=items[:1])
    actual = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert (
        next(x for x in actual.held_items if x.id == items[0]).asset_json
        != next(x for x in before.held_items if x.id == items[0]).asset_json
    )
    assert [x.damaged for x in mechanical_assets(actual, patient)] == [False, True]
    assert actual.sheets["3"] == before.sheets["3"] and patient.entity not in actual.sheets
    assert NpcResourcesService(game).view(ADMIN, patient)["resources"]["heat"] == saved["heat"]
    with pytest.raises(WorkflowError):
        NpcResourcesService(game).view(OTHER, patient)
    with ledger.engine.connect() as c:
        assert prove(game, c, actual, patient).id == saved["id"]
    assert game.dice.calls == 1 and actual.sheets["2"].obsolescence_marked == 1


def test_npc_nanobot_mid_gives_actual_spent_heat_removes_real_drug_and_unmarks_identity(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, patient, _ = setup(ledger, tmp_path, monkeypatch)
    drug = dose_tag(game, worker, gateway, patient)
    saved = record_native(game, patient)
    before = state(game)
    action = begin_native(game, worker, gateway, patient, (3, 4), 1)
    receipt = game.inspect(PLAYER, action)["receipt"]
    doctor_row = next(x for x in game.choices(PLAYER) if x["kind"] == "doctor_nanobot_benefits")
    doctor_view = game.decision(PLAYER, doctor_row["id"])
    assert doctor_view["doctor"]["identities"] == []
    assert saved["identities"][0]["name"] not in str(doctor_view)
    assert saved["identities"][0]["id"] not in str(doctor_view)
    choice_native(
        game,
        PLAYER,
        "doctor_nanobot_benefits",
        choices=("remove", "identity"),
        effect=("tag:" + drug.id,),
    )
    patient_row = next(x for x in game.choices(ADMIN) if x["kind"] == "doctor_patient")
    assert game.decision(ADMIN, patient_row["id"])["doctor"]["identities"] == [
        dict(id=saved["identities"][0]["id"], label=saved["identities"][0]["name"])
    ]
    # The physician chooses the benefit; the actual NPC retains the final sheet details.
    assert drug.id in {x.id for x in actor_tags(state(game), patient)}
    choice_native(game, ADMIN, "doctor_patient", identity=(saved["identities"][0]["id"],))
    actual = resources.current(state(game), patient)
    assert actual.heat == 3 and not actual.identities[0].marked
    assert drug.id not in {x.id for x in actor_tags(state(game), patient)}
    assert len(actual.awards) == 1 and actual.awards[0].amount == 1
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 2
    assert state(game).sheets["3"] == before.sheets["3"]


def test_npc_nanobot_high_awards_five_and_repairs_two_real_items_after_owned_choice(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, patient, _ = setup(ledger, tmp_path, monkeypatch)
    items = setup_equipment(game, patient)
    saved = record_native(game, patient)
    action = begin_native(game, worker, gateway, patient, (6, 6), 0)
    choice_native(game, PLAYER, "doctor_nanobot_benefits", choices=("repair", "identity"))
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "doctor_patient")
    before = state(game)
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(
                options=(items[0], "invented"), fields={"identity": saved["identities"][0]["id"]}
            ),
        )
    assert state(game) == before
    choice_native(
        game, ADMIN, "doctor_patient", assets=items, identity=(saved["identities"][0]["id"],)
    )
    value = NpcResourcesService(game).view(ADMIN, patient)["resources"]
    assert value["heat"] == 7 and not value["identities"][0]["marked"]
    assert all(not x.damaged for x in mechanical_assets(state(game), patient))
    assert len(value["awards"]) == 1 and value["awards"][0]["amount"] == 5
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_legacy_positive_heat_reopens_after_setup_without_repeating_real_removal_or_cost(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, patient, _ = setup(ledger, tmp_path, monkeypatch)
    drug = dose_tag(game, worker, gateway, patient)
    game.dice.faces = (3, 4)
    action = roll_nanobot(game, patient, 1)
    choice_native(
        game, PLAYER, "doctor_nanobot_benefits", choices=("remove",), effect=("tag:" + drug.id,)
    )
    choice_native(game, ADMIN, "doctor_patient", confirm=("confirm",))
    receipt = game.inspect(PLAYER, action)["receipt"]
    before = state(game)
    assert not resources.original(before, patient)
    assert drug.id not in {x.id for x in actor_tags(before, patient)}
    assert game.inspect(PLAYER, action)["state"] != "complete"
    saved = record_native(game, patient)
    choice_native(game, ADMIN, "doctor_patient", confirm=("confirm",))
    actual = NpcResourcesService(game).view(ADMIN, patient)["resources"]
    assert actual["heat"] == saved["heat"] + 1 and len(actual["awards"]) == 1
    assert len([x for x in state(game).facts if x.get("kind") == "doctor_npc_effect_removed"]) == 1
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 2
    assert (
        state(game).sheets["2"].obsolescence_marked == before.sheets["2"].obsolescence_marked == 1
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
