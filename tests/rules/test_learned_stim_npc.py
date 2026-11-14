"""A real earned Stim lesson keeps original NPC contact, consumption and drug lifetime."""

import json
from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_stim_sex import choose
from test_vatgrown_plays import (
    _learn_daily_source,
    _native_learned_sex_card,
    _native_learned_sex_invitation,
    ready,
)

from girlframe.discord_adapter.m3_stim_sex import open_stim
from girlframe.engine import m3_stim_sex as rules
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_learned_sex import lessons
from girlframe.services.m3_learned_sex import prove as prove_lesson
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_stim_sex import SexService, _drug, prove, prove_effect
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_earned_stim_npc_decline_fresh_contact_once_only_drug_and_actual_expiry(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="STIM-BLISSED")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            vat.EXPERIMENT,
            vat.INVESTMENT,
            vat.SEX,
            vat.BRUTALIZE,
            "girl.stim-blissed.dose-up",
            rules.RULE,
        ),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, rules.RULE)
    learner = current_ref(state(game), PLAYER.user_id)
    assert not has_rule(state(game).sheets["2"], rules.RULE, "STIM-BLISSED")
    assert not rules.records(state(game), rules.Drug)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    cast = CastService(ActorService(missions))
    npc = ActorRef(kind="npc", entity="earned-stim-original-counterpart")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Actual counterpart",
            jobs=("guard",),
            controller=ADMIN.user_id,
            detail="PRIVATE_LEARNED_STIM_NPC_DETAIL",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_change(cast, ADMIN, "join", npc)
    BodyFactsService(game).record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        npc,
        "human_npc",
        "I witness this actual original ordinary civilian's body and brain",
    )
    service = SexService(game)
    declined = _native_learned_sex_invitation(game, lesson, npc)
    _native_learned_sex_card(
        game,
        service,
        open_stim,
        declined.session,
        ADMIN,
        accept=("no",),
        account="PRIVATE_LEARNED_STIM_NPC I decline this one source",
    )
    with ledger.engine.connect() as c:
        assert prove_lesson(game, c, state(game), declined.id).released_kind == "declined"
        assert lessons(game, c, state(game), learner, rules.RULE)[0]["id"] == lesson.id

    link = _native_learned_sex_invitation(game, lesson, npc)
    before = state(game)
    calls, heat = game.dice.calls, before.sheets["2"].heat
    with pytest.raises(WorkflowError):
        service.respond(OTHER, str(uuid4()), link.session, before.revision, True, "Not my NPC")
    assert state(game) == before and game.dice.calls == calls
    with pytest.raises(WorkflowError, match="Attest actual physical contact"):
        service.respond(
            ADMIN,
            str(uuid4()),
            link.session,
            before.revision,
            True,
            "Consent alone does not establish actual contact",
        )
    assert state(game) == before and game.dice.calls == calls
    _native_learned_sex_card(
        game,
        service,
        open_stim,
        link.session,
        ADMIN,
        accept=("yes",),
        account="PRIVATE_LEARNED_STIM_NPC My own source confirmation",
        npc_contact="Actual original body contact here, outside all enclosures and rides",
    )
    contact = rules.get(state(game), link.session).npc_contact
    assert contact is not None and contact.controller == ADMIN.user_id
    assert contact.target == npc and contact.actor == learner
    game.dice.faces = (3, 4)
    _native_learned_sex_card(
        game,
        service,
        open_stim,
        link.session,
        PLAYER,
        heat=("1",),
        gain=("0",),
        disposable=("0",),
        account="Actual learned source with separately confirmed original NPC contact",
    )
    with ledger.engine.connect() as c:
        action = game.lock(c, 900)["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    choose(game, PLAYER, "stim_sex_drug", ("calm",), native=True)
    before_unsupported = state(game)
    with pytest.raises(WorkflowError, match="human adjudication"):
        choose(game, PLAYER, "stim_sex_effects", ("orders",))
    assert state(game) == before_unsupported
    assert game.inspect(PLAYER, action)["state"] != "complete"
    choose(game, PLAYER, "stim_sex_effects", ("helpless",), native=True)
    actual = state(game)
    drug = rules.records(actual, rules.Drug)[-1]
    effect = rules.records(actual, rules.Effect)[-1]
    assert drug.giver == learner and drug.target == npc and drug.session == link.session
    assert drug.action == action and drug.tag in actor_tags(actual, npc)
    assert effect.giver == learner and effect.target == npc and effect.drug == drug.id
    assert is_helpless(actual, npc) and not is_helpless(actual, learner)
    assert actual.sheets["2"].heat == heat - 1 and game.dice.calls == calls + 1
    assert game.inspect(PLAYER, action)["state"] == "complete"
    with ledger.engine.connect() as c:
        assert prove_lesson(game, c, actual, link.id).roll_event
        assert not lessons(game, c, actual, learner, rules.RULE)
        assert _drug(game, c, actual, drug.id) == drug
        assert prove_effect(game, c, actual, effect.id) == effect
    with pytest.raises(WorkflowError):
        service.view(OTHER, link.session)
    with pytest.raises(WorkflowError):
        service.invite(
            PLAYER,
            str(uuid4()),
            900,
            npc,
            actual.revision,
            "The consumed lesson cannot supply a second source",
            learned_source=lesson.id,
        )
    assert state(game) == actual and game.dice.calls == calls + 1
    tick(worker, gateway, 8)
    game.close_scene(ADMIN, str(uuid4()), 900)
    assert not rules.expired(state(game), drug.id) and is_helpless(state(game), npc)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    cast_change(cast, ADMIN, "join", npc)
    game.close_scene(ADMIN, str(uuid4()), 900)
    actual = state(game)
    assert rules.expired(actual, drug.id) and not is_helpless(actual, npc)
    assert not any(x.id == drug.id for x in actor_tags(actual, npc))
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == calls + 1
    assert service.view(PLAYER, link.session)["drugs"][0]["expired"]
    with ledger.engine.connect() as c:
        assert prove_lesson(game, c, actual, link.id).action == action
        assert prove_lesson(game, c, actual, declined.id).released_kind == "declined"
        assert _drug(game, c, actual, drug.id) == drug
        assert prove_effect(game, c, actual, effect.id) == effect
        assert prove(game, c, actual, link.session).phase == "complete"
    assert actual.sheets["2"].girl == "VATGROWN"
    assert not has_rule(actual.sheets["2"], rules.RULE, "STIM-BLISSED")
    assert not has_rule(actual.sheets["2"], "girl.stim-blissed.dose-up", "STIM-BLISSED")
    assert "PRIVATE_LEARNED_STIM_NPC" not in json.dumps(gateway.messages)
