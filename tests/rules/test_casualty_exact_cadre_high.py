"""One real high Casualty consequence in Kat's exact cadre; no session simulation."""

from uuid import uuid4

from test_casualty import choose
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_newgirl_changeling_preflight import exact_setup

from girlframe.engine import m3_casualty as rules
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.m3_am_sex import SexService
from girlframe.services.m3_casualty import CasualtyService


def test_casualty_doctor_high_with_am_ankou_applies_all_immediate_effects(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, viewers, play = exact_setup(ledger, tmp_path, monkeypatch)
    am, casualty, newgirl, mockingbird = viewers
    original = state(game)
    service = CasualtyService(game)
    source = service.invite(
        casualty,
        str(uuid4()),
        900,
        current_ref(original, am.user_id),
        original.revision,
        "Owned voluntary mechanical source",
    )["id"]
    service.confirm(
        am,
        str(uuid4()),
        source,
        state(game).revision,
        True,
        "AM independently confirms participation",
    )
    calls = game.dice.calls
    action = play(
        casualty,
        "casualty_sex",
        faces=(6, 6),
        source_work=source,
        target_actor=current_ref(state(game), am.user_id),
    )
    before = state(game)
    receipt = game.inspect(casualty, action)["receipt"]
    choose(game, casualty, "casualty_high_heat", native=True, number=3)
    choose(game, am, "casualty_high_heat", native=True, number=4)
    asset = next(
        x for x in before.sheets[str(am.user_id)].assets if x.family == "girl" and not x.damaged
    )
    choose(
        game,
        casualty,
        "casualty_high_asset",
        native=True,
        denied=(asset.id,),
        text="The actual counterpart Asset is damaged",
    )
    choose(
        game,
        am,
        "casualty_high_part",
        native=True,
        options=("hands",),
        text="The independently chosen original Hands are broken",
    )
    after = state(game)
    assert after.sheets[str(casualty.user_id)].heat == before.sheets[str(casualty.user_id)].heat + 3
    assert after.sheets[str(am.user_id)].heat == before.sheets[str(am.user_id)].heat + 4
    assert next(x for x in after.sheets[str(am.user_id)].assets if x.id == asset.id).damaged
    assert rules.part_state(after, current_ref(after, casualty.user_id), "hands") == "broken"
    assert depth(after, current_ref(after, casualty.user_id), current_ref(after, am.user_id)) == (
        depth(before, current_ref(before, casualty.user_id), current_ref(before, am.user_id)) + 1
    )
    assert game.inspect(casualty, action)["state"] == "complete"
    assert game.inspect(casualty, action)["receipt"] == receipt
    menu = SexService(game).menu(am, 900)
    assert menu["no_additional_roll"]
    assert next(x for x in menu["sources"] if x["id"] == action)["receipt"] == receipt["id"]
    assert game.dice.calls == calls + 1
    # No effect is silently applied to the other two cadre members.
    for viewer in (newgirl, mockingbird):
        assert after.sheets[str(viewer.user_id)] == before.sheets[str(viewer.user_id)]
    tick(worker, gateway, 5)
