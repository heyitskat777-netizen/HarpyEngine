"""A genuine earned Alpha source preserves actual NPC consent and once-only effects."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_vatgrown_plays import (
    _learn_daily_source,
    _learned_sex_interaction,
    _native_learned_sex_invitation,
    ready,
)

from girlframe.discord_adapter.m2_ui import open_play
from girlframe.discord_adapter.m3_alpha_sex import open_alpha
from girlframe.engine import m3_alpha as broken
from girlframe.engine import m3_alpha_sex as rules
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_alpha_sex import SexService, prove
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_learned_sex import lessons, source_id
from girlframe.services.m3_learned_sex import prove as prove_lesson
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_earned_alpha_npc_decline_fresh_native_contact_broken_tracking_and_once_use(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, vat.BRUTALIZE, rules.RULE),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, rules.RULE)
    learner = current_ref(state(game), PLAYER.user_id)
    assert not has_rule(state(game).sheets["2"], rules.RULE, "ALPHA")
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="earned-alpha-original-counterpart")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Actual counterpart",
            jobs=("guard",),
            controller=ADMIN.user_id,
            detail="PRIVATE_LEARNED_ALPHA_NPC_DETAIL",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_change(CastService(ActorService(missions)), ADMIN, "join", npc)
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

    async def answer_native(link, accept):
        opened = _learned_sex_interaction(ADMIN.user_id)
        await opened.response.defer(ephemeral=True)
        await open_alpha(opened, service)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        selected = "consent:" + link.session
        assert selected in dict(next(x for x in menu.fields if x.key == "action").options)
        menu.values.update(action=(selected,))
        response = _learned_sex_interaction(ADMIN.user_id)
        await menu.confirm.callback(response)
        form = response.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            accept=("yes" if accept else "no",),
            account="PRIVATE_LEARNED_ALPHA_NPC My own independent source answer",
        )
        if accept:
            form.values["npc_contact"] = (
                "Actual original body contact here, outside all enclosures and rides"
            )
        sent = _learned_sex_interaction(ADMIN.user_id)
        await form.confirm.callback(sent)
        assert form.completed, (
            sent.response.events,
            sent.edit_original_response.call_args_list,
        )
        saved = state(game)
        await form.confirm.callback(sent)
        assert state(game) == saved

    declined = _native_learned_sex_invitation(game, lesson, npc)
    asyncio.run(answer_native(declined, False))
    with ledger.engine.connect() as c:
        released = prove_lesson(game, c, state(game), declined.id)
        assert released.released_kind == "declined" and released.roll_event is None
        assert lessons(game, c, state(game), learner, rules.RULE)[0]["id"] == lesson.id
    assert rules.get(state(game), declined.session).npc_contact is None

    link = _native_learned_sex_invitation(game, lesson, npc)
    before = state(game)
    calls, heat = game.dice.calls, before.sheets["2"].heat
    bond = depth(before, learner, npc)
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
    asyncio.run(answer_native(link, True))
    contact = rules.get(state(game), link.session).npc_contact
    assert contact is not None and contact.controller == ADMIN.user_id
    assert contact.target == npc and contact.actor == learner
    assert contact.session == link.session and link.id != declined.id
    game.dice.faces = (3, 4)

    async def perform_native():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_play(opened, game)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert rules.PLAY in dict(next(x for x in form.fields if x.key == "play").options)
        form.values.update(
            play=(rules.PLAY,),
            alpha_sex_source=(link.session,),
            heat=("1",),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="Actual learned source with independently confirmed original NPC contact",
            disposable_heat=("0",),
        )
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, (
            sent.response.events,
            sent.edit_original_response.call_args_list,
        )
        saved = state(game)
        await form.confirm.callback(sent)
        assert state(game) == saved

    asyncio.run(perform_native())
    with ledger.engine.connect() as c:
        action = game.lock(c, 900)["action_id"]
        assert source_id(game.action(c, action)) == link.id
    tick(worker, gateway, 3)
    pass_tags(game)
    actual = state(game)
    value = rules.get(actual, link.session)
    assert value.phase == "complete" and value.condition
    assert any(
        x.id == value.condition and x.source_action == action
        for x in broken.conditions(actual, npc, learner)
    )
    assert depth(actual, learner, npc) == bond + 1
    assert rules.tracking(actual, value)
    assert service.track(PLAYER, link.session)["cell"] == (0, 0)
    assert actual.sheets["2"].heat == heat - 1 and game.dice.calls == calls + 1
    assert next(x for x in actual.world.npcs if x.id == npc.entity).alive
    assert game.inspect(PLAYER, action)["state"] == "complete"
    receipt = game.inspect(PLAYER, action)["receipt"]
    with ledger.engine.connect() as c:
        assert prove(game, c, actual, link.session) == value
        spent = prove_lesson(game, c, actual, link.id)
        assert spent.action == action and spent.roll_event and spent.receipt_sha256
        assert spent.accepted and spent.consent_event == contact.event
        assert spent.released_event is None
        assert not lessons(game, c, actual, learner, rules.RULE)
        assert prove_lesson(game, c, actual, declined.id).released_kind == "declined"
    with pytest.raises(WorkflowError):
        service.view(OTHER, link.session)
    tick(worker, gateway, 8)
    before_reuse = state(game)
    with pytest.raises(WorkflowError):
        service.invite(
            PLAYER,
            str(uuid4()),
            900,
            npc,
            before_reuse.revision,
            "The consumed lesson cannot supply a second source",
            learned_source=lesson.id,
        )
    assert state(game) == before_reuse and game.dice.calls == calls + 1
    with pytest.raises(WorkflowError):
        service.invite(
            PLAYER,
            str(uuid4()),
            900,
            npc,
            before_reuse.revision,
            "The lesson does not supply permanent Alpha ownership",
        )
    assert state(game) == before_reuse
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert service.view(ADMIN, link.session)["phase"] == "complete"
    assert state(game).sheets["2"].girl == "VATGROWN"
    assert not has_rule(state(game).sheets["2"], rules.RULE, "ALPHA")
    assert "PRIVATE_LEARNED_ALPHA_NPC" not in json.dumps(gateway.messages)
