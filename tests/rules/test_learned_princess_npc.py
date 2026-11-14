"""Actual earned Princess NPC favour/refusal and exact once-use Link."""

from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_vatgrown_plays import _learn_daily_source, ready

from girlframe.engine import m3_princess_sex as rules
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_learned_sex import lessons
from girlframe.services.m3_learned_sex import prove as prove_link
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_princess_sex import SexService, prove
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_earned_princess_npc_favour_and_once_use(ledger, tmp_path, monkeypatch):
    game, worker, gateway, teacher = ready(ledger, tmp_path, monkeypatch, teacher="PRINCESS")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, vat.BRUTALIZE, rules.RULE),
    )
    lesson = _learn_daily_source(game, worker, gateway, teacher, rules.RULE)
    service = SexService(game)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="original-oldgen-counterpart")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("guard",),
            controller=1,
            detail="PRIVATE_OLDGEN_NPC_DETAIL",
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
        "I witness this actual original ordinary civilian's human body and brain",
    )
    assert any(
        x["ref"] == npc.model_dump(mode="json") for x in service.menu(PLAYER, 900)["targets"]
    )
    identity = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "PRIVATE_LEARNED_NPC_SOURCE Actual voluntary original encounter",
        learned_source=lesson.id,
    )["id"]
    before = state(game)
    with pytest.raises(WorkflowError):
        service.confirm(OTHER, str(uuid4()), identity, before.revision, True, "Not my NPC")
    assert state(game) == before
    with pytest.raises(WorkflowError, match="Attest actual physical contact"):
        service.confirm(
            ADMIN,
            str(uuid4()),
            identity,
            before.revision,
            True,
            "Consent alone is not spatial evidence",
        )
    assert state(game) == before
    service.confirm(
        ADMIN,
        str(uuid4()),
        identity,
        before.revision,
        True,
        "Actual original NPC controller confirms voluntary interaction",
        npc_contact_account="Actual original body contact here, outside all enclosures and rides",
    )

    def perform(identity, faces):
        game.dice = Dice(faces)
        action = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play=rules.PLAY,
                source_work=identity,
                target_actor=npc,
                heat=0,
                context="Actual confirmed original NPC interaction",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        return action

    action = perform(identity, (4, 4))
    answer(game, PLAYER, "princess_sex_favour", text="Please deliver the actual note")
    answer(
        game,
        ADMIN,
        "princess_sex_favour_reply",
        options=("refuse",),
        text="The actual NPC refuses this favour",
    )
    answer(
        game, PLAYER, "princess_sex_optional_tag", options=("give",), text="Actual refused favour"
    )
    final = state(game)
    value = rules.get(final, identity)
    assert value.response == "refuse" and value.phase == "complete"
    tag = next(x for x in actor_tags(final, npc) if x.id == value.tag)
    assert tag.giver_entity == current_ref(final, 2).model_dump_json()
    assert game.inspect(PLAYER, action)["state"] == "complete"
    with ledger.engine.connect() as c:
        assert prove(game, c, final, identity) == value
    assert value.learned_source is not None
    with ledger.engine.connect() as c:
        link = prove_link(game, c, final, value.learned_source)
        assert link.lesson == lesson.id and link.actor == value.actor and link.target == npc
        assert link.action == action and link.roll_event and link.receipt_sha256
        assert link.accepted and link.consent_event == value.consent_event
        assert link.released_event is None
        assert not lessons(game, c, final, value.actor, rules.RULE)
    assert final.sheets["2"].girl == "VATGROWN"
    assert not has_rule(final.sheets["2"], rules.RULE, "PRINCESS")
    tick(worker, gateway, 8)
    before = state(game)
    with pytest.raises(WorkflowError):
        service.invite(
            PLAYER,
            str(uuid4()),
            900,
            npc,
            before.revision,
            "Cannot reuse the spent lesson",
            learned_source=lesson.id,
        )
    assert state(game) == before
    with pytest.raises(WorkflowError):
        service.invite(
            PLAYER, str(uuid4()), 900, npc, before.revision, "Cannot invent permanent ownership"
        )
    assert state(game) == before
    assert "PRIVATE_OLDGEN_NPC_DETAIL" not in repr(gateway.messages)
