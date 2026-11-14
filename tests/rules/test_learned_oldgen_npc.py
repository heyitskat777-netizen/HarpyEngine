"""A genuine earned Oldgen source preserves actual NPC consent and once-only effects."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_oldgen_sex import native_choice
from test_vatgrown_plays import (
    _learn_daily_source,
    _learned_sex_interaction,
    _native_learned_sex_invitation,
    ready,
)

from girlframe.discord_adapter.m3_oldgen_sex import open_oldgen_sex
from girlframe.engine import m3_oldgen as maxims
from girlframe.engine import m3_oldgen_sex as rules
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_learned_sex import lessons, source_id
from girlframe.services.m3_learned_sex import prove as prove_lesson
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_oldgen_sex import OldgenSexService, prove, prove_effect
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_earned_oldgen_npc_decline_fresh_native_contact_tag_bond_and_once_use(
    ledger, tmp_path, monkeypatch
):
    # Prior body/world/resources and scoped approval are synthetic setup. The lesson,
    # invitations, contact, actual roll and effects below use real services/UI.
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="OLDGEN")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, vat.BRUTALIZE, rules.RULE),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, rules.RULE)
    learner = current_ref(state(game), PLAYER.user_id)
    assert not has_rule(state(game).sheets["2"], rules.RULE, "OLDGEN")
    assert not maxims.base_maxims(state(game), PLAYER.user_id)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="earned-oldgen-original-counterpart")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Actual counterpart",
            jobs=("guard",),
            controller=ADMIN.user_id,
            detail="PRIVATE_LEARNED_OLDGEN_NPC_DETAIL",
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
    service = OldgenSexService(game)

    async def answer_native(link, accept):
        opened = _learned_sex_interaction(ADMIN.user_id)
        await opened.response.defer(ephemeral=True)
        await open_oldgen_sex(opened, service)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        selected = link.session
        assert selected in dict(next(x for x in menu.fields if x.key == "action").options)
        menu.values.update(action=(selected,))
        response = _learned_sex_interaction(ADMIN.user_id)
        await menu.confirm.callback(response)
        form = response.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            accept=("yes" if accept else "no",),
            account="PRIVATE_LEARNED_OLDGEN_NPC My own independent source answer",
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

    # The owner can also release a never-accepted NPC invitation without invented contact.
    unused = _native_learned_sex_invitation(game, lesson, npc)
    before_release = state(game)
    calls_before_release = game.dice.calls
    service.withdraw(PLAYER, str(uuid4()), unused.session, before_release.revision)
    assert service.view(ADMIN, unused.session)["phase"] == "withdrawn"
    assert rules.get(state(game), unused.session).npc_contact is None
    assert state(game).sheets["2"] == before_release.sheets["2"]
    assert game.dice.calls == calls_before_release
    with ledger.engine.connect() as c:
        withdrawn = prove_lesson(game, c, state(game), unused.id)
        assert withdrawn.released_kind == "withdrawn" and withdrawn.consent_event is None
        assert lessons(game, c, state(game), learner, rules.RULE)[0]["id"] == lesson.id

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
        await open_oldgen_sex(opened, service, link.session)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert {x.key for x in form.fields} == {"heat", "account"}
        form.values.update(
            heat=("1",),
            account="Actual learned source with independently confirmed original NPC contact",
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
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "oldgen_sex_effects")
    assert game.decision(PLAYER, row["id"])["detail"]["unsupported_status"]
    pending = state(game)
    with pytest.raises(WorkflowError, match="UNSUPPORTED_NPC_STATUS"):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("tag", "status"), fields={"tag": "Never committed"}),
        )
    assert state(game) == pending and not actor_tags(state(game), npc)
    native_choice(
        game,
        PLAYER,
        "oldgen_sex_effects",
        ("tag", "bond"),
        fields={"tag": "Actual earned-source NPC Tag"},
    )
    actual = state(game)
    value = rules.get(actual, link.session)
    assert value.phase == "complete" and value.tier == "mid" and value.completed_event
    assert depth(actual, learner, npc) == bond + 1
    effects = [x for x in rules.records(actual, rules.Effect) if x.session == link.session]
    assert {x.kind for x in effects} == {"tag", "bond"}
    tag = next(x for x in effects if x.kind == "tag")
    assert tag.tag is None and tag.npc_tag in actor_tags(actual, npc)
    assert ActorRef.model_validate_json(tag.npc_tag.giver_entity) == learner
    assert actual.sheets["2"].heat == heat - 1 and game.dice.calls == calls + 1
    assert next(x for x in actual.world.npcs if x.id == npc.entity).alive
    assert game.inspect(PLAYER, action)["state"] == "complete"
    receipt = game.inspect(PLAYER, action)["receipt"]
    with ledger.engine.connect() as c:
        assert prove(game, c, actual, link.session) == value
        for effect in effects:
            assert prove_effect(game, c, actual, effect.id) == effect
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
            "The lesson does not supply permanent Oldgen ownership",
        )
    assert state(game) == before_reuse
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert service.view(ADMIN, link.session)["phase"] == "complete"
    assert state(game).sheets["2"].girl == "VATGROWN"
    assert not has_rule(state(game).sheets["2"], rules.RULE, "OLDGEN")
    assert not maxims.base_maxims(state(game), PLAYER.user_id)
    assert "PRIVATE_LEARNED_OLDGEN_NPC" not in json.dumps(gateway.messages)
