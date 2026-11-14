"""Owned protection nonparticipation preserves the actual primary and later failure."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_easy_target import _npc_protection_native, choose, ready, source, validate
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_easy_target import open_easy_target
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_easy_target import EasyTargetService, prove_protection_cohort
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def test_native_protection_cohorts_decline_before_and_after_performance(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, mixed=True)
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
            urge=("protect",),
            context="Actually guard the corridor against interruptions",
            account="My actual NPC chooses to protect her",
        ),
        98500,
        "easy_target_react",
    )
    for viewer, actor in ((OTHER, helper), (OTHER, early), (ADMIN, late)):
        choose(game, viewer, actor, "cohort", primary=work)
    validate(game, npc)
    before = state(game)
    calls = game.dice.calls
    receipt = game.inspect(PLAYER, identity)["receipt"]
    helper_choice = row(OTHER, helper)
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            "not-my-protection-cohort",
            helper_choice["id"],
            helper_choice["revision"],
            ChoiceAnswer(options=("decline",), text="I cannot answer for this original person"),
        )
    assert state(game) == before
    submit(
        OTHER,
        helper,
        dict(outcome=("decline",), account="PRIVATE_PROTECT_DECLINE I decline to go along"),
        98510,
    )
    declined = rules.get(state(game), rules.Reaction, rules.identity(identity, helper))
    first = rules.records(state(game), rules.ProtectionCohort)[-1]
    assert first.outcome == "declined" and first.protection is None
    assert declined.completed_event and not declined.performance_event and not declined.exemption
    assert rules.get(state(game), rules.Reaction, work) == rules.get(before, rules.Reaction, work)
    assert not rules.records(state(game), rules.NpcProtection)
    assert not rules.records(state(game), rules.NpcProtectionFailure)
    assert state(game).sheets == before.sheets and state(game).world == before.world

    submit(OTHER, npc, dict(account="I actually stand guard along the corridor"), 98520)
    performed = state(game)
    primary = rules.get(performed, rules.Reaction, work)
    protection = rules.records(performed, rules.NpcProtection)[-1]
    assert primary.performance_event and primary.protection_event and not primary.exemption
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    submit(
        OTHER,
        early,
        dict(outcome=("decline",), account="I did not join the guard and decline now"),
        98530,
    )
    second = rules.records(state(game), rules.ProtectionCohort)[-1]
    assert second.outcome == "declined" and second.protection == protection.id
    assert rules.get(state(game), rules.Reaction, work) == primary
    assert controls.view(ADMIN, work)["can_report_failure"]
    late_choice = row(ADMIN, late)
    failure = controls.fail_protection(
        ADMIN,
        str(uuid4()),
        work,
        state(game).revision,
        "The original guard tried to keep the corridor clear",
        "An actual visitor interrupted despite the guard's attempt",
    )
    failed = state(game)
    assert controls.view(PLAYER, work)["can_failure_tag"]
    # Failure is irreversible by a stale cohort form, not a new chance at exemption.
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            "late-protection-cohort-decline",
            late_choice["id"],
            late_choice["revision"],
            ChoiceAnswer(options=("decline",), text="Too late to decline the original opportunity"),
        )
    assert state(game) == failed
    submit(
        ADMIN,
        late,
        dict(outcome=("missed",), account="I did not participate before the protection failed"),
        98540,
    )
    missed = rules.records(state(game), rules.ProtectionCohort)[-1]
    assert missed.outcome == "missed" and missed.failure == failure["id"]
    assert rules.get(state(game), rules.Reaction, declined.id) == declined
    assert controls.view(PLAYER, work)["can_failure_tag"]
    controls.failure_tag(
        PLAYER, str(uuid4()), work, state(game).revision, True, "The actual corridor guard failed"
    )
    actual = state(game)
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert rules.get(actual, rules.Reaction, work).consequence == "failure-tag"
    assert not rules.get(actual, rules.Reaction, work).exemption
    assert all(not x.exemption for x in rules.records(actual, rules.Reaction))
    assert actual.sheets == before.sheets
    assert game.dice.calls == calls and game.inspect(PLAYER, identity)["receipt"] == receipt
    outcomes = rules.records(actual, rules.ProtectionCohort)
    assert len(outcomes) == 3
    with game.store.engine.connect() as c:
        for outcome in outcomes:
            assert prove_protection_cohort(game, c, actual, outcome.id) == outcome
        assert "PRIVATE_PROTECT_DECLINE" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
    with pytest.raises(WorkflowError):
        controls.view(GuildViewer(9, 200, True, False), declined.id)

    # The original decline remains privately readable after a genuine new scene.
    tick(worker, gateway, 6)
    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    later = state(game)
    with game.store.engine.connect() as c:
        for outcome in outcomes:
            assert prove_protection_cohort(game, c, later, outcome.id) == outcome
    assert EasyTargetService(game).view(OTHER, declined.id)["protection_cohort"][0] == (
        first.model_dump(mode="json")
    )

    async def reopen():
        interaction = current(OTHER.user_id, 98590)
        interaction.channel_id = 999
        await interaction.response.defer(ephemeral=True)
        await open_easy_target(interaction, EasyTargetService(game), declined.id)
        text = str(interaction.edit_original_response.call_args)
        assert "PRIVATE_PROTECT_DECLINE" in text and "declined" in text

    asyncio.run(reopen())
