"""Two real independent repair producers reuse the owned Modular substitution."""

import asyncio
import copy
from uuid import uuid4

import test_creation_review
import test_m2_game
import test_strain_service
from test_doctor_runtime import doctor
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service as mission_service
from test_mission_ui import current
from test_repair_service import ready as repairs_ready

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_doctor import open_choice, open_roll
from girlframe.discord_adapter.m3_modular import open_purchase
from girlframe.discord_adapter.m3_repairs import open_quote
from girlframe.engine import m3_modular as rules
from girlframe.engine.drafts import DraftInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_modular import ModularService


def acquire(game, viewer, number):
    with game.store.transaction() as c:
        actual = state(game)
        actual.sheets[str(viewer.user_id)].permissions += 4
        game.event(c, 1, str(uuid4()), "synthetic.actual_modular_repair_funds", actual)

    async def run():
        own = current(viewer.user_id, number)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, ModularService(game))
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            name="Actual modular spare",
            description="Actual additional source hardware",
            account="Actual native Modular acquisition",
        )
        await form.confirm.callback(current(viewer.user_id, number + 1))
        assert form.completed

    asyncio.run(run())


def test_actual_doctor_nanobots_preserve_cost_and_patient_owns_void_replacement(
    ledger, tmp_path, monkeypatch
):
    original = test_m2_game.selected
    original_seed = test_creation_review.seed

    def seed_actual(store, viewer=PLAYER, callsign="SYNTH_A", notes="PRIVATE_CANARY"):
        if viewer != OTHER:
            return original_seed(store, viewer, callsign, notes)
        store.join(viewer, "join-3")
        store.save_draft(
            viewer,
            "draft-3",
            0,
            DraftInput(
                callsign=callsign,
                girl_playbook="MOCKINGBIRD",
                frame_playbook="WYVERN 0.4",
                notes=notes,
            ),
        )

    monkeypatch.setattr(test_creation_review, "seed", seed_actual)
    monkeypatch.setattr(
        test_m2_game,
        "selected",
        lambda girl, frame: original(girl, "WYVERN 0.4" if frame == "JANUS-B" else frame),
    )
    source, game = doctor(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    acquire(game, OTHER, 999901)
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].heat = 2
        patient = actual.sheets["3"]
        frame = next(x for x in patient.assets if x.family == "frame" and x.intrinsic is None)
        girl = next(x for x in patient.assets if x.family == "girl")
        frame.damaged = frame.void = True
        girl.damaged = True
        old, ordinary = copy.deepcopy(frame), girl.id
        game.event(c, 1, str(uuid4()), "synthetic.actual_patient_damage", actual)
    before = state(game)
    game.dice.faces = (3, 4)

    async def prepare():
        own = current(2, 999903)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_roll(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("nanobot_injection",),
            target=(current_ref(state(game), 3).token,),
            heat=("2",),
            account="I actually inject the patient with nanobots",
        )
        await form.confirm.callback(current(2, 999904))
        assert form.completed

    asyncio.run(prepare())
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    identity = game.choices(PLAYER)[0]["action_id"]
    raw = copy.deepcopy(game.inspect(PLAYER, identity)["receipt"])
    pass_tags(game)

    async def actual_repairs():
        choice = next(x for x in game.choices(PLAYER) if x["kind"] == "doctor_nanobot_benefits")
        own = current(2, 999905)
        await own.response.defer(ephemeral=True)
        await open_choice(own, source, choice["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(choices=("repair",))
        await form.confirm.callback(current(2, 999906))
        assert form.completed
        choice = next(x for x in game.choices(OTHER) if x["kind"] == "doctor_patient")
        patient = current(3, 999907)
        await patient.response.defer(ephemeral=True)
        await open_choice(patient, source, choice["id"])
        form = patient.edit_original_response.call_args.kwargs["view"]
        form.values.update(assets=(old.id, ordinary), modular_assets=(old.id,))
        form.values["modular_name:" + old.id] = "Actual Nano-time replacement"
        form.values["modular_description:" + old.id] = (
            "New hardware installed instead of this actual repair"
        )
        await form.confirm.callback(current(3, 999908))
        assert form.completed

    asyncio.run(actual_repairs())
    final = state(game)
    assert (
        final.sheets["2"].heat == 0
        and final.sheets["2"].obsolescence_marked == before.sheets["2"].obsolescence_marked + 1
    )
    assert final.sheets["3"].permissions == before.sheets["3"].permissions
    assert old.id not in {x.id for x in final.sheets["3"].assets}
    new = next(x for x in final.sheets["3"].assets if x.name == "Actual Nano-time replacement")
    assert not new.void and not new.damaged
    assert not next(x for x in final.sheets["3"].assets if x.id == ordinary).damaged
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.inspect(PLAYER, identity)["receipt"] == raw and game.dice.calls == 1
    fact = next(x for x in final.facts if x.get("kind") == "modular_repair")
    assert fact["source"].startswith("doctor:" + identity + ":") and "period" not in fact
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_actual_handler_quote_modular_replacement_charges_exactly_once(
    ledger, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        test_strain_service,
        "service",
        lambda store, frame: mission_service(store, girl="ALPHA", frame="WYVERN 0.4"),
    )
    source, cycle, game, period = repairs_ready(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    acquire(game, PLAYER, 999921)
    from girlframe.services.m3_access import Access

    cycle.missions.access = Access(ledger)
    quoted = source.offer(ADMIN, str(uuid4()), state(game).revision, period, 2, "frame:1", 2)
    before = state(game)
    data = source.get(PLAYER, quoted["id"])
    calls = game.dice.calls

    async def accept():
        own = current(2, 999923)
        await own.response.defer(ephemeral=True)
        await open_quote(own, source, quoted["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(answer=("accept",), modular_assets=("frame:1",))
        form.values["modular_name:frame:1"] = "Actual quoted replacement"
        form.values["modular_description:frame:1"] = (
            "New hardware instead of this exactly priced repair"
        )
        await form.confirm.callback(current(2, 999924))
        assert form.completed

    asyncio.run(accept())
    from girlframe.engine.m3_modular import Replacement

    result = source.respond(
        PLAYER,
        "999924",
        quoted["id"],
        data["game_revision"],
        data["revision"],
        True,
        replacement=Replacement(
            asset="frame:1",
            name="Actual quoted replacement",
            description="New hardware instead of this exactly priced repair",
        ),
    )
    assert result["state"] == "accepted"
    final = state(game)
    assert final.sheets["2"].permissions == before.sheets["2"].permissions - 2
    assert "frame:1" not in {x.id for x in final.sheets["2"].assets}
    new = next(x for x in final.sheets["2"].assets if x.name == "Actual quoted replacement")
    assert not new.void and not new.damaged and game.dice.calls == calls
    fact = next(x for x in final.facts if x.get("kind") == "modular_repair")
    assert fact["source"] == "repair_quote:" + quoted["id"] and "period" not in fact
