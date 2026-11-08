"""Defeat Punishment follows a real mission and retains a separate recorded cause."""

import json

import sqlalchemy as sa
from test_defeat_service import rolled
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick

from girlframe.database import tables as t
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_punishments import PunishmentService


def owed(store):
    game, worker, gateway, _, _ = rolled(store, (6, 6))
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("lower_status", "post_mission_punishment"),
        text="Actual Handler rescue, with the original Girl owing post-mission discipline",
    )
    tick(worker, gateway, 6)
    return game, MissionService(store)


def test_defeat_punishment_is_not_prematurely_consumed_by_off_duty(ledger):
    game, missions = owed(ledger)
    period = OffDutyService(missions).begin(ADMIN, "off-duty-before-next-mission")
    assert period["phase"] == "preparing"
    assert any(
        x.kind == "punishment" and x.details.get("cause") == "defeat" and x.state == "pending"
        for x in state(game).obligations
    )
    with ledger.engine.connect() as c:
        table = t.m3["m3_required_work"]
        assert not any(
            json.loads(x).get("cause") == "defeat"
            for x in c.scalars(sa.select(table.c.body_json).where(table.c.kind == "punishment"))
        )


def test_actual_mission_end_creates_distinct_owned_defeat_debt_and_failure_dog_bundle(ledger):
    game, missions = owed(ledger)
    mission = missions.offer(ADMIN, "real-next-mission", "Actual original mission", (2,))
    reply = missions.respond(PLAYER, "real-acceptance", mission["id"], 1, "accept")
    started = missions.start(ADMIN, "real-dispatch", mission["id"], reply["revision"])
    ended = missions.end(ADMIN, "real-failed-mission", mission["id"], started["revision"], False)
    tasks = [
        w
        for w in missions.owned_work(ADMIN)
        if w["kind"] == "punishment" and w["mission_id"] == mission["id"]
    ]
    assert len(tasks) == 3
    service = PunishmentService(ledger)
    original = next(
        w for w in tasks if service.get(ADMIN, w["id"])["causes"] == ["defeat_post_mission"]
    )
    data = service.get(ADMIN, original["id"])
    service.apply(
        ADMIN,
        "actual-defeat-punishment",
        original["id"],
        data["revision"],
        data["game_revision"],
        Details(kind="stimulant_injection"),
    )
    debt = next(x for x in state(game).obligations if x.details.get("cause") == "defeat")
    assert debt.state == "fulfilled" and debt.details["mission"] == mission["id"]
    remaining = [
        w
        for w in missions.owned_work(ADMIN)
        if w["kind"] == "punishment" and w["mission_id"] == mission["id"]
    ]
    assert len(remaining) == 2
    data = service.get(ADMIN, remaining[0]["id"])
    assert set(data["causes"]) == {"mission_failure", "dog_mission_end"}
    service.apply(
        ADMIN,
        "actual-failure-dog-punishment",
        remaining[0]["id"],
        data["revision"],
        data["game_revision"],
        Details(kind="stimulant_injection"),
    )
    assert missions.complete(ADMIN, "actual-mission-complete", mission["id"], ended["revision"])
