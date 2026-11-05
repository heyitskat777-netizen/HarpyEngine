"""An original's return does not rewrite a mission she actually left."""

from uuid import uuid4

from test_career_missions import dispatch, end_career
from test_ledger import ADMIN
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine.m2 import PilotSheet
from girlframe.engine.m3_career_state import IncarnationBinding


def test_returned_original_remains_source_departed_from_dispatched_mission(ledger):
    missions, game, started = dispatch(ledger)
    _, original = end_career(ledger, game)
    with ledger.transaction() as c:
        canon = state(game)
        archive = canon.career_archives[-1]
        sheet = PilotSheet.model_validate_json(archive.sheet_json)
        canon.sheets[original.entity] = sheet
        canon.order = (2, 3)
        canon.incarnation_bindings.append(
            IncarnationBinding(
                owner=2,
                character=original.incarnation,
                profile_id=archive.profile_id,
                first_profile_revision=archive.profile_revision,
                active=True,
                source_event="actual-synthetic-return",
            )
        )
        game.event(c, 2, str(uuid4()), "m3.synthetic_original_return", canon)
    missions.end(ADMIN, str(uuid4()), started["id"], started["revision"], True)
    with ledger.engine.connect() as c:
        saved = missions._mission(c, started["id"])
    assert saved.ended_participants == {"2": original.incarnation}
    assert state(game).sheets["2"].permissions == sheet.permissions + 1
    # Current Ace is genuine; original mission participation is not restored.
