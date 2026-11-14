"""Earned Newgirl lesson: legacy held result repairs a human-authored prerequisite."""

from uuid import uuid4

import pytest
import test_creation_review as creation_fixture
import test_vatgrown_plays as fixture
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick
from test_vatgrown_plays import native_choice

from girlframe.engine import m3_changeling as changing
from girlframe.engine import m3_newgirl_sex as newgirl
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.m3_changeling import ChangelingService
from girlframe.services.m3_learned_sex import prove
from girlframe.services.m3_newgirl_sex import NewgirlSexService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_earned_newgirl_held_respect_preserves_lesson_while_owner_records_fact(
    ledger, tmp_path, monkeypatch
):
    ready, approved = creation_fixture.ready, fixture.approved

    def ready_changeling(store, *args, **kwargs):
        kwargs["frame"] = "CHANGELING"
        return ready(store, *args, **kwargs)

    def approved_strings(*args, **kwargs):
        kwargs["extra"] = (*kwargs.get("extra", ()), changing.STRINGS)
        return approved(*args, **kwargs)

    monkeypatch.setattr(creation_fixture, "ready", ready_changeling)
    monkeypatch.setattr(fixture, "approved", approved_strings)
    game, worker, gateway, controls = fixture._actual_newgirl_teacher_vatgrown_sex_learner(
        ledger, tmp_path, monkeypatch
    )
    teacher, learner = current_ref(state(game), 2), current_ref(state(game), 3)
    source = controls.invite(
        OTHER, str(uuid4()), 900, teacher, state(game).revision, "Voluntary original lesson"
    )["id"]
    controls.respond(
        PLAYER, str(uuid4()), source, state(game).revision, True, "Independent consent"
    )
    taught = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play=vat.PLAY,
            source_work=source,
            heat=1,
            trigger_confirmed=True,
            context="Actual Newgirl lesson",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    original = state(game)
    native_choice(
        game,
        PLAYER,
        "vat_sex_learn",
        identities=(original.sheets["2"].identities[1].id,),
        replacements=(original.sheets["3"].identities[0].id,),
        play=(newgirl.RULE,),
        account="Teach actual own Play",
    )
    lesson = vat.records(state(game), vat.LearnedPlay)[-1]
    assert game.inspect(OTHER, taught)["state"] == "complete"
    controls.send_away(PLAYER, str(uuid4()), source, state(game).revision, "Release learner")
    tick(worker, gateway, 6)
    sex = NewgirlSexService(game)
    proposed = sex.invite(
        OTHER,
        str(uuid4()),
        900,
        (teacher,),
        state(game).revision,
        "Voluntary earned source",
        learned_source=lesson.id,
    )["id"]
    sex.confirm(PLAYER, str(uuid4()), proposed, state(game).revision, True, "Independent consent")
    game.dice.faces = (3, 4)
    # Only bypass newer preflight during begin to recreate the real legacy state.
    with monkeypatch.context() as legacy:
        legacy.setattr("girlframe.services.m3_changeling.preflight_deepening", lambda *a: None)
        action = game.begin(
            OTHER,
            str(uuid4()),
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play=newgirl.PLAY,
                source_work=proposed,
                heat=1,
                trigger_confirmed=True,
                context="Actual earned Play",
            ),
        )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "newgirl_sex_ask", text="Do you respect me?")
    before, calls = state(game), game.dice.calls
    with pytest.raises(WorkflowError, match="SOURCE_BODY_FACT_REQUIRED"):
        answer(game, PLAYER, "newgirl_sex_respect", options=("yes",), text="My own yes")
    assert state(game) == before
    saved = newgirl.get(before, proposed)
    with ledger.engine.connect() as c:
        held = game.action(c, action)
        link = prove(game, c, before, saved.learned_source)
    body = ChangelingService(game)
    with pytest.raises(WorkflowError, match="actual owner or original Handler"):
        body.body_fact(PLAYER, str(uuid4()), before.revision, 900, learner, "girl", "Not mine")
    body.body_fact(
        OTHER,
        str(uuid4()),
        before.revision,
        900,
        learner,
        "girl",
        "Owner confirms unchanged original human body",
    )
    recorded = state(game)
    assert recorded.sheets == before.sheets and game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert game.action(c, action) == held
        assert prove(game, c, recorded, saved.learned_source) == link
    answer(game, PLAYER, "newgirl_sex_respect", options=("yes",), text="My own yes")
    after = state(game)
    assert game.inspect(OTHER, action)["state"] == "complete"
    assert game.dice.calls == calls
    assert depth(after, learner, teacher) == depth(before, learner, teacher) + 1
    assert after.order.index(3) == before.order.index(3) - 1
    fresh = [
        x
        for x in changing.records(after, changing.String)
        if x.id not in {v.id for v in changing.records(before, changing.String)}
        and x.origin == "deepen"
        and x.actor == teacher
        and x.subject.actor == learner
    ]
    assert len(fresh) == 1 and fresh[0].spent_event is None
    with ledger.engine.connect() as c:
        final = prove(game, c, after, saved.learned_source)
        assert final.action == action and final.roll_event == link.roll_event
        assert final.receipt_sha256 == link.receipt_sha256
