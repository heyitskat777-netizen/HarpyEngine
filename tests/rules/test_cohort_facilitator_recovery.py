"""A human ruling coordinates the original cohort response, never substitutes for it."""

import asyncio

import pytest
from test_easy_target import _npc_protection_native, choose, ready, source, validate
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService


def test_existing_facilitator_recovers_only_after_original_cohort_response(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch, mixed=True)
    npc, helper = (ActorRef(kind="npc", entity=x) for x in ("bystander", "cohort"))
    identity = source(game, worker, gateway, faces=(5, 5), selected=npc)
    work = rules.identity(identity, npc)
    early, late = current_ref(state(game), 3), current_ref(state(game), 1)

    def submit(viewer, actor, values, number, kind="easy_target_child"):
        choice = next(x for x in game.choices(viewer) if x["kind"] == kind + ":" + actor.token)
        asyncio.run(_npc_protection_native(game, viewer.user_id, choice, values, number))

    submit(
        OTHER,
        npc,
        dict(
            urge=("use",),
            context="Ordinary rehearsal without a Play trigger",
            account="I use her as my audience",
        ),
        99900,
        "easy_target_react",
    )
    for viewer, actor in ((OTHER, helper), (OTHER, early), (ADMIN, late)):
        choose(game, viewer, actor, "cohort", primary=work)
    validate(game, npc)
    submit(OTHER, helper, dict(outcome=("participate",), account="I actually go along"), 99910)
    submit(OTHER, early, dict(outcome=("decline",), account="I decline to go along"), 99920)
    submit(OTHER, npc, dict(account="My actual rehearsal is now finished"), 99930)
    before = state(game)
    waiting = rules.get(before, rules.Reaction, rules.identity(identity, late))
    receipt = game.inspect(PLAYER, identity)["receipt"]
    calls = game.dice.calls
    assert not waiting.completed_event

    service = FacilitatorService(game)
    # The facilitator is deliberately not the unavailable cohort's controller.
    service.configure(ADMIN, "cohort-facilitator", "user", OTHER.user_id)
    candidates = service.candidates(PLAYER, 900)
    assert any(x[0] == "action:" + identity for x in candidates["sources"])
    request = service.request(
        PLAYER,
        "cohort-request",
        900,
        "action",
        identity,
        rules.RULE,
        state(game).revision,
        "The original cohort controller is unavailable; retain their unanswered choice.",
        shared=True,
    )["id"]

    def change(operation, text="", adapter="blocked"):
        current = service.view(OTHER, request)
        return service.change(
            OTHER,
            "cohort-" + operation + "-" + adapter + "-" + str(current["revision"]),
            request,
            current["revision"],
            state(game).revision,
            operation,
            text,
            adapter=adapter,
        )

    with pytest.raises(WorkflowError, match="mandatory"):
        change("rule", "Treat silence as a fiction-only answer", "fiction_only")
    with pytest.raises(WorkflowError, match="mandatory"):
        change("decline")
    change("rule", "Keep the unanswered choice blocked while the controller is absent")
    with pytest.raises(WorkflowError, match="supported source effect"):
        change("resume")
    change(
        "rule",
        "The original controller must record their own missed participation",
        "existing_source",
    )
    with pytest.raises(WorkflowError, match="actual original action"):
        change("resume")
    assert rules.get(state(game), rules.Reaction, waiting.id) == waiting
    assert game.inspect(PLAYER, identity)["state"] != "complete"

    # Recovery becomes possible only when the original controller actually returns.
    submit(
        ADMIN,
        late,
        dict(outcome=("missed",), account="I did not participate before the rehearsal finished"),
        99940,
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert change("resume")["status"] == "resolved"
    after = state(game)
    missed = rules.get(after, rules.Reaction, waiting.id)
    assert missed.consequence == "use-cohort-missed" and not missed.exemption
    assert not missed.performance_event
    assert after.sheets == before.sheets and after.world == before.world
    assert rules.get(after, rules.Reaction, work) == rules.get(before, rules.Reaction, work)
    assert game.dice.calls == calls and game.inspect(PLAYER, identity)["receipt"] == receipt
    assert service.view(PLAYER, request)["request"]["status"] == "resolved"
