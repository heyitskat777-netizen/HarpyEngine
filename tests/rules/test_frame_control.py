"""Actual original spinal contact needs factual access; it never creates a body or Frame."""

import asyncio

import pytest
from test_janus_core import facts
from test_janus_core_service import cast_core, change, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_frame_control import open_neural_links
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_janus import ref
from girlframe.services.m3_frame_control import FrameControlService, prepare_battery
from girlframe.services.onboarding import WorkflowError


def exposed_core(store, tmp_path, monkeypatch, *, exposed=True):
    service, game = ready(store, tmp_path, monkeypatch)
    identity = service.request(PLAYER, "actual-original-core-contact-setup", 3)["id"]
    change(service, OTHER, identity, facts=facts().model_copy(update={"exposed": exposed}))
    change(
        service,
        ADMIN,
        identity,
        approve=True,
        account="Actual source body and spinal exposure facts reviewed",
    )
    core = ref(state(game).janus_cores[0])
    cast_core(service, game, core)
    return game, current_ref(state(game), 2), core


def test_actual_restrained_exposed_core_contact_has_judge_facts_without_fictional_consent(
    ledger, tmp_path, monkeypatch
):
    game, caster, core = exposed_core(ledger, tmp_path, monkeypatch)
    service = FrameControlService(game)
    before = state(game)
    value = service.propose(
        PLAYER,
        "actual-spinal-contact",
        900,
        caster,
        core,
        "My neural jack reaches the actual exposed original Core in my own cockpit",
    )
    assert value["phase"] == "review"
    assert not service.get(OTHER, value["id"])["can_act"]
    with pytest.raises(WorkflowError):
        service.decide(
            OTHER,
            "no-invented-core-choice",
            value["id"],
            state(game).revision,
            True,
            "Core's body cannot supply invented willing dialogue",
        )
    with ledger.engine.connect() as c:
        with pytest.raises(WorkflowError):
            prepare_battery(game, c, state(game), caster, core, 900)
    service.decide(
        ADMIN,
        "actual-source-contact-review",
        value["id"],
        state(game).revision,
        True,
        "The exposed spinal cord and actual neural jack establish this performed contact",
    )
    canon = state(game)
    with ledger.engine.connect() as c:
        meta = prepare_battery(game, c, canon, caster, core, 900)
    assert meta["connection"] == value["id"] and canon.neural_connections[-1].target_event is None
    assert canon.placements == before.placements and canon.sheets == before.sheets
    assert canon.janus_cores == before.janus_cores
    assert canon.neural_connections[-1].phase == "connected"
    with pytest.raises(WorkflowError):
        service.unplug(
            OTHER,
            "restrained-core-cannot-move",
            value["id"],
            canon.revision,
            "Attempted physical unplug while restrained",
        )
    service.unplug(
        PLAYER,
        "actual-caster-unplug",
        value["id"],
        canon.revision,
        "I physically remove my actual jack from this original spinal port",
    )
    assert state(game).neural_connections[-1].phase == "unplugged"
    assert state(game).sheets == before.sheets and state(game).placements == before.placements


def test_unknown_spinal_access_stays_pending_until_real_review_and_duplicate_is_rejected(
    ledger, tmp_path, monkeypatch
):
    game, caster, core = exposed_core(ledger, tmp_path, monkeypatch, exposed=False)
    service = FrameControlService(game)
    before = state(game)
    identity = service.propose(
        PLAYER,
        "no-guessed-spinal-access",
        900,
        caster,
        core,
        "Actual proposed internal jack access still needs the source judge's physical review",
    )["id"]
    assert state(game).neural_connections[-1].port_access == "reviewed_port"
    assert state(game).neural_connections[-1].id == identity
    with ledger.engine.connect() as c:
        with pytest.raises(WorkflowError):
            prepare_battery(game, c, state(game), caster, core, 900)
    with pytest.raises(WorkflowError):
        service.propose(
            PLAYER,
            "duplicate-unknown-spinal-access",
            900,
            caster,
            core,
            "A pending original contact cannot be duplicated",
        )
    assert state(game).sheets == before.sheets and state(game).placements == before.placements
    assert not state(game).janus_cores[-1].exposed


def place_original(game, actor, *, outside=False):
    from uuid import uuid4

    from girlframe.engine import m3_physical
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.engine.m3_world_state import Board, World
    from girlframe.services.m3_actors import profiles

    with game.store.transaction() as c:
        canon = state(game)
        if canon.world is None:
            canon.world = World(board=Board(minimum=(-2, -2), maximum=(2, 2)), locations=())
        frame = canon.janus_cores[-1].frame_instance
        canon = m3_physical.initial(
            canon,
            profiles(c, game.store.campaign_id),
            InitialPlacement(
                actor=actor,
                frame_instance=frame,
                girl_cell=(0, 0),
                frame_cell=(1, 1) if outside else (0, 0),
                mode="outside_frame" if outside else "inside_frame",
                account="Actual original known body/cockpit and Frame facts",
                facts_confirmed=True,
            ),
            "actual-original-physical-vessel",
            str(uuid4()),
            str(uuid4()),
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_source_pose", canon)


def test_baseline_unexposed_core_has_actual_internal_spinal_port_without_combat_exposure(
    ledger, tmp_path, monkeypatch
):
    game, caster, core = exposed_core(ledger, tmp_path, monkeypatch, exposed=False)
    place_original(game, caster)
    service = FrameControlService(game)
    before = state(game)
    identity = service.propose(
        PLAYER,
        "actual-inside-spinal-port",
        900,
        caster,
        core,
        "Inside this exact original cockpit I connect the actual internal spinal jack",
    )["id"]
    assert state(game).neural_connections[-1].port_access == "own_cockpit"
    service.decide(
        ADMIN,
        "actual-internal-contact-review",
        identity,
        state(game).revision,
        True,
        "The original cockpit's internal spinal port and actual contact are verified",
    )
    with ledger.engine.connect() as c:
        assert prepare_battery(game, c, state(game), caster, core, 900)["connection"] == identity
    assert state(game).placements == before.placements and not state(game).janus_cores[-1].exposed


def test_actual_separated_body_and_frame_reject_spinal_reach_without_teleport(
    ledger, tmp_path, monkeypatch
):
    game, caster, core = exposed_core(ledger, tmp_path, monkeypatch, exposed=False)
    place_original(game, caster, outside=True)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="separated"):
        FrameControlService(game).propose(
            PLAYER,
            "no-remote-spinal-jack",
            900,
            caster,
            core,
            "A known separate body cannot reach the original Core remotely",
        )
    assert state(game).model_dump_json() == before


def test_real_neural_contact_native_nested_next_form_keeps_original_judge_question(
    ledger, tmp_path, monkeypatch
):
    game, caster, core = exposed_core(ledger, tmp_path, monkeypatch)
    service = FrameControlService(game)

    async def propose():
        caller = current(2, 99410)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_neural_links(caller, service, caster, core)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values["account"] = "My actual neural jack connects through the accessible spinal port"
        submit = current(2, 99411)
        submit.channel_id = 900
        await form.confirm.callback(submit)
        assert form.completed

    asyncio.run(propose())
    value = state(game).neural_connections[-1]
    assert (
        value.phase == "review" and value.caster_controller == 2 and value.battery_controller == 3
    )
    assert service.get(ADMIN, value.id)["can_act"]
    assert not service.get(PLAYER, value.id)["can_act"]


def test_optional_other_body_contact_needs_its_actual_confirmation_then_separate_judge(
    ledger, tmp_path, monkeypatch
):
    game, caster, _ = exposed_core(ledger, tmp_path, monkeypatch)
    battery = current_ref(state(game), 3)
    service = FrameControlService(game)
    identity = service.propose(
        PLAYER,
        "actual-optional-contact",
        900,
        caster,
        battery,
        "We establish the actual optional spinal contact through the known jack",
    )["id"]
    assert service.get(OTHER, identity)["connection"]["phase"] == "target"
    with pytest.raises(WorkflowError):
        service.decide(
            ADMIN,
            "judge-cannot-invent-consent",
            identity,
            state(game).revision,
            True,
            "Not this original body's contact response",
        )
    service.decide(
        OTHER,
        "actual-other-body-contact",
        identity,
        state(game).revision,
        True,
        "I confirm this actual contact with my original body",
    )
    assert service.get(ADMIN, identity)["connection"]["phase"] == "review"
    service.decide(
        ADMIN,
        "actual-optional-physical-review",
        identity,
        state(game).revision,
        True,
        "The actual original bodies, jack, reach and spinal access establish contact",
    )
    assert service.get(PLAYER, identity)["connection"]["phase"] == "connected"


def test_actual_original_end_interrupts_authority_without_fake_unplug_and_rolls_back_atomically(
    ledger, tmp_path, monkeypatch
):
    from uuid import uuid4

    from girlframe.services import m3_frame_control as controls
    from girlframe.services.m3_careers import end_in_transaction, synchronize_end

    game, caster, core = exposed_core(ledger, tmp_path, monkeypatch)
    service = FrameControlService(game)
    identity = service.propose(
        PLAYER,
        "actual-ending-contact",
        900,
        caster,
        core,
        "Actual performed spinal contact before this original ending",
    )["id"]
    service.decide(
        ADMIN,
        "actual-ending-contact-review",
        identity,
        state(game).revision,
        True,
        "Actual contact and original bodies reviewed",
    )
    before = state(game).model_dump_json()
    real = controls.synchronize_endings

    def fail(*args, **kwargs):
        raise WorkflowError("Actual injected source callback failure")

    def end():
        with ledger.transaction() as c:
            event = str(uuid4())
            canon = end_in_transaction(
                c,
                game,
                state(game),
                caster,
                reason="death",
                source_event=event,
                account="Actual original fatal source fixture",
                archive_id="actual-contact-original-end",
            )
            game.event(
                c, 2, "actual-contact-ending-source", "m3.synthetic_ending", canon, event_id=event
            )
            synchronize_end(c, game, canon.career_archives[-1])

    monkeypatch.setattr(controls, "synchronize_endings", fail)
    with pytest.raises(WorkflowError, match="callback failure"):
        end()
    assert state(game).model_dump_json() == before
    monkeypatch.setattr(controls, "synchronize_endings", real)
    end()
    canon = state(game)
    assert canon.neural_connections[-1].phase == "ended"
    assert canon.neural_connections[-1].ended_by == caster
    assert canon.neural_connections[-1].connected_event
    assert "unplug" not in canon.neural_connections[-1].end_account.lower()
    assert canon.career_archives[-1].actor == caster and "2" not in canon.sheets
