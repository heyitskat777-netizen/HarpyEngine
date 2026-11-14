"""Ordinary introduced NPC minds use actual world source proof, never fake placements."""

from uuid import uuid4

import test_strain_effect_service
from test_ankou import processor
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_off_duty_cycle import activate, prepared
from test_physical_operations import place
from test_strain_service import ready as strain_ready

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ankou import AnkouService, prove_tag
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService


def test_actual_npc_processor_preserves_canonical_source_private_symptoms_and_owner_expiry(
    ledger, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        test_strain_effect_service,
        "ready",
        lambda store, face: strain_ready(store, face=face, frame=rules.FRAME),
    )
    cycle, game, period = prepared(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RELAY, *rules.REQUISITIONS))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    with ledger.transaction() as c:
        canon = place(place(state(game), 2, mode="piloting"), 3, mode="outside_frame")
        canon.sheets["2"].permissions = 30
        canon.sheets["2"].heat = 4
        game.event(c, 1, str(uuid4()), "synthetic.prior_processor_resources_positions", canon)
    cycle.missions.access = Access(ledger)
    actor = current_ref(state(game), 2)
    target = ActorRef(kind="npc", entity="original-processor-npc")
    world = WorldService(MissionService(ledger))
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=target.entity,
            name="PRIVATE_UNREVEALED_PROCESSOR",
            jobs=("guard",),
            controller=1,
            detail="Actual independently controlled living mind",
            cell=(0, 0),
            revealed=False,
        ),
    )
    controls, worker, gateway = AnkouService(game), GameWorker(game), Gateway()
    symptoms = ("Auditory hallucinations", "Vomiting and nausea")
    handler = HandlerPlayService(ledger)
    previous = handler.start(ADMIN, str(uuid4()), state(game).revision, (target,))["id"]
    handler.submit(
        ADMIN,
        str(uuid4()),
        previous,
        state(game).revision,
        "mess",
        Effect(
            kind="tag",
            target=target,
            tag=symptoms[0],
            account="Actual independent earlier source with the same words",
        ),
    )
    prior = next(x for x in actor_tags(state(game), target) if x.id == previous + ":tag")
    with ledger.engine.connect() as c:
        actual = resolve(state(game), target, profiles(c, ledger.campaign_id))
        assert actual.cell == (0, 0) and actual.position_sha256 is None
        original_source = actual.source_sha256
    action = processor(game, worker, gateway, controls, (5, 5))
    answer(game, PLAYER, "ankou_processor_benefits", options=("champion", "eyes", "will"))
    answer(game, PLAYER, "ankou_processor_symptoms", options=symptoms)
    completed = state(game)
    source = rules.get(completed, rules.Processor, action)
    assert source.total >= 11 and source.completed_event and source.symptoms == symptoms
    assert target in source.minds and source.positions[target.token] == original_source
    private_view = controls.view(PLAYER, action)
    assert "PRIVATE_UNREVEALED_PROCESSOR" not in str(private_view)
    assert target.model_dump(mode="json") not in private_view["source"]["minds"]
    uses = [
        x
        for x in rules.records(completed, rules.TagUse)
        if x.source == action and x.kind == "symptom" and x.target == target
    ]
    assert len(uses) == 2 and len({x.id for x in uses}) == 2
    assert all(x.actor == actor and x.event == source.symptoms_event for x in uses)
    tags = [x for x in actor_tags(completed, target) if x.id in {use.tag for use in uses}]
    assert {x.label for x in tags} == set(symptoms)
    assert len(source.tags) == len(set(source.tags))
    assert prior in actor_tags(completed, target)
    for tag in tags:
        assert tag.id == rules.identity(
            "tag", action, target.token, "symptom", source.symptoms_event, tag.label
        )
    with ledger.engine.connect() as c:
        birth = _history(c, game, source.symptoms_event)
        for use in uses:
            assert rules.get(birth, rules.TagUse, use.id) == use
            assert prove_tag(game, c, completed, target, use.tag) == use
    controls.unlink(PLAYER, str(uuid4()), completed.revision, action, "I actually end this link")
    assert all(tag in actor_tags(state(game), target) for tag in tags)
    tick(worker, gateway, 5)
    calls = game.dice.calls
    activate(cycle, game, period)
    final = state(game)
    assert all(rules.get(final, rules.TagUse, use.id).ended_event for use in uses)
    assert not any(x.id in {use.tag for use in uses} for x in actor_tags(final, target))
    assert prior in actor_tags(final, target)
    with ledger.engine.connect() as c:
        assert _history(c, game, source.symptoms_event) == birth
    assert game.dice.calls == calls
