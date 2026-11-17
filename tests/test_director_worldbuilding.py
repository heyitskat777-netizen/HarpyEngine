"""Reviewed world additions commit through native authority, never through proposal prose."""

import json
from dataclasses import replace

import pytest
import sqlalchemy as sa
from rules.m3_policy_scenario import configure_m3_fixture
from rules.test_world import initial
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.worldbuilding import (
    DevelopmentAction,
    FactionAction,
    NpcAction,
    WorldbuildingProposal,
)
from girlframe.database import tables as t
from girlframe.engine.m3_world_development import DevelopmentDraft, Subject, records
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.director_worldbuilding import DirectorWorldbuildingService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def ready(routed):
    observer, context, scene, game, _ = routed
    configure_m3_fixture(observer.store)
    approval = observer.store.policy.m3_approval
    observer.store.policy = observer.store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            ),
        }
    )
    world = WorldService(MissionService(observer.store))
    start = initial()
    world.initialize(
        ADMIN,
        "initialize-world",
        state(game).revision,
        start.board,
        start.locations,
        start.gorgons[0],
    )
    return DirectorWorldbuildingService(context)


def detail(**changes):
    return DevelopmentAction(
        development=DevelopmentDraft(
            **(
                {
                    "key": "barracks-notice",
                    "kind": "detail",
                    "subject": Subject(kind="location", id="base0"),
                    "title": "Inspection notice",
                    "text": "A red inspection tag hangs beside the service panel.",
                }
                | changes
            )
        )
    )


def propose(service, scene, action, key="author", gm=ADMIN):
    _, source = send(
        service.observer, scene, key + ":source", text="GM, frame the maintenance scene."
    )
    request = service.open(gm, key + ":open", scene, source.source_id)
    proposal = WorldbuildingProposal(
        request_id=request["id"],
        action=action,
        cited_evidence=("source", "native"),
        private_reasoning="PRIVATE_WORLD_REASON",
    )
    saved = service.propose(gm, key + ":proposal", scene, request["id"], proposal)
    return request, saved, proposal


def test_native_npc_faction_and_goal_additions_remain_private_and_replay_once(routed):
    service = ready(routed)
    observer, context, scene, game, dice = routed
    sheets = state(game).sheets
    actions = (
        NpcAction(
            npc=Npc(
                id="reviewed-tech",
                name="Nera",
                cell=(0, 0),
                jobs=("mechanic",),
                controller=1,
                detail="PRIVATE_TECH_DETAIL",
            )
        ),
        FactionAction(
            faction=Faction(
                id="reviewed-circle",
                name="Maintenance Circle",
                kind="political",
                cells=((0, 0),),
                leader="reviewed-tech",
            )
        ),
        detail(
            key="tech-goal",
            kind="goal",
            subject=Subject(kind="npc", id="reviewed-tech"),
            text="PRIVATE_TECH_GOAL: preserve the old maintenance recordings.",
        ),
    )
    for index, action in enumerate(actions):
        _, saved, _ = propose(service, scene, action, f"addition:{index}")
        assert service.private(ADMIN, scene, saved["id"])["status"] == "awaiting_gm_review"
        with pytest.raises(WorkflowError):
            service.confirm(ADMIN, f"unreviewed:{index}", scene, saved["id"])
        service.review(
            ADMIN,
            f"review:{index}",
            scene,
            saved["id"],
            "approve",
            "Continuity and ownership reviewed; no forced mechanical result.",
        )
        assert "PRIVATE_WORLD_REASON" not in json.dumps(
            service.owner_review(ADMIN, scene, saved["id"])
        )
        before = state(game).revision
        committed = service.confirm(ADMIN, f"confirm:{index}", scene, saved["id"])
        assert state(game).revision == before + 1
        assert service.confirm(ADMIN, f"confirm:{index}", scene, saved["id"]) == committed
        assert service.confirm(ADMIN, f"another-key:{index}", scene, saved["id"]) == committed
    canon = state(game)
    assert canon.world.npcs[-1].id == "reviewed-tech"
    assert canon.world.factions[-1].id == "reviewed-circle"
    assert len(records(canon)) == 1 and canon.sheets == sheets and dice.calls == 0
    assert not service.pending(ADMIN, scene, gm=True)
    with observer.store.engine.connect() as c:
        handler = observer._authorize_input(c, ADMIN, scene, "handler")[2]
        audit = " ".join(c.scalars(sa.select(t.events.c.payload_json)))
    assert "PRIVATE_TECH" not in context.build(ADMIN, scene, actor=handler).model_dump_json()
    assert "PRIVATE_TECH" not in audit and "PRIVATE_WORLD_REASON" not in audit


def test_actual_world_owner_is_separate_from_authoring_gm(routed):
    service = ready(routed)
    scene = routed[2]
    gm = replace(OTHER, is_administrator=True)
    _, saved, _ = propose(service, scene, detail(), gm=gm)
    service.review(
        gm, "gm-review", scene, saved["id"], "approve", "Source and continuity reviewed."
    )
    with pytest.raises(WorkflowError, match="WORLD_NOT_OWNED"):
        service.confirm(gm, "gm-is-not-world-owner", scene, saved["id"])
    result = service.confirm(ADMIN, "actual-world-owner", scene, saved["id"])
    assert result["canon_committed"]


def test_provider_replay_staleness_and_schema_feedback_do_not_apply_world_effects(routed):
    service = ready(routed)
    observer, _, scene, game, dice = routed
    _, source = send(observer, scene, "source", text="GM, propose a maintenance complication.")
    opened = service.open(ADMIN, "open", scene, source.source_id)
    before = state(game).model_dump_json()

    class FixtureProvider:
        calls = 0

        def propose(self, packet):
            self.calls += 1
            return WorldbuildingProposal(
                request_id=packet.request_id,
                action=detail(
                    kind="complication", text="The inspection queue has two conflicting requests."
                ),
                cited_evidence=("source", "native"),
                private_reasoning="PRIVATE_PROVIDER_REASON",
            )

    provider = FixtureProvider()
    saved = service.generate(ADMIN, "generate", scene, opened["id"], provider)
    assert service.generate(ADMIN, "generate", scene, opened["id"], provider) == saved
    assert provider.calls == 1 and state(game).model_dump_json() == before
    raw = provider.propose(service.packet(ADMIN, scene, opened["id"])).model_dump(mode="json")
    raw["action"]["development"]["damage"] = "PRIVATE_INVALID_EFFECT"
    feedback = service.feedback(ADMIN, scene, opened["id"], raw)
    assert not feedback["valid"] and "PRIVATE_INVALID_EFFECT" not in json.dumps(feedback)
    assert state(game).model_dump_json() == before
    send(observer, scene, "later-source", text="I ask a new question.")
    with pytest.raises(WorkflowError, match="STALE_WORLDBUILDING"):
        service.review(ADMIN, "stale-review", scene, saved["id"], "approve", "Old context changed.")
    assert state(game).model_dump_json() == before and dice.calls == 0


def test_semantically_invalid_prose_can_be_rejected_without_native_mutation(routed):
    service = ready(routed)
    scene, game = routed[2:4]
    _, saved, _ = propose(
        service,
        scene,
        detail(text="A Pilot loses all permissions and is forcibly moved by this description."),
    )
    before = state(game).model_dump_json()
    service.review(
        ADMIN,
        "semantic-reject",
        scene,
        saved["id"],
        "reject",
        "This prose claims personal costs/movement without a native source.",
    )
    with pytest.raises(WorkflowError, match="WORLD_REVIEW_REQUIRED"):
        service.confirm(ADMIN, "no-prose-effects", scene, saved["id"])
    assert state(game).model_dump_json() == before


def test_native_commit_recovers_after_private_finalize_failure_without_duplicate_world_change(
    routed, monkeypatch
):
    service = ready(routed)
    scene, game = routed[2:4]
    _, saved, _ = propose(service, scene, detail())
    service.review(ADMIN, "review", scene, saved["id"], "approve", "Reviewed detail.")
    original = service._save
    failures = []

    def fail_once(c, scene_id, identity, kind, **fields):
        if kind == "worldbuilding_commit" and not failures:
            failures.append(identity)
            raise RuntimeError("Synthetic after-native finalize failure")
        return original(c, scene_id, identity, kind, **fields)

    monkeypatch.setattr(service, "_save", fail_once)
    with pytest.raises(RuntimeError, match="after-native"):
        service.confirm(ADMIN, "confirm", scene, saved["id"])
    assert len(records(state(game))) == 1
    assert (
        service.private(ADMIN, scene, saved["id"])["status"] == "native_committed_recover_receipt"
    )
    assert service.pending(ADMIN, scene, gm=True)[0]["status"] == "native_committed_recover_receipt"
    committed = service.confirm(ADMIN, "confirm", scene, saved["id"])
    assert committed["canon_committed"] and len(records(state(game))) == 1
    assert not service.pending(ADMIN, scene, gm=True)


def test_existing_session_work_remains_readable_without_world_capability(routed):
    observer, context, scene, _, _ = routed
    assert observer.store.policy.m3_approval is None
    assert DirectorSessionService(context).work(PLAYER, scene)["worldbuilding"] == []
    with pytest.raises(WorkflowError):
        DirectorWorldbuildingService(context).pending(replace(ADMIN, guild_id=201), scene)
