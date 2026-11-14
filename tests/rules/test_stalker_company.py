"""Actual Stalker companionship requires its directional source and owned facts."""

from uuid import uuid4

import pytest
from test_ankou import buy, native, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine import m3_ankou as rules
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.m3_ankou import request_source, stalker_view
from girlframe.services.onboarding import WorkflowError


def test_native_stalker_company_uses_actual_directional_source_and_target_owned_fact(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    buy(controls, rules.STALKER)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    before = state(game)
    assert depth(before, actor, target) != 2
    with pytest.raises(WorkflowError, match="Intense"):
        request_source(
            game,
            PLAYER,
            str(uuid4()),
            before.revision,
            900,
            target,
            "company",
            "No qualifying source yet",
        )
    assert state(game) == before
    buy(controls, rules.OBSESSIVE)
    controls.choose_obsession(
        PLAYER, str(uuid4()), state(game).revision, target, "My actual one-sided connection"
    )
    qualified = state(game)
    assert rules.effective_intense(qualified, actor, target)
    assert not rules.effective_intense(qualified, target, actor)
    assert depth(qualified, actor, target) == depth(before, actor, target)
    with ledger.engine.connect() as c:
        initial = stalker_view(game, c, qualified, actor, target)
    assert initial["cell"] is not None and not initial["company_known"]
    assert initial["company"] is None
    native(
        controls,
        "request_source",
        person=(target.token,),
        kind=("company",),
        account="I use my actual Stalker connection to know who they are with",
    )
    requested = state(game)
    task = next(x for x in rules.records(requested, rules.Task) if x.kind == "company")
    assert task.actor == target and task.target == actor and task.controller == OTHER.user_id
    assert actor.model_dump_json() in task.options
    asker_view = controls.view(PLAYER, task.id)
    owner_view = controls.view(OTHER, task.id)
    assert asker_view["source"]["options"] == [] and "company_options" not in asker_view
    assert not asker_view["can_choose"] and owner_view["can_choose"]
    assert any(x["value"] == actor.model_dump_json() for x in owner_view["company_options"])
    for wrong in (PLAYER, ADMIN):
        with pytest.raises(WorkflowError):
            controls.choose_task(
                wrong,
                str(uuid4()),
                requested.revision,
                task.id,
                actor.model_dump_json(),
                "Not the actual target's answer",
            )
        assert state(game) == requested
    response = controls.choose_task(
        OTHER,
        str(uuid4()),
        requested.revision,
        task.id,
        actor.model_dump_json(),
        "This actual original person is here with me",
    )
    answered = state(game)
    company = next(x for x in rules.records(answered, rules.Company) if x.request == task.id)
    assert company.actor == target and company.companions == (actor,)
    assert response["id"] == task.id
    assert company.author == OTHER.user_id
    assert company.event == rules.get(answered, rules.Task, task.id).selected_event
    with ledger.engine.connect() as c:
        known = stalker_view(game, c, answered, actor, target)
    assert known["company_known"] and known["company"][0]["ref"] == actor.model_dump(mode="json")
    assert known["cell"] == initial["cell"]
    with pytest.raises(WorkflowError):
        controls.choose_task(
            OTHER,
            str(uuid4()),
            answered.revision,
            task.id,
            "none",
            "The completed fact cannot be overwritten",
        )
    assert state(game) == answered and game.dice.calls == 0
