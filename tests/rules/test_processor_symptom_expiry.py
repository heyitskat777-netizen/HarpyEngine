"""Real Processor symptoms follow source timing, moved Tags and original career endings."""

from uuid import uuid4

import pytest
import test_m2_game as game_fixture
import test_strain_effect_service
from test_ankou import processor
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_off_duty_cycle import activate, prepared
from test_physical_operations import place
from test_retirement import retire
from test_strain_service import ready as strain_ready

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_retirement import RetirementService
from girlframe.services.m3_world import WorldService


@pytest.mark.parametrize("aftermath", ("original", "moved", "retired", "npc"))
def test_actual_processor_symptoms_wait_for_source_ankou_off_duty_and_keep_other_tags(
    ledger, tmp_path, monkeypatch, aftermath
):
    original_ready, original_selected = game_fixture.ready, game_fixture.selected
    monkeypatch.setattr(
        game_fixture,
        "ready",
        lambda *a, **kw: original_ready(*a, **(kw | {"other_frame": rules.FRAME})),
    )
    monkeypatch.setattr(
        game_fixture, "selected", lambda girl, frame: original_selected(girl, rules.FRAME)
    )
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
        canon = place(place(state(game), 2, mode="piloting"), 3, mode="piloting")
        for uid in ("2", "3"):
            canon.sheets[uid].permissions = 30
        canon.sheets["2"].heat = 4
        game.event(c, 1, str(uuid4()), "synthetic.prior_processor_resources_positions", canon)
    cycle.missions.access = Access(ledger)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    controls, worker, gateway = AnkouService(game), GameWorker(game), Gateway()
    symptom = "Crippling migraines and headaches"
    handler = HandlerPlayService(ledger)
    original = handler.start(ADMIN, str(uuid4()), state(game).revision, (target,))["id"]
    handler.submit(
        ADMIN,
        str(uuid4()),
        original,
        state(game).revision,
        "mess",
        Effect(
            kind="tag",
            target=target,
            tag=symptom,
            account="A distinct actual earlier source with the same words",
        ),
    )
    prior = next(x for x in actor_tags(state(game), target) if x.id == original + ":tag")
    if aftermath in ("moved", "npc"):
        controls.buy(
            OTHER,
            str(uuid4()),
            state(game).revision,
            rules.PULSE,
            "I actually buy my own original Amygdala Pulse",
        )
    action = processor(game, worker, gateway, controls, (1, 1))
    answer(game, PLAYER, "ankou_processor_benefits", options=("champion",))
    answer(game, PLAYER, "ankou_processor_symptoms", options=(symptom,))
    source = rules.get(state(game), rules.Processor, action)
    assert target in source.minds and source.completed_event
    use = next(
        x
        for x in rules.records(state(game), rules.TagUse)
        if x.source == action and x.target == target and x.kind == "symptom"
    )
    assert use.actor == actor and use.tag != prior.id
    controls.unlink(PLAYER, str(uuid4()), state(game).revision, action, "I end the actual link")
    assert any(x.id == use.tag for x in actor_tags(state(game), target))
    tick(worker, gateway, 5)
    destination = target
    if aftermath == "npc":
        destination = ActorRef(kind="npc", entity="actual-symptom-pulse-opponent")
        missions = MissionService(ledger)
        WorldService(missions).npc(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            Npc(
                id=destination.entity,
                name="Actual Symptom Recipient",
                jobs=("guard",),
                cell=(0, 0),
                controller=ADMIN.user_id,
                revealed=True,
                detail="The actual opposing NPC who receives the original symptom Tag",
            ),
        )
        change(CastService(ActorService(missions)), ADMIN, "join", destination)
    if aftermath in ("moved", "npc"):
        game.dice.faces = (4, 4)
        moved_action = game.begin(
            OTHER,
            str(uuid4()),
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="engage",
                target_actor=destination if aftermath == "npc" else actor,
                trigger_confirmed=True,
                heat=0,
                piloting=True,
                context="I engage the actual original opposing pilot",
                ankou_pulse=use.tag,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        if game.inspect(OTHER, moved_action)["receipt"] is None:
            game.roll(OTHER, str(uuid4()), moved_action)
        pass_tags(game)
        destination = destination if aftermath == "npc" else actor
        assert any(x.id == use.tag for x in actor_tags(state(game), destination))
        assert not any(x.id == use.tag for x in actor_tags(state(game), target))
        asset = next(x.id for x in state(game).sheets["3"].assets if not x.damaged)
        answer(
            game,
            OTHER,
            "engage_maneuvers",
            options=("cover", "advance"),
            fields={"cover": asset, "advance": asset},
            text="My actual Frame advances behind cover",
        )
        tick(worker, gateway, 5)
    archive = None
    if aftermath == "retired":
        retire(RetirementService(game), viewer=OTHER, key=str(uuid4()))
        archive = next(x for x in state(game).career_archives if x.actor == target)
        assert "3" not in state(game).sheets
    before, calls = state(game), game.dice.calls
    activate(cycle, game, period)
    after = state(game)
    assert rules.get(after, rules.TagUse, use.id).ended_event
    if archive is None:
        assert not any(x.id == use.tag for x in actor_tags(after, destination))
        assert prior in actor_tags(after, target)
    else:
        assert archive in after.career_archives
    assert rules.get(before, rules.TagUse, use.id).ended_event is None
    champion = next(
        x
        for x in rules.records(before, rules.TagUse)
        if x.source == action and x.kind == "champion"
    )
    assert champion.ended_event  # Actual unlink already ended this distinct linked benefit.
    assert rules.get(after, rules.TagUse, champion.id) == champion
    assert game.dice.calls == calls
