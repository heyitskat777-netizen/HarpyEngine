"""Real high-result Easy Target participation, without fabricated NPC dice."""

import asyncio
from uuid import uuid4

import sqlalchemy as sa
from test_easy_target import _npc_protection_native, choose, ready, source, validate
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.database import tables as t
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_easy_target import EasyTargetService, prove_protection_cohort


def test_native_cohort_joins_real_npc_protection_without_roll_or_failure_tag(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, mixed=True)
    npc = ActorRef(kind="npc", entity="bystander")
    helper = ActorRef(kind="npc", entity="cohort")
    identity = source(game, worker, gateway, faces=(5, 5), selected=npc)
    work = rules.identity(identity, npc)
    helper_work = rules.identity(identity, helper)
    calls = game.dice.calls
    receipt = game.inspect(PLAYER, identity)["receipt"]

    def submit(actor, values, interaction_id, *, kind="easy_target_child", user=3):
        viewer = ADMIN if user == 1 else OTHER
        row = next(x for x in game.choices(viewer) if x["kind"] == kind + ":" + actor.token)
        asyncio.run(_npc_protection_native(game, user, row, values, interaction_id))

    submit(
        npc,
        dict(
            urge=("protect",),
            context="Guard the actual corridor",
            account="I choose to protect her",
        ),
        99600,
        kind="easy_target_react",
    )
    submit(
        helper,
        dict(urge=("cohort",), primary=(work,), account="I choose to go along with the guard"),
        99610,
        kind="easy_target_react",
    )
    choose(game, OTHER, current_ref(state(game), 3), "pass")
    choose(game, ADMIN, current_ref(state(game), 1), "pass")
    validate(game, npc)
    submit(npc, dict(account="I actually stand guard in the corridor"), 99620)
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    assert not rules.get(state(game), rules.Reaction, work).exemption
    before = state(game)
    submit(
        helper,
        dict(account="PRIVATE_COHORT I actually join the guard and watch the corridor"),
        99630,
    )
    actual = state(game)
    participation = rules.records(actual, rules.ProtectionCohort)[-1]
    assert participation.reaction == helper_work and participation.primary == work
    assert participation.actor == helper and participation.controller == 3
    primary = rules.get(actual, rules.Reaction, work)
    follower = rules.get(actual, rules.Reaction, helper_work)
    assert primary.exemption == helper_work and follower.exemption == work
    assert primary.consequence == follower.consequence == "cohort-exempt"
    assert primary.protection_event and follower.performance_event
    assert not primary.child and not follower.child
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.dice.calls == calls and game.inspect(PLAYER, identity)["receipt"] == receipt
    assert actual.sheets == before.sheets and actual.world == before.world
    assert not controls.view(ADMIN, work)["can_report_failure"]
    assert not EasyTargetService(game).view(OTHER, work)["can_failure_tag"]
    with game.store.engine.connect() as c:
        assert prove_protection_cohort(game, c, actual, participation.id) == participation
        assert "PRIVATE_COHORT" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))


def test_failed_protection_pending_cohort_acknowledges_without_erasing_failure(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, mixed=True)
    npc = ActorRef(kind="npc", entity="bystander")
    helper = ActorRef(kind="npc", entity="cohort")
    identity = source(game, worker, gateway, faces=(5, 5), selected=npc)
    work = rules.identity(identity, npc)
    helper_work = rules.identity(identity, helper)
    calls = game.dice.calls
    receipt = game.inspect(PLAYER, identity)["receipt"]

    def submit(actor, values, interaction_id, *, kind="easy_target_child", user=3):
        viewer = ADMIN if user == 1 else OTHER
        row = next(x for x in game.choices(viewer) if x["kind"] == kind + ":" + actor.token)
        asyncio.run(_npc_protection_native(game, user, row, values, interaction_id))

    submit(
        npc,
        dict(
            urge=("protect",),
            context="Guard the actual corridor",
            account="I choose to protect her",
        ),
        99600,
        kind="easy_target_react",
    )
    submit(
        helper,
        dict(urge=("cohort",), primary=(work,), account="I choose to go along with the guard"),
        99610,
        kind="easy_target_react",
    )
    choose(game, OTHER, current_ref(state(game), 3), "pass")
    choose(game, ADMIN, current_ref(state(game), 1), "pass")
    validate(game, npc)
    submit(npc, dict(account="I actually stand guard in the corridor"), 99620)
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    assert not rules.get(state(game), rules.Reaction, work).exemption
    failure = controls.fail_protection(
        ADMIN,
        str(uuid4()),
        work,
        state(game).revision,
        "The guard tried to keep the corridor clear",
        "Someone actually passed the guard",
    )
    assert controls.view(PLAYER, work)["can_failure_tag"]
    before = state(game)
    submit(helper, dict(account="PRIVATE_MISSED I missed the opportunity before it failed"), 99730)
    actual = state(game)
    acknowledgment = rules.records(actual, rules.ProtectionCohort)[-1]
    assert acknowledgment.outcome == "missed" and acknowledgment.failure == failure["id"]
    primary = rules.get(actual, rules.Reaction, work)
    follower = rules.get(actual, rules.Reaction, helper_work)
    assert primary.failure == failure["id"] and not primary.exemption
    assert not follower.exemption and not follower.performance_event
    assert follower.completed_event and follower.consequence == "protection-already-failed"
    assert controls.view(PLAYER, work)["can_failure_tag"]
    assert actual.sheets == before.sheets and actual.world == before.world
    with game.store.engine.connect() as c:
        assert prove_protection_cohort(game, c, actual, acknowledgment.id) == acknowledgment
    controls.failure_tag(PLAYER, str(uuid4()), work, actual.revision, True, "Failed corridor guard")
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert rules.get(state(game), rules.Reaction, work).consequence == "failure-tag"
    assert game.dice.calls == calls and game.inspect(PLAYER, identity)["receipt"] == receipt
    assert not controls.view(PLAYER, work)["can_failure_tag"]
