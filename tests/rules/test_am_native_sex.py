"""Deferred actual native AM + native AM source; no relabel, borrowed body or duplicate roll."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
import test_m2_game as game_fixture
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, state
from test_mission_service import service
from test_mission_ui import current
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_am_sex import open_am_sex, open_native
from girlframe.engine import m3_am_sex as rules
from girlframe.engine import m3_gender_designation as gender
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import p1_unrolled_sex as unrolled
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.services.m3_access import load_registry
from girlframe.services.m3_am_sex import SexService, prove_native
from girlframe.services.m3_gender_designation import GenderDesignationService
from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService
from girlframe.services.m3_handler_pr import HandlerPRService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import projection
from girlframe.services.p1_unrolled_sex import give
from girlframe.services.p1_unrolled_sex import prove as prove_gift

ledger = ledger_fixture


def _interaction(viewer, number):
    value = current(viewer.user_id, number)
    value.channel_id = 900
    return value


def _native_control(service, viewer, identity, operation, *, number, **values):
    async def run():
        opened = _interaction(viewer, number)
        await opened.response.defer(ephemeral=True)
        await open_native(opened, service, identity)
        control = opened.edit_original_response.call_args.kwargs["view"]
        control.values.update(operation=(operation,))
        selected = _interaction(viewer, number + 1)
        await control.confirm.callback(selected)
        assert control.completed, selected.edit_original_response.call_args_list
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submitted = _interaction(viewer, number + 2)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(service.game)
        await form.confirm.callback(submitted)
        assert state(service.game) == saved

    asyncio.run(run())


def test_actual_native_am_pair_independent_no_roll_scene_animal_gift_and_private_closure(
    ledger, tmp_path, monkeypatch
):
    original_ready, original_selected = game_fixture.ready, game_fixture.selected
    monkeypatch.setattr(
        game_fixture,
        "ready",
        lambda store, girl, frame: original_ready(store, girl, frame, other_girl="AM"),
    )
    # setup_game really saves/reviews/activates Other's matching native AM draft.
    monkeypatch.setattr(
        game_fixture, "selected", lambda girl, frame: original_selected("AM", frame)
    )
    missions, game = service(ledger, girl="AM", frame="JANUS-B")
    assert {x.girl for x in state(game).sheets.values()} == {"AM"}
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE, gender.RULE, ordinary.RULE))
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"world", "playbooks"}}
            )
        }
    )
    # MissionService was created before this scoped source registry was reviewed.
    missions.access.registry = load_registry()
    world = initial()
    WorldService(missions).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    physical = PhysicalService(ledger)
    for viewer in (PLAYER, OTHER):
        preview = physical.preview(viewer)
        proposed = physical.propose(
            viewer,
            str(uuid4()),
            preview["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(preview["actor"]),
                frame_instance=preview["frame_instance"],
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="outside_frame",
                account="My actual original AM body is outside its parked Frame",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN,
            str(uuid4()),
            proposed["id"],
            1,
            "accept",
            "The actual Handler confirms the existing original bodies and positions",
        )
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)

    # The actual printed Award/legal designation source creates the owed-gift consumer.
    HandlerOrdinaryService(ledger).record_session(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "Actual native AM Session",
        "The original facilitator starts this actual Session",
    )
    pr = HandlerPRService(ledger)
    feature = pr.plan(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "Actual Foundation feature",
        "The actual AM participates in a real Foundation feature",
        (actor,),
    )["id"]
    pr.activity(
        ADMIN,
        str(uuid4()),
        feature,
        state(game).revision,
        "I actually host this feature",
        hosting=True,
    )
    pr.activity(
        PLAYER,
        str(uuid4()),
        feature,
        state(game).revision,
        "My actual AM takes part in the feature",
    )
    pr.submit_result(
        ADMIN, str(uuid4()), feature, state(game).revision, "The actual feature was performed"
    )
    award = pr.resolve(
        ADMIN,
        str(uuid4()),
        feature,
        state(game).revision,
        True,
        "The actual source adjudicator judges the feature successful",
    )["award"]
    law = GenderDesignationService(ledger)
    acquisition = law.buy(
        ADMIN,
        str(uuid4()),
        award,
        state(game).revision,
        "Spend this real held Award on Gender Designation Request",
    )["id"]
    law.designate(
        ADMIN,
        str(uuid4()),
        acquisition,
        state(game).revision,
        (actor,),
        "animal",
        "Actual legal designation of this unchanged native AM",
    )
    assert gender.current(state(game), actor).gender == "animal"
    controls = SexService(game)
    baseline = state(game)
    with ledger.engine.connect() as c:
        actions = c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"]))
        receipts = c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_receipts"]))
    calls = game.dice.calls

    async def invite():
        opened = _interaction(PLAYER, 993000)
        await opened.response.defer(ephemeral=True)
        await open_am_sex(opened, controls)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values.update(source=("native",))
        selected = _interaction(PLAYER, 993001)
        await menu.confirm.callback(selected)
        assert menu.completed, selected.edit_original_response.call_args_list
        entry = selected.edit_original_response.call_args.kwargs["view"]
        entry.values.update(source=("invite",))
        requested = _interaction(PLAYER, 993002)
        await entry.confirm.callback(requested)
        assert entry.completed, requested.edit_original_response.call_args_list
        form = requested.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(_interaction(OTHER, 993003))
        assert "lesson" not in {x.key for x in form.fields}
        form.values.update(
            target=(target.token,),
            account=(
                "PRIVATE_NATIVE_AM actual original voluntary invitation; no circuit manipulation"
            ),
        )
        sent = _interaction(PLAYER, 993004)
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(sent)
        assert state(game) == saved

    asyncio.run(invite())
    source = next(x for x in rules.sources(state(game)) if x.native)
    assert source.actor == actor and source.target == target and source.lesson is None
    assert source.phase == "invited" and not source.used_event and not source.consent_event
    fact = next(
        x for x in state(game).facts if x.get("kind") == "native_am_source" and x["id"] == source.id
    )
    assert "lesson" not in json.loads(fact["body"])
    assert state(game).sheets == baseline.sheets
    assert not controls.view_native(PLAYER, source.id)["can_perform"]
    with ledger.engine.connect() as c:
        assert projection(game, c, source.id)["state"] == "not_activated"
    with pytest.raises(WorkflowError):
        controls.view_native(ADMIN, source.id)
    unchanged = state(game)
    with pytest.raises(WorkflowError):
        controls.confirm(
            PLAYER,
            str(uuid4()),
            source.id,
            unchanged.revision,
            True,
            "I cannot supply the other person's answer",
        )
    assert state(game) == unchanged
    _native_control(
        controls,
        OTHER,
        source.id,
        "confirm",
        number=993010,
        accept=("yes",),
        account="PRIVATE_OTHER_AM my actual independent source confirmation",
    )
    assert len(rules.consents(state(game))) == 1
    _native_control(
        controls,
        PLAYER,
        source.id,
        "perform",
        number=993020,
        circuits=("no",),
        account=(
            "PRIVATE_NATIVE_AM I actually performed my part of this scene without touching circuits"
        ),
    )
    assert rules.source(state(game), source.id).phase == "active"
    assert len(rules.performances(state(game))) == 1
    _native_control(
        controls,
        OTHER,
        source.id,
        "perform",
        number=993030,
        circuits=("no",),
        account=(
            "PRIVATE_OTHER_AM I independently record my actual performed participation "
            "without circuit manipulation"
        ),
    )
    performed = state(game)
    assert rules.source(performed, source.id).phase == "effects"
    gift = next(x for x in unrolled.gifts(performed) if x.source == source.id)
    assert gift.source_kind == "native_am" and gift.animal == actor and gift.target == target
    assert gift.tag is None and not rules.source(performed, source.id).completed_event
    gateway = Gateway()
    original_permissions = copy.deepcopy(gateway.values)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, source.id)["state"] == "held"
    unchanged = state(game)
    with pytest.raises(WorkflowError):
        give(
            game,
            OTHER,
            str(uuid4()),
            gift.id,
            unchanged.revision,
            "Cannot author the actual Animal's Tag",
        )
    assert state(game) == unchanged
    _native_control(
        controls,
        PLAYER,
        source.id,
        "gift",
        number=993040,
        gift=(gift.id,),
        tag="PRIVATE_NATIVE_GIFT the real Animal's owned Tag",
    )
    final = state(game)
    ended = rules.source(final, source.id)
    assert ended.phase == "complete" and ended.completed_event and ended.counterpart_action is None
    assert len(rules.performances(final)) == 2 and game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert prove_native(game, c, final, source.id) == ended
        given = prove_gift(game, c, final, gift.id)
        assert given.tag and given.source_kind == "native_am"
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"])) == actions
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_receipts"])) == receipts
        for event in (ended.event, ended.consent_event, ended.used_event, ended.completed_event):
            audit = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == ledger.campaign_id, t.events.c.id == event
                    )
                )
                .mappings()
                .one()
            )
            assert audit["kind"].startswith("m3.native_am_")
        assert (
            c.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == ended.consent_event))
            == "3"
        )
    for uid in ("2", "3"):
        before, after = baseline.sheets[uid], final.sheets[uid]
        assert (after.heat, after.permissions, after.identities, after.assets) == (
            before.heat,
            before.permissions,
            before.identities,
            before.assets,
        )
        assert (
            getattr(after.girl_runtime, "learned_plays", ())
            == getattr(before.girl_runtime, "learned_plays", ())
            == ()
        )
    assert (
        final.placements == baseline.placements
        and final.neural_connections == baseline.neural_connections
    )
    assert not any(x.get("kind", "").startswith("learned_am_") for x in final.facts)
    tag = next(x for x in final.sheets["3"].tags if x.id == given.tag)
    assert tag.giver_actor == actor and tag.giver == PLAYER.user_id
    assert controls.view_native(OTHER, source.id)["body"]["phase"] == "complete"
    with pytest.raises(WorkflowError):
        controls.view_native(ADMIN, source.id)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    assert gateway.values == original_permissions
    with ledger.engine.connect() as c:
        assert projection(game, c, source.id)["state"] == "closed"
