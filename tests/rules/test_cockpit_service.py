"""Owned actual cockpit controls and source-proved Frame consent/extraction."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_physical_service import decide, propose, ready

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_physical import open_frame, open_initial
from girlframe.engine import m3_physical as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.m3_physical_state import CockpitAction, ExtractionConsent, InitialPlacement
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError


def placed(store):
    svc, game = ready(store)
    request = propose(svc)
    decide(svc, request["id"])
    return svc, game


def command(svc, operation="exit", *, viewer=PLAYER, data=None):
    data = data or svc.preview(viewer)
    return data, CockpitAction(
        actor=ActorRef.model_validate(data["actor"]),
        operation=operation,
        expected_position=data["position_sha256"],
        account="PRIVATE_ACTUAL_COCKPIT_ACTION",
        confirmed=True,
    )


def locked(store):
    svc, game = placed(store)
    policy = store.policy.owner_m3_rulings
    store.policy = store.policy.model_copy(
        update={
            "owner_m3_rulings": policy.model_copy(
                update={
                    "physical_frame_voice": "controller_or_handler",
                }
            )
        }
    )
    with store.transaction() as c:
        canon = state(game)
        world = canon.world
        canon.world = world.model_copy(
            update={
                "npcs": world.npcs
                + (
                    Npc(
                        id="physical-helper",
                        name="Actual helper",
                        jobs=("guard",),
                        detail="Actual present role",
                        controller=3,
                        cell=(0, 0),
                    ),
                )
            }
        )
        actor = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
        source = str(uuid4())
        canon = rules.lock_cockpit(
            canon, profiles(c, store.campaign_id), actor, source, "PRIVATE_ACTUAL_SUBSUMPTION"
        )
        game.event(
            c, 2, "actual-sourced-subsumption", "m3.synthetic_subsumption", canon, event_id=source
        )
    return svc, game, state(game).frame_locks[0].id


def respond(svc, identity, action="allow", *, viewer=ADMIN, key=None, data=None, target=None):
    data = data or svc.frame(viewer, identity, target)
    return svc.respond_frame(
        viewer,
        key or str(uuid4()),
        identity,
        data["expected"],
        data["revision"],
        action,
        "PRIVATE_ACTUAL_FRAME_RESPONSE",
        target=target,
    )


def test_actual_ordinary_cockpit_exit_and_control_are_owned_durable_and_exactly_once(ledger):
    svc, game = placed(ledger)
    data, choice = command(svc)
    before = state(game)
    with pytest.raises(WorkflowError, match="original Girl's owner"):
        svc.operate(OTHER, "wrong-body", data["game_revision"], choice)
    result = svc.operate(PLAYER, "actual-exit-once", data["game_revision"], choice)
    assert svc.operate(PLAYER, "actual-exit-once", data["game_revision"], choice) == result
    exited = state(game)
    assert exited.placements[0].mode == "outside_frame" and exited.sheets == before.sheets
    assert exited.placements[0].vessel_id == before.placements[0].vessel_id
    data, choice = command(svc, "pilot")
    svc.operate(PLAYER, "actual-enter-pilot", data["game_revision"], choice)
    assert state(game).placements[0].mode == "piloting"
    with ledger.engine.connect() as c:
        assert "PRIVATE_ACTUAL" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    assert game.rebuild() > 0 and state(game).placements[0].mode == "piloting"


def test_pause_stale_state_and_missing_registry_cannot_move_the_body(ledger, monkeypatch, tmp_path):
    svc, game = placed(ledger)
    data, choice = command(svc)
    ledger.safety(OTHER, "pause-cockpit", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.operate(PLAYER, "paused-exit", data["game_revision"], choice)
    ledger.safety(OTHER, "resume-cockpit", ledger.status(OTHER)["revision"], pause=False)
    with pytest.raises(WorkflowError, match="STALE_COCKPIT"):
        svc.operate(PLAYER, "stale-exit", data["game_revision"] - 1, choice)
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(tmp_path / "missing.json"))
    with pytest.raises(WorkflowError, match="registry is unavailable"):
        svc.operate(PLAYER, "disabled-exit", data["game_revision"], choice)
    assert state(game).placements[0].mode == "piloting"


def test_real_frame_refusal_consent_and_separate_extractor_preserve_dead_vitals(ledger):
    svc, game, identity = locked(ledger)
    original_vessel = state(game).placements[0].vessel_id
    with pytest.raises(WorkflowError, match="human voice"):
        respond(svc, identity, viewer=PLAYER)
    respond(svc, identity, "refuse")
    assert not svc.frame(OTHER, identity)["extractors"]
    before = svc.frame(ADMIN, identity)
    allowed = respond(svc, identity, key="actual-frame-yes", data=before)
    assert respond(svc, identity, key="actual-frame-yes", data=before) == allowed
    data = svc.frame(OTHER, identity)
    assert data["allowed"] and len(data["extractors"]) == 1
    helper = ActorRef.model_validate(data["extractors"][0]["ref"])
    outcome = svc.extract_body(
        OTHER,
        "actual-extraction",
        identity,
        data["expected"],
        data["revision"],
        helper,
        "PRIVATE_ACTUAL_HELPER_EXTRACTION",
    )
    assert (
        svc.extract_body(
            OTHER,
            "actual-extraction",
            identity,
            data["expected"],
            data["revision"],
            helper,
            "PRIVATE_ACTUAL_HELPER_EXTRACTION",
        )
        == outcome
    )
    body = state(game).placements[0]
    assert body.mode == "outside_frame" and not body.subsumed and not body.vitals_active
    assert body.vessel_id == original_vessel
    assert svc.frame(PLAYER, identity)["present"] is False


def test_frame_opening_does_not_extract_or_heal_but_allows_actual_present_extraction(ledger):
    svc, game, identity = locked(ledger)
    original = state(game).placements[0]
    respond(svc, identity, "open")
    assert state(game).placements[0] == original and not state(game).frame_locks[0].active
    data = svc.frame(OTHER, identity)
    helper = ActorRef.model_validate(data["extractors"][0]["ref"])
    svc.extract_body(
        OTHER,
        "after-opening-extraction",
        identity,
        data["expected"],
        data["revision"],
        helper,
        "Actual extraction after Frame opens",
    )
    assert not state(game).placements[0].vitals_active


def test_source_forged_frame_consent_and_release_cannot_grant_extraction(ledger):
    svc, game, identity = locked(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        lock = canon.frame_locks[0]
        forged = ExtractionConsent(
            actor=lock.subject,
            controller=1,
            allowed=True,
            source_event="not-an-actual-frame-response",
            account="Forged",
        )
        canon.frame_locks[0] = lock.model_copy(update={"consents": (forged,)})
        game.event(c, 1, "forged-frame-state", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="SOURCE_FRAME_CONSENT_MISSING"):
        svc.frame(PLAYER, identity)


def test_actual_cockpit_source_and_response_are_readable_during_pause_without_registry(
    ledger, monkeypatch, tmp_path
):
    svc, _, identity = locked(ledger)
    ledger.safety(OTHER, "pause-frame-consent", ledger.status(OTHER)["revision"], pause=True)
    assert svc.frame(PLAYER, identity)["active"]
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        respond(svc, identity)
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(tmp_path / "missing.json"))
    assert svc.frame(ADMIN, identity)["can_voice"]
    with pytest.raises(WorkflowError, match="registry is unavailable"):
        respond(svc, identity)


def test_native_owned_position_operations_and_actual_frame_response_then_extraction(ledger):
    svc, game, identity = locked(ledger)

    async def run():
        handler = current(1, 60301)
        await handler.response.defer(ephemeral=True)
        await open_frame(handler, svc, identity)
        form = handler.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2))
        form.values.update(operation=("allow",), account="The Frame explicitly consents")
        await form.confirm.callback(current(1, 60302))
        assert form.completed
        helper = current(3, 60303)
        await helper.response.defer(ephemeral=True)
        await open_frame(helper, svc, identity)
        extraction = helper.edit_original_response.call_args.kwargs["view"]
        assert not await extraction.interaction_check(current(2))
        token = next(x for x in extraction.fields if x.key == "extractor").options[0][0]
        extraction.values.update(
            operation=("extract",), extractor=(token,), account="The actual helper extracts her"
        )
        await extraction.confirm.callback(current(3, 60304))
        assert extraction.completed

    asyncio.run(run())
    assert (
        not state(game).placements[0].vitals_active
        and state(game).placements[0].mode == "outside_frame"
    )


def test_native_voluntary_exit_reopens_as_owned_cockpit_enter_controls(ledger):
    svc, game = placed(ledger)

    async def run():
        pilot = current(2, 60401)
        await pilot.response.defer(ephemeral=True)
        await open_initial(pilot, svc)
        form = pilot.edit_original_response.call_args.kwargs["view"]
        form.values.update(operation=("exit",), account="I actually leave")
        await form.confirm.callback(current(2, 60402))
        assert form.completed
        await open_initial(pilot, svc)
        reopened = pilot.edit_original_response.call_args.kwargs["view"]
        assert set(dict(next(x for x in reopened.fields if x.key == "operation").options)) == {
            "sit",
            "pilot",
        }
        reopened.values.update(operation=("pilot",), account="I actually pilot again")
        await reopened.confirm.callback(current(2, 60403))
        assert reopened.completed

    asyncio.run(run())
    assert state(game).placements[0].mode == "piloting"


def test_unknown_body_facts_and_new_frame_position_are_reviewed_without_resetting_vessel(ledger):
    svc, game = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        actor = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
        source = str(uuid4())
        canon, original = rules.original_placement(
            canon,
            profiles(c, ledger.campaign_id),
            actor,
            source,
            "Actual unknown original body",
            prior_event="actual-prior-receipt",
        )
        game.event(c, 2, "actual-unknown-body", "m3.synthetic_body", canon, event_id=source)
    data = svc.preview(PLAYER)
    assert data["can_record_unknown"]
    proposal = InitialPlacement(
        actor=actor,
        frame_instance=data["frame_instance"],
        girl_cell=(0, 0),
        frame_cell=(0, 0),
        mode="outside_frame",
        account="Actual newly known facts",
        facts_confirmed=True,
    )
    request = svc.propose(PLAYER, "unknown-physical-proposal", data["game_revision"], proposal)
    decide(svc, request["id"])
    assert state(game).placements[0].vessel_id == original.vessel_id
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].frame_runtime = FrameRuntime(
            id="actual-replacement-frame", generation=2, source_work="actual-compulsory-package"
        )
        game.event(c, 1, "new-assigned-frame", "synthetic.frame", canon)
    data = svc.preview(PLAYER)
    assert data["can_record_unknown"]
    new = proposal.model_copy(
        update={"frame_instance": "actual-replacement-frame", "frame_cell": (2, 0)}
    )
    request = svc.propose(PLAYER, "new-frame-location", data["game_revision"], new)
    decide(svc, request["id"])
    body = state(game).placements[0]
    assert (
        body.vessel_id == original.vessel_id
        and body.girl_cell == (0, 0)
        and body.frame_cell == (2, 0)
    )
    data, enter = command(svc, "pilot")
    with pytest.raises(WorkflowError, match="same known cell"):
        svc.operate(PLAYER, "no-new-frame-teleport", data["game_revision"], enter)


def test_cockpit_history_failure_rolls_back_and_concurrent_retry_is_exactly_once(
    ledger, monkeypatch
):
    svc, game = placed(ledger)
    data, choice = command(svc)
    original = state(game).model_dump_json()
    event = svc.game.event

    def fail(*args, **kwargs):
        event(*args, **kwargs)
        raise RuntimeError("Synthetic post-physical-history failure")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError, match="post-physical-history"):
        svc.operate(PLAYER, "retry-actual-exit", data["game_revision"], choice)
    assert state(game).model_dump_json() == original
    monkeypatch.setattr(svc.game, "event", event)
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(
                lambda _: svc.operate(PLAYER, "retry-actual-exit", data["game_revision"], choice),
                range(2),
            )
        )
    assert results[0] == results[1] and state(game).placements[0].mode == "outside_frame"


def test_separately_represented_core_controls_its_actual_frame_consent(ledger):
    svc, game = placed(ledger)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"physical_frame_voice": "controller_or_handler"}
            )
        }
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].frame_runtime = FrameRuntime(
            id=canon.placements[0].frame_instance,
            generation=1,
            source_work="actual-core-source",
            core_id="actual-linked-core",
        )
        canon.world = canon.world.model_copy(
            update={
                "npcs": canon.world.npcs
                + (
                    Npc(
                        id="actual-linked-core",
                        name="Unrevealed role",
                        jobs=("guard",),
                        detail="Distinct controller of this Core",
                        controller=3,
                        cell=(0, 0),
                    ),
                )
            }
        )
        source = str(uuid4())
        actor = canon.placements[0].actor
        canon = rules.lock_cockpit(
            canon, profiles(c, ledger.campaign_id), actor, source, "The actual linked Frame locks"
        )
        game.event(
            c, 2, "actual-linked-core-lock", "m3.synthetic_core_lock", canon, event_id=source
        )
    identity = state(game).frame_locks[0].id
    with pytest.raises(WorkflowError, match="human voice"):
        respond(svc, identity, viewer=ADMIN)
    respond(svc, identity, viewer=OTHER)
    assert svc.frame(PLAYER, identity)["allowed"]
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"alive": False}) if x.id == "actual-linked-core" else x
                    for x in canon.world.npcs
                )
            }
        )
        game.event(c, 1, "actual-core-death", "synthetic.state", canon)
    assert not svc.frame(PLAYER, identity)["can_voice"]
    with pytest.raises(WorkflowError, match="after its death"):
        respond(svc, identity, viewer=ADMIN)


def test_current_guest_needs_own_frame_consent_and_voice_selects_actual_occupant(ledger):
    svc, game = placed(ledger)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"physical_frame_voice": "controller_or_handler"}
            )
        }
    )
    with ledger.transaction() as c:
        canon = state(game)
        guest = ActorRef(kind="pilot", entity="3", incarnation=canon.sheets["3"].character_id)
        owner = canon.placements[0].actor
        prior, source = str(uuid4()), str(uuid4())
        canon = rules.rescue_to_cockpit(
            canon,
            profiles(c, ledger.campaign_id),
            guest,
            owner,
            prior,
            "The real guest is rescued",
            prior_event="actual-prior-guest-roll",
        )
        game.event(c, 3, "actual-guest-rescue", "m3.synthetic_guest_rescue", canon, event_id=prior)
        canon = rules.lock_cockpit(
            canon,
            profiles(c, ledger.campaign_id),
            owner,
            source,
            "The actual Frame seals with both inside",
        )
        game.event(
            c, 2, "actual-shared-cockpit-lock", "m3.synthetic_shared_lock", canon, event_id=source
        )
    identity = state(game).frame_locks[0].id
    assert svc.frame(OTHER, identity)["subject"] == guest.model_dump(mode="json")
    respond(svc, identity, target=guest)
    assert svc.frame(OTHER, identity)["allowed"] and not svc.frame(PLAYER, identity)["allowed"]
    data, choice = command(svc, viewer=OTHER)
    svc.operate(OTHER, "actual-guest-leaves", data["game_revision"], choice)
    assert state(game).placements[1].mode == "outside_frame"
    assert state(game).placements[0].subsumed
