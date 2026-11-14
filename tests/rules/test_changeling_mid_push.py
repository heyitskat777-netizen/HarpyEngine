"""Native Blank Slate mid follow-up carries the printed Status cost and Tag."""

from uuid import uuid4

from test_changeling import define, ready, roll
from test_ledger import OTHER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state

from girlframe.engine import m3_changeling as rules
from girlframe.engine.m3_actor_bonds import current_ref

ledger = ledger_fixture


def test_native_mid_blank_slate_overstep_lowers_speaker_status_and_gives_tag(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    action = roll(game, worker, gateway, source=define(game, controls))
    assert rules.session(state(game), action).completed_event
    assert state(game).order == (3, 2)
    speaker, addressed = current_ref(state(game), 3), current_ref(state(game), 2)
    speech = controls.speak(
        OTHER,
        str(uuid4()),
        state(game).revision,
        900,
        speaker,
        addressed,
        "push",
        "I insist that you are too cautious for this mission.",
        session=action,
    )["id"]
    payload = (OTHER, "actual-mid-overstep", state(game).revision, speech, "Too cautious")
    result = controls.push(*payload)
    canon = state(game)
    assert canon.order == (2, 3)
    tags = [tag for tag in canon.sheets["2"].tags if tag.label == "Too cautious"]
    assert len(tags) == 1 and tags[0].giver_actor == speaker
    consequence = rules.record(canon, rules.Push, result["id"])
    assert consequence.session == action and consequence.actor == speaker
    assert consequence.target == addressed and consequence.speech == speech
    assert rules.record(canon, rules.Speech, speech).used_by == consequence.id
    assert any(
        fact.get("kind") == "changeling_status"
        and fact.get("source") == action
        and fact.get("actor") == speaker.model_dump_json()
        and fact.get("delta") == "-1"
        for fact in canon.facts
    )
    saved = canon.model_dump_json()
    assert controls.push(*payload) == result
    assert state(game).model_dump_json() == saved
    assert game.dice.calls == 1
