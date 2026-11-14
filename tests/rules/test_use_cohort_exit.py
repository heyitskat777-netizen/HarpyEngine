"""Owned nonparticipation never fabricates an exemption or blocks actual NPC completion."""

import asyncio

import pytest
from test_easy_target import _npc_protection_native, choose, ready, source, validate
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_easy_target import EasyTargetService, prove_use_cohort
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("participate", [True, False])
def test_native_multiple_cohorts_decline_and_miss_use(ledger, tmp_path, monkeypatch, participate):
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch, mixed=True)
    npc, helper = (ActorRef(kind="npc", entity=x) for x in ("bystander", "cohort"))
    identity = source(game, worker, gateway, faces=(5, 5), selected=npc)
    work = rules.identity(identity, npc)
    early, late = current_ref(state(game), 3), current_ref(state(game), 1)

    def row(viewer, actor, kind="easy_target_child"):
        return next(x for x in game.choices(viewer) if x["kind"] == kind + ":" + actor.token)

    def submit(viewer, actor, values, number, kind="easy_target_child"):
        asyncio.run(
            _npc_protection_native(game, viewer.user_id, row(viewer, actor, kind), values, number)
        )

    submit(
        OTHER,
        npc,
        dict(
            urge=("use",),
            context="Ordinary rehearsal without a Play trigger",
            account="I use her as my audience",
        ),
        99800,
        "easy_target_react",
    )
    for viewer, actor in ((OTHER, helper), (OTHER, early), (ADMIN, late)):
        choose(game, viewer, actor, "cohort", primary=work)
    validate(game, npc)
    before = state(game)
    calls = game.dice.calls
    receipt = game.inspect(PLAYER, identity)["receipt"]
    submit(
        OTHER,
        helper,
        dict(
            outcome=("participate" if participate else "decline",),
            account="My own actual rehearsal participation decision",
        ),
        99810,
    )
    submit(OTHER, early, dict(outcome=("decline",), account="I decline to go along"), 99820)
    declined = rules.get(state(game), rules.Reaction, rules.identity(identity, early))
    assert declined.completed_event and not declined.exemption and not declined.performance_event
    late_choice = row(ADMIN, late)
    submit(OTHER, npc, dict(account="My actual rehearsal is now finished"), 99830)
    finished = state(game)
    primary = rules.get(finished, rules.Reaction, work)
    pending = rules.get(finished, rules.Reaction, rules.identity(identity, late))
    assert primary.performance_event and not pending.completed_event and not pending.exemption
    assert rules.get(finished, rules.Reaction, declined.id) == declined
    assert len(rules.records(finished, rules.NpcUse)) == 1
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    bonds = [x for x in game.choices(PLAYER) if x["kind"].startswith("easy_target_bond")]
    assert bool(bonds) is not participate
    assert bool(primary.exemption) is participate
    # A stale pre-completion form cannot retroactively participate or decline.
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            "stale-cohort-participation",
            late_choice["id"],
            late_choice["revision"],
            ChoiceAnswer(options=("participate",), text="Too late to participate"),
        )
    submit(
        ADMIN,
        late,
        dict(outcome=("missed",), account="I did not participate before the rehearsal finished"),
        99840,
    )
    after = state(game)
    missed = rules.get(after, rules.Reaction, pending.id)
    assert missed.completed_event and missed.consequence == "use-cohort-missed"
    assert not missed.exemption and not missed.performance_event
    assert rules.get(after, rules.Reaction, work) == primary
    if not participate:
        assert row(PLAYER, npc, "easy_target_bond")["id"] == bonds[0]["id"]
        submit(
            PLAYER,
            npc,
            dict(yes=("no",), account="I keep my Bond unchanged"),
            99850,
            "easy_target_bond",
        )
    actual = state(game)
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.dice.calls == calls and game.inspect(PLAYER, identity)["receipt"] == receipt
    assert actual.sheets == before.sheets and actual.world == before.world
    assert depth(actual, current_ref(actual, 2), npc) == depth(before, current_ref(before, 2), npc)
    assert len(rules.records(actual, rules.UseCohort)) == 3
    with game.store.engine.connect() as c:
        for outcome in rules.records(actual, rules.UseCohort):
            assert prove_use_cohort(game, c, actual, outcome.id) == outcome
    saved = EasyTargetService(game).view(ADMIN, pending.id)["use_cohort"][0]
    assert saved["outcome"] == "missed" and saved["use"]
