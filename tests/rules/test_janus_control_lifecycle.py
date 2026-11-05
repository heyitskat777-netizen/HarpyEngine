"""Actual repeated low rolls reach real final-Tag control and owned Void follow-through."""

import json
from uuid import uuid4

import pytest
from test_frame_control import exposed_core, place_original
from test_janus_battery import start
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_void_keep import keep

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_frame_control import controller
from girlframe.services.m3_frame_control import FrameControlService
from girlframe.services.m3_void import VoidService
from girlframe.services.onboarding import WorkflowError


def test_four_real_low_contacts_free_original_core_without_fake_removals_or_stale_pilot_control(
    ledger, tmp_path, monkeypatch
):
    game, caster, core = exposed_core(ledger, tmp_path, monkeypatch, exposed=False)
    place_original(game, caster)
    controls = FrameControlService(game)
    controls.relink(
        PLAYER,
        str(uuid4()),
        caster,
        state(game).revision,
        "I actually link inside my original available Frame",
    )
    original = state(game)
    frame = original.janus_cores[-1].frame_instance
    assert controller(original, caster, frame) == caster
    worker, gateway = GameWorker(game), Gateway()
    game.dice.faces = (1, 1)
    final = None
    for key in ("drugged", "surgery", "muzzled", "restrained"):
        contact = controls.propose(
            PLAYER,
            str(uuid4()),
            900,
            caster,
            core,
            "I physically reconnect the original actual spinal jack",
        )["id"]
        controls.decide(
            ADMIN,
            str(uuid4()),
            contact,
            state(game).revision,
            True,
            "The original actual jack and spinal port remain physically accessible",
        )
        action = start(game, core)
        tick(worker, gateway, 3)
        if game.inspect(PLAYER, action)["state"] != "tag_window":
            game.roll(PLAYER, str(uuid4()), action)
        pass_tags(game)
        with pytest.raises(WorkflowError):
            controls.unplug(
                PLAYER,
                str(uuid4()),
                contact,
                state(game).revision,
                "Cannot waive the known mandatory low result",
            )
        tag = state(game).janus_cores[-1].baseline_tags[key]
        answer(game, PLAYER, "janus_erase", options=(tag,))
        if key != "restrained":
            answer(game, PLAYER, "janus_select", options=("heat",), number=1)
            tick(worker, gateway, 5)
            controls.unplug(
                PLAYER,
                str(uuid4()),
                contact,
                state(game).revision,
                "I actually unplug this completed source connection",
            )
        else:
            final = (action, contact)
    action, contact = final
    after = state(game)
    assert not after.janus_cores[-1].tags
    assert controller(after, caster, frame) == core
    assert next(x for x in after.placements if x.actor == caster).mode == "inside_frame"
    assert (
        next(x for x in after.placements if x.actor == caster).girl_cell
        == original.placements[0].girl_cell
    )
    assert all(x.void for x in after.sheets["2"].assets if x.family == "frame")
    work = next(x for x in game.choices(PLAYER) if x["kind"] == "janus_void_threshold")
    work_id = json.loads(work["body_json"])["work_id"]
    assert VoidService(ledger).get(PLAYER, work_id)["stage"] == "resist_pending"
    keep(game, worker, gateway, action, work_id)
    answer(game, PLAYER, "janus_select", options=("heat",), number=1)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 5
    tick(worker, gateway, 5)
    controls.unplug(
        PLAYER,
        str(uuid4()),
        contact,
        state(game).revision,
        "I remove the actual old Pilot's neural jack",
    )
    assert controller(state(game), caster, frame) == core
    with pytest.raises(WorkflowError):
        controls.relink(
            PLAYER,
            str(uuid4()),
            caster,
            state(game).revision,
            "An ordinary link cannot displace the actual original Core",
        )
    assert state(game).janus_cores[-1].controller == OTHER.user_id
