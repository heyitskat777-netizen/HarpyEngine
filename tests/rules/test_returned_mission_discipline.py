"""An actual returned original resumes real due causes without inheriting new roles."""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_defeat_debts import owed
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_off_duty_cycle import activate
from test_returned_frame_replacement import end_original, prepare_period, return_original, rows
from test_strain_service import D6
from test_world import initial

from girlframe.database import tables as t
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def prepared_return(ledger):
    game, missions = owed(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"playbooks", "strain", "world"}}
            )
        }
    )
    assert state(game).sheets["2"].medical_state == "fit"
    offered = missions.offer(ADMIN, str(uuid4()), "Actual original mission", (2,))
    accepted = missions.respond(PLAYER, str(uuid4()), offered["id"], 1, "accept")
    launched = missions.start(ADMIN, str(uuid4()), offered["id"], accepted["revision"])
    missions.end(ADMIN, str(uuid4()), offered["id"], launched["revision"], False)
    old_work = [
        w
        for w in missions.owned_work(ADMIN)
        if w["mission_id"] == offered["id"] and w["kind"] == "punishment"
    ]
    assert len(old_work) == 3
    archive = end_original(ledger, game)
    with ledger.engine.connect() as c:
        ended = missions._mission(c, offered["id"])
    missions.complete(ADMIN, str(uuid4()), offered["id"], ended.revision)
    closed_rows = [r for r in rows(ledger) if r["id"] in {w["id"] for w in old_work}]
    return_original(ledger, game, archive)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"strain", "world"}}
            )
        }
    )
    world = initial()
    WorldService(missions).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    with ledger.transaction() as c:
        canon = state(game)
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.nonvoid_baseline", canon)
    periods = OffDutyService(missions)
    strain = StrainService(periods, dice=D6(1))
    strain.configure(ADMIN, str(uuid4()), state(game).revision, "business_as_usual", frozenset())
    period = periods.begin(ADMIN, str(uuid4()))
    pending = [
        w
        for w in missions.owned_work(ADMIN)
        if w["off_duty_id"] == period["id"] and w["kind"] == "punishment"
    ]
    assert len(pending) == 3 and all(w["id"] not in {x["id"] for x in old_work} for w in pending)
    service = PunishmentService(ledger)
    causes = {tuple(service.get(ADMIN, w["id"])["causes"]) for w in pending}
    assert ("defeat_post_mission",) in causes
    assert any(set(x) == {"mission_failure", "dog_mission_end"} for x in causes)
    cycle = prepare_period(ledger, game, periods, period["id"])
    activate(cycle, game, period["id"])
    return game, missions, period, old_work, closed_rows


def test_returned_original_resumes_defeat_and_failure_dog_as_two_actual_punishments(ledger):
    game, missions, period, old_work, closed_rows = prepared_return(ledger)
    service = PunishmentService(ledger)
    actual = 0
    while True:
        pending = [
            w
            for w in missions.owned_work(ADMIN)
            if w["off_duty_id"] == period["id"] and w["kind"] == "punishment"
        ]
        if not pending:
            break
        data = service.get(ADMIN, pending[0]["id"])
        service.propose_scene(
            ADMIN,
            str(uuid4()),
            pending[0]["id"],
            data["revision"],
            data["game_revision"],
            "The actual original and current inflictor play this discipline scene",
        )
        for participant in (ADMIN, PLAYER):
            data = service.get(participant, pending[0]["id"])
            service.attest_scene(
                participant, str(uuid4()), pending[0]["id"], data["revision"], data["game_revision"]
            )
        data = service.get(ADMIN, pending[0]["id"])
        service.apply(
            ADMIN,
            str(uuid4()),
            pending[0]["id"],
            data["revision"],
            data["game_revision"],
            Details(kind="stimulant_injection"),
        )
        actual += 1
    assert actual == 2
    assert (
        next(x for x in state(game).obligations if x.details.get("cause") == "defeat").state
        == "fulfilled"
    )
    assert all(r in rows(ledger) for r in closed_rows)
    with ledger.engine.connect() as c:
        assert all(
            json.loads(r)["return_source_work"] in {x["id"] for x in old_work}
            for r in c.scalars(
                sa.select(t.m3["m3_required_work"].c.body_json).where(
                    t.m3["m3_required_work"].c.off_duty_id == period["id"],
                    t.m3["m3_required_work"].c.kind == "punishment",
                )
            )
        )


def test_forged_return_source_cannot_apply_or_change_the_original(ledger):
    game, missions, period, _, _ = prepared_return(ledger)
    task = next(
        w
        for w in missions.owned_work(ADMIN)
        if w["off_duty_id"] == period["id"] and w["kind"] == "punishment"
    )
    current = next(r for r in rows(ledger) if r["id"] == task["id"])
    before = state(game)
    body = json.loads(current["body_json"])
    body["return_proof"]["return_event"] = str(uuid4())
    with ledger.transaction() as c:
        event = ledger._audit(
            c, "synthetic:forged-work", str(uuid4()), "synthetic.forged_return_claim", {}
        )
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{
                    k: v
                    for k, v in current.items()
                    if k not in ("revision", "event_id", "body_json")
                },
                revision=current["revision"] + 1,
                event_id=event,
                body_json=json.dumps(body),
            )
        )
    with pytest.raises(WorkflowError, match="SOURCE_MISSION_DEBT_MISSING"):
        PunishmentService(ledger).get(ADMIN, task["id"])
    assert state(game) == before
