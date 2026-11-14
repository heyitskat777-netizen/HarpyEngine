"""Native original participation precedes actual completed NPC use and exemptions."""

import asyncio
from uuid import uuid4

import pytest
from test_easy_target import _npc_protection_native, choose, ready, source, validate
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick

from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_easy_target import EasyTargetService, prove_use_cohort
from girlframe.services.onboarding import WorkflowError


def test_native_cohort_participates_before_npc_use_finishes(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, mixed=True)
    npc = ActorRef(kind="npc", entity="bystander")
    helper = ActorRef(kind="npc", entity="cohort")
    identity = source(game, worker, gateway, faces=(5, 5), selected=npc)
    work = rules.identity(identity, npc)
    helper_work = rules.identity(identity, helper)
    calls = game.dice.calls
    receipt = game.inspect(PLAYER, identity)["receipt"]

    def submit(actor, values, interaction_id, kind="easy_target_child"):
        row = next(x for x in game.choices(OTHER) if x["kind"] == kind + ":" + actor.token)
        asyncio.run(_npc_protection_native(game, OTHER.user_id, row, values, interaction_id))

    submit(
        npc,
        dict(
            urge=("use",),
            context="An ordinary rehearsal with no Play trigger",
            account="I use her as my audience",
        ),
        99900,
        "easy_target_react",
    )
    submit(
        helper,
        dict(urge=("cohort",), primary=(work,), account="I go along with the actual rehearsal"),
        99910,
        "easy_target_react",
    )
    choose(game, OTHER, current_ref(state(game), 3), "pass")
    choose(game, ADMIN, current_ref(state(game), 1), "pass")
    validate(game, npc)
    before = state(game)
    original_depth = depth(before, current_ref(before, 2), npc)
    submit(
        helper,
        dict(
            outcome=("participate",),
            account="PRIVATE_USE_COHORT I actually participate in the rehearsal",
        ),
        99920,
    )
    participating = state(game)
    participation = rules.records(participating, rules.UseCohort)[-1]
    assert participation.reaction == helper_work and participation.primary == work
    assert not rules.records(participating, rules.NpcUse)
    assert not rules.get(participating, rules.Reaction, helper_work).completed_event
    assert not rules.get(participating, rules.Reaction, work).completed_event
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    submit(npc, dict(account="I have now finished rehearsing with my actual participant"), 99930)
    actual = state(game)
    primary = rules.get(actual, rules.Reaction, work)
    follower = rules.get(actual, rules.Reaction, helper_work)
    assert primary.exemption == helper_work and follower.exemption == work
    assert primary.consequence == follower.consequence == "cohort-exempt"
    assert primary.completed_event == follower.completed_event == primary.performance_event
    assert follower.performance_event == participation.event
    assert len(rules.records(actual, rules.NpcUse)) == 1
    assert not primary.child and not follower.child
    assert not any(x["kind"].startswith("easy_target_bond") for x in game.choices(PLAYER))
    assert depth(actual, current_ref(actual, 2), npc) == original_depth
    assert actual.sheets == before.sheets and actual.world == before.world
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.dice.calls == calls and game.inspect(PLAYER, identity)["receipt"] == receipt
    assert (
        EasyTargetService(game).view(OTHER, helper_work)["use_cohort"][0]["id"] == participation.id
    )
    with game.store.engine.connect() as c:
        assert prove_use_cohort(game, c, actual, participation.id) == participation
        forged = actual.model_copy(deep=True)
        rules.put(forged, participation.model_copy(update=dict(account="Not the owned response")))
        with pytest.raises(WorkflowError, match="actual owned participation"):
            prove_use_cohort(game, c, forged, participation.id)

    # A later ordinary scene must not replace the immutable performance's cast.
    tick(worker, gateway, 6)
    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    later = state(game)

    def no_live_profiles(*args, **kwargs):
        raise AssertionError("Historical proof must use original snapshot profile bindings")

    with monkeypatch.context() as historical:
        historical.setattr("girlframe.services.m3_easy_target.profiles", no_live_profiles)
        historical.setattr("girlframe.services.m3_dose_up.profiles", no_live_profiles)
        with game.store.engine.connect() as c:
            assert prove_use_cohort(game, c, later, participation.id) == participation
        assert (
            EasyTargetService(game).view(OTHER, helper_work)["use_cohort"][0]["id"]
            == participation.id
        )
