"""Earned Dose to ordinary NPC: exact consumed lesson, WorldTags and recipient scene expiry."""

from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_dose_up import native_choice
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_vatgrown_plays import native_choice as learn_choice
from test_vatgrown_plays import ready, sex

from girlframe.engine import m3_dose_up as rules
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_dose_up import DoseUpService, prove
from girlframe.services.m3_learned_plays import prove_consumed
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_earned_once_dose_actual_npc_components_and_expiry(ledger, tmp_path, monkeypatch):
    game, worker, gateway, teacher_controls = ready(
        ledger, tmp_path, monkeypatch, teacher="STIM-BLISSED"
    )
    session, learning_action = sex(game, worker, gateway, teacher_controls, (5, 5))
    original = state(game)
    learn_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(original.sheets["3"].identities[1].id,),
        replacements=(original.sheets["2"].identities[0].id,),
        play=(rules.RULE,),
        account="The actual original teacher teaches Dose Up for one use",
    )
    assert game.inspect(PLAYER, learning_action)["state"] == "complete"
    lesson = vat.records(state(game), vat.LearnedPlay)[-1]
    teacher_controls.send_away(
        OTHER,
        str(uuid4()),
        session,
        state(game).revision,
        "The actual teacher releases the learner after the genuine lesson",
    )
    tick(worker, gateway, 6)
    controls = DoseUpService(ledger, game)
    rolls_before = game.dice.calls

    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="actual-dose-recipient")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("guard",),
            controller=1,
            cell=(0, 0),
            revealed=True,
            detail="Actual ordinary human source recipient",
        ),
    )
    casts = CastService(ActorService(missions))
    cast_change(casts, ADMIN, "join", npc)
    before = state(game)
    with pytest.raises(WorkflowError):
        controls.record_contact(
            PLAYER, str(uuid4()), 900, npc, before.revision, "A name alone is not actual anatomy"
        )
    assert state(game) == before
    BodyFactsService(game).record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        npc,
        "human_npc",
        "Actual witnessed human body and brain",
    )
    assert any(
        x["ref"] == npc.model_dump(mode="json") for x in controls.menu(PLAYER, 900)["targets"]
    )
    contact = controls.record_contact(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "PRIVATE_NPC_VEIN My hand actually reaches this original body's exposed vein here",
    )["id"]
    game.dice.faces = (6, 6)
    before = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            target_actor=npc,
            source_work=contact,
            heat=1,
            context="Actual original recipient dosing",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    native_choice(game, PLAYER, ("quick", "calm"))
    native_choice(game, ADMIN, ("sense",))
    final = state(game)
    with ledger.engine.connect() as c:
        source = prove(game, c, final, action)
        actual_action = game.action(c, action)
        assert actual_action["data"]["learned_play"]["id"] == lesson.id
        assert prove_consumed(game, c, final, actual_action, rules.RULE, source.roll_event)
    assert source.target == npc and source.target_controller == 1
    assert source.total >= 11 and len(source.selections) == 2
    assert source.selections[0].chooser == 2 and source.selections[1].chooser == 1
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert (
        final.sheets["2"].heat == before.sheets["2"].heat - 1
        and game.dice.calls == rolls_before + 1
    )
    drugs = [x for x in rules.records(final, rules.NpcDrugTag) if x.dose == action]
    assert {x.component for x in drugs} == {"quick", "calm", "sense"}
    assert all(x.tag in actor_tags(final, npc) for x in drugs)
    assert not any(x.dose == action for x in rules.records(final, rules.DrugTag))
    assert controls.view(ADMIN, action)["phase"] == "active"
    with pytest.raises(WorkflowError):
        controls.view(OTHER, action)
    tick(worker, gateway, 8)
    for number in (1, 2):
        game.close_scene(ADMIN, str(uuid4()), 900)
        assert (
            len([x for x in rules.records(state(game), rules.SceneEnd) if x.dose == action])
            == number
        )
        if number == 1:
            assert all(x.tag in actor_tags(state(game), npc) for x in drugs)
            game.bind_scene(ADMIN, str(uuid4()), 900)
            for human in (PLAYER, OTHER, ADMIN):
                game.join_scene(human, str(uuid4()), 900)
            cast_change(casts, ADMIN, "join", npc)
    final = state(game)
    assert rules.expired(final, action)
    assert not any(x.id in {d.id for d in drugs} for x in actor_tags(final, npc))
    assert controls.view(ADMIN, action)["phase"] == "expired"
    with ledger.engine.connect() as c:
        assert prove(game, c, final, action) == source
    assert "PRIVATE_NPC_VEIN" not in str(gateway.messages)
