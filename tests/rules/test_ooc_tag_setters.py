"""Explicit human GM Tag authorship survives body changes without becoming a new persona."""

from uuid import uuid4

import pytest
from test_handler_creation import agree, complete, ready, save
from test_handler_generations import accept_all, end_original, save_fresh
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine.m2 import TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import mentor_tag
from girlframe.services.m3_tag_setters import ooc_setter
from girlframe.services.onboarding import WorkflowError


def created(store):
    svc, game = ready(store)
    appointment = svc.view(ADMIN)["appointment"]
    event = str(uuid4())
    with store.transaction() as c:
        canon = state(game)
        canon.sheets["2"].tags.append(
            TagState(
                id="actual-ooc-gm-tag",
                label="Actual human-authored Tag",
                giver=1,
                observers=(1, 2),
                gm_setter_appointment=appointment,
            )
        )
        game.event(c, 1, "actual-gm-tag-created", "synthetic.actual_gm_tag", canon, event_id=event)
    return svc, game, event


def proof(store, game, tag=None, subject=None):
    actual = state(game)
    tag = tag or actual.sheets["2"].tags[-1]
    subject = subject or current_ref(actual, 2)
    with store.engine.connect() as c:
        return ooc_setter(c, store, subject, tag)


def test_real_event_proves_human_setter_across_first_naming_death_and_fresh_persona(ledger):
    svc, game, event = created(ledger)
    assert proof(ledger, game) == 1
    save(svc, complete(svc, "Trainer"))
    agree(svc)
    view = svc.view(ADMIN)
    svc.activate(
        ADMIN, "first-persona-keeps-ooc-setter", view["revision"], view["game_revision"], True
    )
    tag = state(game).sheets["2"].tags[-1]
    assert tag.giver_actor is None and tag.giver_character is None and tag.gm_setter_event == event
    assert proof(ledger, game) == 1
    end_original(svc, game, create=False)
    save_fresh(svc, complete(svc, "Trainer"))
    accept_all(svc)
    view = svc.view(ADMIN)
    svc.activate(
        ADMIN, "fresh-persona-keeps-ooc-setter", view["revision"], view["game_revision"], True
    )
    tag = state(game).sheets["2"].tags[-1]
    assert tag.giver_actor is None and tag.giver_character is None and tag.gm_setter_event == event
    assert proof(ledger, game) == 1


@pytest.mark.parametrize("change", ["appointment", "event", "giver", "actor", "target"])
def test_truthy_or_replaced_ooc_provenance_cannot_authorize_a_setter(ledger, change):
    _, game, _ = created(ledger)
    tag = state(game).sheets["2"].tags[-1]
    values = {
        "appointment": {"gm_setter_appointment": "not-an-authenticated-appointment"},
        "event": {"gm_setter_event": str(uuid4())},
        "giver": {"giver": 2},
        "actor": {"giver_actor": ActorRef(kind="handler", entity="1")},
        "target": {},
    }
    tag = tag.model_copy(update=values[change])
    target = current_ref(state(game), 3) if change == "target" else None
    with pytest.raises(WorkflowError, match="SOURCE_GM_TAG_SETTER_MISSING"):
        proof(ledger, game, tag, target)


def test_ooc_human_matching_mentor_uid_does_not_gain_mentor_tag_exception(ledger):
    _, game, _ = created(ledger)
    girl = state(game).sheets["2"].model_copy(update={"girl": "NEWGIRL", "mentor": 3})
    ordinary = TagState(id="actual-mentor-tag", label="Actual mentor Tag", giver=3)
    assert mentor_tag(girl, ordinary, state(game))
    ooc = ordinary.model_copy(update={"gm_setter_appointment": "actual-other-gm-appointment"})
    assert not mentor_tag(girl, ooc, state(game))


def test_shared_tag_choice_rechecks_actual_ooc_principal_and_rolls_back_forged_claim(ledger):
    import json

    from test_m2_game import Gateway, answer, tick

    from girlframe.database import tables as t
    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m2 import PlayInput

    _, game, _ = created(ledger)
    identity = game.begin(
        PLAYER,
        "actual-ooc-tag-shared-play",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="Actual source Tag context",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(GameWorker(game), Gateway(), 3)
    before_calls = game.dice.calls
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].tags[-1].gm_setter_appointment = "FORGED_APPOINTMENT"
        table = t.m2["m2_state"]
        c.execute(
            table.update()
            .where(table.c.campaign_id == ledger.campaign_id)
            .values(
                body_json=canon.model_dump_json(),
            )
        )
    pending = next(x for x in game.choices(ADMIN) if x["kind"] == "tag_window")
    with pytest.raises(WorkflowError, match="SOURCE_GM_TAG_SETTER_MISSING"):
        answer(
            game,
            ADMIN,
            "tag_window",
            options=("tag",),
            denied=("actual-ooc-gm-tag",),
            number=1,
            text="Attempted use of forged OOC source",
        )
    assert next(x for x in game.choices(ADMIN) if x["kind"] == "tag_window")["id"] == pending["id"]
    with ledger.engine.connect() as c:
        actual = game.action(c, identity)
    assert str(ADMIN.user_id) not in actual["data"].get("tag_markers", {})
    assert game.dice.calls == before_calls == 1
    assert "tag_marker_applied" not in actual["data"]
    assert "FORGED_APPOINTMENT" not in json.dumps(actual["data"]["choices"])
