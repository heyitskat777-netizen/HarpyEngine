"""Destroyed original Frame → next real period → owned free package."""

import json

import pytest
import sqlalchemy as sa
from test_defeat_service import rolled
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_replacement_service import accept, propose, quote

from girlframe.database import tables as t
from girlframe.engine.m3_frame_state import Preferences
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_replacement import DEFEAT_ROOT, ReplacementService
from girlframe.services.onboarding import WorkflowError


def destroyed(store):
    game, worker, gateway, parent, _ = rolled(store, (1, 1))
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("lose_frame_choose_later",),
        text="The original Frame is irreparably destroyed",
    )
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    tick(worker, gateway, 6)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"playbooks"}}
            )
        }
    )
    missions = MissionService(store)
    return game, OffDutyService(missions), ReplacementService(missions)


def test_destroyed_frame_waits_then_actual_next_off_duty_requires_free_replacement(ledger):
    game, off_duty, replacement = destroyed(ledger)
    before = state(game).sheets["2"]
    assert before.frame_scrapped and not any(a.family == "frame" for a in before.assets)
    assert not any(w["kind"] == DEFEAT_ROOT for w in off_duty.missions.owned_work(PLAYER))
    started = off_duty.begin(ADMIN, "actual-next-period")
    before = state(game).sheets["2"]
    work = next(w for w in off_duty.missions.owned_work(PLAYER) if w["kind"] == DEFEAT_ROOT)
    assert work["off_duty_id"] == started["id"]
    proposed = propose(replacement, work["id"])
    quote(replacement, proposed["package_id"])
    result = accept(replacement, work["id"])
    assert result["frame"] == "THE ENFORCER"
    after = state(game).sheets["2"]
    assert not after.frame_scrapped and after.character_id == before.character_id
    assert after.permissions == before.permissions and after.heat == before.heat
    assert after.identities == before.identities
    assert [a for a in after.assets if a.family == "girl"] == [
        a for a in before.assets if a.family == "girl"
    ]
    with ledger.engine.connect() as c:
        rows = list(
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.kind == "defeat_frame_replacement"
                )
            ).mappings()
        )
        assert rows[-1]["state"] == "resolved"
        assert json.loads(rows[-1]["body_json"])["replacement_work"] == work["id"]


def test_unproven_scrapping_does_not_let_handler_bypass_roster_guard(ledger):
    from test_beneath_service import ready

    game, _, _ = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].frame_scrapped = True
        game.event(c, 1, "synthetic-unproven-loss", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="current Pilot roster"):
        OffDutyService(MissionService(ledger)).begin(ADMIN, "unproven-period")


def test_pending_replacement_remains_owned_and_restart_replay_does_not_duplicate(ledger):
    game, off_duty, replacement = destroyed(ledger)
    started = off_duty.begin(ADMIN, "actual-next-period")
    assert OffDutyService(off_duty.missions).begin(ADMIN, "actual-next-period") == started
    work = next(w for w in off_duty.missions.owned_work(PLAYER) if w["kind"] == DEFEAT_ROOT)
    current = replacement.get(PLAYER, work["id"])
    with pytest.raises(WorkflowError):
        replacement.propose(
            ADMIN,
            "handler-cannot-propose",
            work["id"],
            current["revision"],
            state(game).revision,
            Preferences(frame="THE ENFORCER"),
        )
    assert len([w for w in off_duty.missions.owned_work(PLAYER) if w["kind"] == DEFEAT_ROOT]) == 1
