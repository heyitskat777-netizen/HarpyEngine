"""First actual DNA comparison: optional Tag or decline; authored, deferred final P1."""

import asyncio
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_vatgrown_plays import ready

from girlframe.discord_adapter import m3_vatgrown_dna as native
from girlframe.engine import m3_vatgrown_dna as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_vatgrown_dna import VatgrownDNAService, prove
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


@pytest.mark.parametrize("give", (True, False), ids=("give", "decline"))
def test_actual_comparer_owns_once_only_tag_or_decline_with_private_addressed_basis(
    ledger, tmp_path, monkeypatch, give
):
    game, _, _, _ = ready(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    source = VatgrownDNAService(game)
    actor, comparer = current_ref(state(game), 2), current_ref(state(game), 3)
    own = source.menu(PLAYER, 900)
    private = own["own_basis"][0]["basis"]
    digest = hashlib.sha256(private.encode()).hexdigest()
    other = source.menu(OTHER, 900)
    assert other["roles"] and other["targets"]
    assert private not in json.dumps(other) and digest not in json.dumps(other)
    assert private not in json.dumps(source.menu(ADMIN, 900))
    actual_account = (
        "I actually compare this original Vatgrown and their basis person "
        "from my existing experience."
    )
    comparison_request = (
        OTHER,
        "actual-first-dna-comparison",
        state(game).revision,
        900,
        actor,
        comparer,
        actual_account,
    )
    first = source.compare(*comparison_request)
    assert source.compare(*comparison_request) == first
    comparison = first["id"]
    private_view = source.view(OTHER, comparison)
    assert "basis" not in private_view and private not in json.dumps(private_view)
    assert digest not in json.dumps(private_view)
    assert source.view(PLAYER, comparison)["basis"] == private
    assert private_view["can_resolve"] and private_view["outcome"] == "pending"
    assert not source.view(PLAYER, comparison)["can_resolve"]
    with pytest.raises(WorkflowError):
        source.view(ADMIN, comparison)
    with ledger.engine.connect() as c:
        assert next(row for row in source._tasks(c, OTHER) if row["id"] == comparison)["pending"]
        assert not next(row for row in source._tasks(c, PLAYER) if row["id"] == comparison)[
            "pending"
        ]
        assert not source._tasks(c, ADMIN)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        source.resolve(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            comparison,
            None,
            "The recipient has no fictional veto over the actual comparer",
        )
    assert state(game).model_dump_json() == before
    # Disclosure follows the already real comparison; it was never an approval prerequisite.
    disclosure = source.disclose(
        PLAYER,
        "actual-addressed-dna-disclosure",
        state(game).revision,
        900,
        actor,
        comparer,
        "I disclose my saved basis only to this actual person",
    )
    assert source.view(OTHER, disclosure["id"])["basis"] == private
    assert source.view(OTHER, comparison)["basis"] == private
    with pytest.raises(WorkflowError):
        source.view(ADMIN, disclosure["id"])
    tags_before = tuple(state(game).sheets["2"].tags)
    result_request = (
        OTHER,
        "actual-optional-dna-tag",
        state(game).revision,
        comparison,
        "A familiar face" if give else None,
        "I choose my actual optional Tag"
        if give
        else "I actually decline to give a Tag for this first comparison",
    )
    settled = source.resolve(*result_request)
    assert source.resolve(*result_request) == settled
    saved = source.view(OTHER, comparison)
    assert saved["outcome"] == ("given" if give else "declined") and not saved["can_resolve"]
    if give:
        tag = next(tag for tag in state(game).sheets["2"].tags if tag.id == saved["tag"])
        assert tag.giver_actor == comparer and tag.giver == 3 and tag.label == "A familiar face"
        assert tag.giver_character == comparer.incarnation
    else:
        assert tuple(state(game).sheets["2"].tags) == tags_before and saved["tag"] is None
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), comparison).outcome == saved["outcome"]
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        source.compare(
            OTHER,
            str(uuid4()),
            state(game).revision,
            900,
            actor,
            comparer,
            "A later actual comparison creates no new opportunity",
        )
    assert state(game).model_dump_json() == before and game.dice.calls == 0
    captured = []
    monkeypatch.setattr(native, "viewer_from_interaction", lambda interaction: OTHER)

    async def reply(interaction, text, view=None):
        captured.append(view)

    monkeypatch.setattr(native, "reply", reply)
    asyncio.run(
        native.open_vatgrown_dna(
            SimpleNamespace(user=SimpleNamespace(id=3), channel_id=999), source, comparison
        )
    )
    history = "".join(page.body for page in captured[0].pages)
    assert native.clean(private) in history and saved["outcome"] in history
    assert len(rules.records(state(game), rules.Comparison)) == 1
