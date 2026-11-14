"""Actual mandatory Mentor Tag embrace keeps equal labels as distinct legal Identities."""

from uuid import uuid4

import pytest
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_trainee import native_select, ready, teach

from girlframe.engine import m3_trainee as rules
from girlframe.engine.m2 import PlayInput
from girlframe.services.m3_trainee import prove
from girlframe.services.onboarding import WorkflowError


def test_original_mentor_duplicate_label_embrace_only_under_explicit_ruling(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    original = state(game).sheets["2"]
    legal = [
        x
        for x in original.identities
        if not x.protected
        and not x.paired
        and not x.am_limiter
        and not x.obsession_sources
        and x.id not in original.sedation_locked
    ]
    erased, retained = legal[:2]
    game.dice.faces = (6, 6)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        original.revision,
        PlayInput(
            play="flirt",
            target=3,
            heat=0,
            context="Actual conversation with my original Mentor",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_flirt",
        options=("name",),
        fields={"extra": "owe"},
        text="My actual personal question goes too far",
    )
    answer(game, OTHER, "target_flirt", text="My actual preferred name")
    answer(game, OTHER, "flirt_owe_tag", text=retained.name)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    lesson = teach(controls, game, native=True)
    before = state(game)
    tag = next(x for x in before.sheets["2"].tags if x.label == retained.name)
    # The source has no authority to silently choose a duplicate-label interpretation.
    policy = ledger.policy
    assert policy.owner_m3_rulings.identity_duplicate_labels == "distinct_ids"
    ledger.policy = policy.model_copy(update={"owner_m3_rulings": None})
    with pytest.raises((WorkflowError, ValueError)):
        controls.choose(
            PLAYER,
            str(uuid4()),
            lesson,
            before.revision,
            "erase",
            identity_id=erased.id,
            tag=tag.id,
            account="Actual contradictory Identity",
        )
    assert state(game) == before
    ledger.policy = policy
    with pytest.raises(WorkflowError):
        controls.choose(
            OTHER,
            str(uuid4()),
            lesson,
            before.revision,
            "erase",
            identity_id=erased.id,
            tag=tag.id,
            account="Cannot choose for the learner",
        )
    native_select(
        controls,
        PLAYER,
        lesson,
        "erase",
        identity=(erased.id,),
        tag=(tag.id,),
        account="PRIVATE actual contradiction; original Mentor Tag is mandatory",
    )
    final = state(game)
    selected = next(x for x in rules.records(final, rules.Selection) if x.teaching == lesson)
    assert selected.embraced is not None and selected.embraced.id != retained.id
    assert selected.embraced.slot == erased.slot
    assert selected.embraced.name == retained.name
    assert next(x for x in final.sheets["2"].identities if x.id == retained.id) == retained
    assert len({x.id for x in final.sheets["2"].identities}) == len(final.sheets["2"].identities)
    assert len([x for x in final.sheets["2"].identities if x.name == retained.name]) == 2
    assert not any(x.id == erased.id for x in final.sheets["2"].identities)
    assert not any(x.id == tag.id for x in final.sheets["2"].tags)
    assert final.sheets["2"].heat == before.sheets["2"].heat
    assert final.sheets["3"] == before.sheets["3"]
    assert controls.view(PLAYER, lesson)["phase"] == "complete"
    with ledger.engine.connect() as c:
        prove(game, c, final, lesson)
    with pytest.raises(WorkflowError):
        controls.choose(
            PLAYER,
            str(uuid4()),
            lesson,
            final.revision,
            "erase",
            identity_id=retained.id,
            tag=tag.id,
            account="No repeated source effect",
        )
    assert state(game) == final
    assert "PRIVATE actual contradiction" not in str(gateway.messages)
