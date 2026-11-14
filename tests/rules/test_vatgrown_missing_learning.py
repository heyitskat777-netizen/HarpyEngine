"""Missing mandatory learned consumers retain the real source and human ownership."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_vatgrown_plays import ready, sex

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_vatgrown_plays import open_choice
from girlframe.engine import m3_vatgrown_plays as rules
from girlframe.services import m3_learned_plays
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService, pending


def test_high_learning_missing_consumer_opens_durable_owned_request_without_spending(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    identity, action = sex(game, worker, gateway, controls, (5, 5))
    # A temporarily unavailable teacher consumer exercises the missing capability
    # boundary without inventing a Pair, anatomy or a successful learned effect.
    monkeypatch.setattr(m3_learned_plays, "teacher_lessons", lambda sheet: ())
    row = next(x for x in game.choices(OTHER) if x["kind"] == "vat_sex_learn")
    decision = game.decision(OTHER, row["id"])
    assert decision["detail"]["tier"] == "high" and not decision["detail"]["plays"]
    before = state(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    service = FacilitatorService(game)

    async def open_native():
        interaction = current(OTHER.user_id, uuid4().int % 1000000000)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, decision)
        rendered = interaction.edit_original_response.call_args.kwargs
        assert rendered["view"].owner == OTHER.user_id
        assert "Human adjudication" in rendered["content"]
        assert rendered["allowed_mentions"].everyone is False

    asyncio.run(open_native())
    with ledger.engine.connect() as c:
        requests = pending(game, c, 900)
    assert len(requests) == 1
    request = requests[0]
    assert request.source_kind == "action" and request.source == action
    assert request.rule == "choice:vat_sex_learn"
    assert request.requester == OTHER.user_id and request.mandatory
    assert request.status == "configuration_required" and not request.shared
    # Reopening is a single durable request, not another roll, grant or charge.
    asyncio.run(open_native())
    with ledger.engine.connect() as c:
        assert len(pending(game, c, 900)) == 1
    assert state(game).sheets == before.sheets
    assert rules.records(state(game), rules.LearnedPlay) == rules.records(before, rules.LearnedPlay)
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert any(x["id"] == row["id"] for x in game.choices(OTHER))
    assert controls.view(OTHER, identity)["session"]["phase"] != "complete"
    with pytest.raises(WorkflowError):
        service.view(PLAYER, request.id)
    service.configure(ADMIN, "configure-human", "user", ADMIN.user_id)
    view = service.view(ADMIN, request.id)
    service.change(
        ADMIN,
        "missing-actual-consumer",
        request.id,
        view["revision"],
        state(game).revision,
        "rule",
        "The actual learned effect remains unsupported.",
        adapter="blocked",
    )
    view = service.view(ADMIN, request.id)
    with pytest.raises(WorkflowError):
        service.change(
            ADMIN,
            "cannot-narrate-away-learning",
            request.id,
            view["revision"],
            state(game).revision,
            "rule",
            "No substitute for the original owed learning.",
            adapter="fiction_only",
        )
    assert service.view(OTHER, request.id)["request"]["status"] == "adapter_blocked"
    with ledger.engine.connect() as c:
        assert "PRIVATE_VOLUNTARY_SOURCE" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
