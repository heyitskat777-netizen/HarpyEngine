import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, setup_game, start, state, tick

from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_paired_slot_rename_keeps_its_period_lock(ledger, monkeypatch):
    import json

    from girlframe.engine.m2 import ChoiceAnswer, TagState
    from girlframe.services.m2_choices import ChoiceEngine

    game, *_ = setup_game(ledger)
    saved = state(game)
    sheet = saved.sheets["2"]
    paired = sheet.identities[0]
    paired.paired = True
    paired.protected = True
    paired.marked = True
    sheet.sedation_locked = (paired.id,)
    sheet.sedation_period = "off-duty-test"
    sheet.tags.append(TagState(id="pair-tag", label="Pair's new Identity", giver=3, marked=True))
    engine = ChoiceEngine(game)
    monkeypatch.setattr(engine, "results", lambda *args: None)
    with ledger.transaction() as c:
        engine.apply(
            c,
            saved,
            {"actor_id": "2", "data": {}},
            {
                "kind": "paired_tag",
                "actor_id": "3",
                "body_json": json.dumps({"tag": "pair-tag", "already_marked": True}),
            },
            ChoiceAnswer(options=("yes",)),
        )
    assert paired.name == "Pair's new Identity" and paired.marked
    assert sheet.sedation_locked == (paired.id,) and sheet.sedation_period == "off-duty-test"


def test_flirt_actor_and_target_cannot_unmark_sedated_identity_through_existing_play(ledger):
    game, worker, gateway, _ = setup_game(ledger)
    with ledger.transaction() as c:
        saved = state(game)
        for sheet in saved.sheets.values():
            sheet.identities[0].marked = True
            sheet.identities[1].marked = True
            sheet.sedation_locked = ("identity:0",)
            sheet.sedation_period = "off-duty-test"
        game.event(c, ADMIN.user_id, "test-locks", "synthetic.sedation", saved)
    start(game, play="flirt", target=3)
    tick(worker, gateway)
    pass_tags(game)
    with pytest.raises(WorkflowError, match="legal options"):
        answer(game, PLAYER, "actor_flirt", options=("hurt",), denied=("identity:0",))
    assert state(game).sheets["2"].identities[0].marked
    answer(game, PLAYER, "actor_flirt", options=("hurt",), denied=("identity:1",))
    with pytest.raises(WorkflowError, match="legal options"):
        answer(game, OTHER, "target_flirt", text="An owned answer", denied=("identity:0",))
    answer(game, OTHER, "target_flirt", text="An owned answer", denied=("identity:1",))
    for sheet in state(game).sheets.values():
        assert sheet.identities[0].marked and not sheet.identities[1].marked
        assert sheet.sedation_locked == ("identity:0",)
