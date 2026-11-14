"""Native Pair delegation preserves an already rolled child while recording a fact."""

from uuid import uuid4

import pytest
import test_bonded as fixture
from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, state, tick

from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_changeling as changing
from girlframe.engine import m3_newgirl_sex as newgirl
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.m3_changeling import ChangelingService
from girlframe.services.m3_newgirl_sex import NewgirlSexService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_native_pair_delegated_newgirl_held_result_records_original_fact(
    ledger, tmp_path, monkeypatch
):
    service = fixture.service

    def changeling_service(store, **kwargs):
        kwargs["frame"] = "CHANGELING"
        return service(store, **kwargs)

    monkeypatch.setattr(fixture, "service", changeling_service)
    game, worker, gateway, controls = fixture.ready(
        ledger, tmp_path, monkeypatch, three=True, native_pair_book="NEWGIRL"
    )
    approved(
        ledger, game, tmp_path, monkeypatch, extra=(*bonded.RULES, newgirl.RULE, changing.STRINGS)
    )
    actor, counterpart = current_ref(state(game), 2), current_ref(state(game), 4)
    parent = fixture.intimate(controls, game, 4, "delegated")
    sex = NewgirlSexService(game)
    child = sex.invite(
        PLAYER,
        str(uuid4()),
        900,
        (counterpart,),
        state(game).revision,
        "My actual Pair's native Newgirl rule",
        bonded_source=parent,
    )["id"]
    sex.confirm(
        fixture.FOUR, str(uuid4()), child, state(game).revision, True, "My independent consent"
    )
    game.dice.faces = (4, 4)
    # Recreate historical already-rolled state, bypassing only the newer preflight.
    with monkeypatch.context() as legacy:
        legacy.setattr("girlframe.services.m3_changeling.preflight_deepening", lambda *a: None)
        action = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play=newgirl.PLAY,
                source_work=child,
                heat=0,
                trigger_confirmed=True,
                context="Original voluntarily delegated source",
            ),
        )["action_id"]
    tick(worker, gateway, 3)
    fixture.pass_tags(game)
    answer(game, PLAYER, "newgirl_sex_ask", text="Do you respect me?")
    before, calls = state(game), game.dice.calls
    with pytest.raises(WorkflowError, match="SOURCE_BODY_FACT_REQUIRED"):
        answer(game, fixture.FOUR, "newgirl_sex_respect", options=("yes",), text="My own yes")
    assert state(game) == before
    with ledger.engine.connect() as c:
        held = game.action(c, action)
    original_parent = bonded.get(before, parent)
    original_child = newgirl.get(before, child)
    body = ChangelingService(game)
    with pytest.raises(WorkflowError, match="actual owner or original Handler"):
        body.body_fact(OTHER, str(uuid4()), before.revision, 900, counterpart, "girl", "Not mine")
    body.body_fact(
        fixture.FOUR,
        str(uuid4()),
        before.revision,
        900,
        counterpart,
        "girl",
        "Original body witnessed by its owner",
    )
    recorded = state(game)
    assert recorded.sheets == before.sheets and recorded.order == before.order
    assert bonded.get(recorded, parent) == original_parent
    assert newgirl.get(recorded, child) == original_child
    assert game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert game.action(c, action) == held
    answer(game, fixture.FOUR, "newgirl_sex_respect", options=("yes",), text="My own yes")
    after = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert controls.view(PLAYER, parent)["phase"] == "complete"
    assert sex.view(PLAYER, child)["phase"] == "complete"
    assert game.dice.calls == calls
    assert depth(after, actor, counterpart) == depth(before, actor, counterpart) + 1
    assert after.order.index(2) == before.order.index(2) - 1
    fresh = [
        s
        for s in changing.records(after, changing.String)
        if s.id not in {x.id for x in changing.records(before, changing.String)}
        and s.actor == actor
        and s.subject.actor == counterpart
    ]
    assert len(fresh) == 1 and fresh[0].spent_event is None
