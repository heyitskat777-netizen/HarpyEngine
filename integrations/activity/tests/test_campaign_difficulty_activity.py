"""Exercise the Activity's owned Defeat form with real synthetic engine choices."""

import pytest
from defeat_play import defeat_choice
from test_campaign_opening import narrative_fixture
from test_defeat_service import rolled
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger

from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.campaign_difficulty import DEATH_USED
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("spent", (False, True))
def test_activity_defeat_reflects_the_campaign_death_limit(ledger, spent):
    game, *_ = rolled(ledger, faces=(1, 1))
    narrative_fixture(ledger)
    if spent:
        with ledger.transaction() as c:
            ledger._audit(
                c, OTHER.user_id, "earlier-death", DEATH_USED, {"archive": "earlier-death"}
            )
    choice = next(item for item in game.choices(PLAYER) if item["kind"] == "defeat_select")
    with pytest.raises(WorkflowError):
        game.decision(OTHER, choice["id"])
    fields = {
        item["key"]: item for item in defeat_choice(game.decision(PLAYER, choice["id"]))["schema"]
    }
    allowed = dict(fields["options"]["options"])
    assert "lose_frame_choose_later" in allowed
    assert ("death" in allowed) is not spent
    assert ("flag" in fields) is not spent
    if not spent:
        assert not fields["flag"]["required"]
        with pytest.raises(WorkflowError, match="NARRATIVE_LIMIT"):
            game.respond(
                PLAYER,
                "unconfirmed-death",
                choice["id"],
                choice["revision"],
                ChoiceAnswer(options=("death",), text="The Pilot chooses the lethal outcome."),
            )
        choice["revision"] = game.decision(PLAYER, choice["id"])["revision"]
        options, flag = ("death",), True
    else:
        options, flag = ("lose_frame_choose_later",), None
    game.respond(
        PLAYER,
        "owned-defeat-result",
        choice["id"],
        choice["revision"],
        ChoiceAnswer(options=options, text="The Pilot confirms their outcome.", flag=flag),
    )
    assert not any(item["id"] == choice["id"] for item in game.choices(PLAYER))
