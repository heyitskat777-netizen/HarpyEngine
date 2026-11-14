"""One legacy native held-result recovery, not a session or admission approval."""

from uuid import uuid4

import pytest
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, state
from test_newgirl_changeling_preflight import exact_setup

from girlframe.engine import m3_changeling as changing
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.m3_changeling import ChangelingService
from girlframe.services.m3_newgirl_sex import NewgirlSexService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_legacy_held_respect_can_record_missing_original_fact_and_retry(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, viewers, play = exact_setup(ledger, tmp_path, monkeypatch)
    am, casualty, newgirl, mockingbird = viewers
    service = NewgirlSexService(game)
    source = service.invite(
        newgirl,
        str(uuid4()),
        900,
        (current_ref(state(game), 2),),
        state(game).revision,
        "Voluntary native source",
    )["id"]
    service.confirm(am, str(uuid4()), source, state(game).revision, True, "Owned confirmation")
    # Recreate only the pre-r272 missing-preflight defect. All real roll, choices,
    # source provenance and recovery checks below use unmodified production code.
    with monkeypatch.context() as legacy:
        legacy.setattr("girlframe.services.m3_changeling.preflight_deepening", lambda *args: None)
        action = play(newgirl, "newgirl_sex", source_work=source)
    answer(game, newgirl, "newgirl_sex_ask", text="Do you respect me?")
    before = state(game)
    calls = game.dice.calls
    with ledger.engine.connect() as c:
        held = game.action(c, action)
    choice = next(x for x in game.choices(am) if x["kind"] == "newgirl_sex_respect")
    with pytest.raises(WorkflowError, match="SOURCE_BODY_FACT_REQUIRED"):
        answer(game, am, "newgirl_sex_respect", options=("yes",), text="Independent yes")
    assert state(game) == before
    assert next(x for x in game.choices(am) if x["id"] == choice["id"]) == choice
    body = ChangelingService(game)
    with pytest.raises(WorkflowError, match="actual owner or original Handler"):
        body.body_fact(
            newgirl,
            str(uuid4()),
            before.revision,
            900,
            current_ref(before, 2),
            "girl",
            "Cannot assert another body",
        )
    with pytest.raises(WorkflowError, match="Finish the actual held Play"):
        body.body_fact(
            casualty,
            str(uuid4()),
            before.revision,
            900,
            current_ref(before, 3),
            "girl",
            "Unrelated original body",
        )
    assert state(game) == before
    body.body_fact(
        am,
        str(uuid4()),
        before.revision,
        900,
        current_ref(before, 2),
        "girl",
        "Owner confirms original native body from actual placement; no transformation.",
    )
    recorded = state(game)
    assert recorded.sheets == before.sheets
    assert recorded.order == before.order
    assert game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert game.action(c, action) == held
    with pytest.raises(WorkflowError, match="Do not reset an existing original brain"):
        body.body_fact(
            am,
            str(uuid4()),
            recorded.revision,
            900,
            current_ref(recorded, 2),
            "girl",
            "Cannot overwrite original fact",
        )
    assert state(game) == recorded
    answer(game, am, "newgirl_sex_respect", options=("yes",), text="Independent yes")
    after = state(game)
    assert game.inspect(newgirl, action)["state"] == "complete"
    assert game.dice.calls == calls
    assert (
        depth(after, current_ref(after, 4), current_ref(after, 2))
        == depth(before, current_ref(before, 4), current_ref(before, 2)) + 1
    )
    assert after.order.index(4) == before.order.index(4) - 1
    old = {x.id for x in changing.records(before, changing.String)}
    fresh = [
        x
        for x in changing.records(after, changing.String)
        if x.id not in old
        and x.origin == "deepen"
        and x.actor == current_ref(after, 4)
        and x.subject.actor == current_ref(after, 2)
    ]
    assert len(fresh) == 1 and fresh[0].spent_event is None
    with ledger.engine.connect() as c:
        assert game.action(c, action)["data"]["result"] == held["data"]["result"]
