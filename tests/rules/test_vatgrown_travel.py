"""One actual attempt/movement/disclosure/Punishment normal; deferred final P1."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_vatgrown_plays import ready

from girlframe.database import tables as t
from girlframe.discord_adapter import m3_movement as movement_native
from girlframe.discord_adapter import m3_vatgrown_travel as native
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine import m3_vatgrown_travel as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.m3_vatgrown_travel import (
    VatgrownTravelService,
    prove_chaperoned,
    prove_violation_source,
)
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_actual_attempt_preserves_position_then_private_disclosure_optional_punishment_and_move(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    travel = VatgrownTravelService(game)
    actor = current_ref(state(game), 2)
    before = state(game)
    pose = next(value for value in before.placements if value.actor == actor)
    # The source is explicit conduct evidence, never an implicit permission exception.
    with pytest.raises(WorkflowError, match="UNCHAPERONED_SOURCE_REQUIRED"):
        MovementService(game).move(
            PLAYER,
            str(uuid4()),
            before.revision,
            900,
            actor,
            (1, 0),
            account="I propose to leave base alone",
        )
    assert state(game).model_dump_json() == before.model_dump_json()
    request = (
        PLAYER,
        "actual-unchaperoned-attempt",
        900,
        before.revision,
        actor,
        (1, 0),
    )
    account = "I actually attempt to leave the Foundation base alone without a chaperone"
    result = travel.attempt(*request, account=account)
    assert travel.attempt(*request, account=account) == result
    identity = result["id"]
    after_attempt = state(game)
    assert not result["moved"]
    assert next(value for value in after_attempt.placements if value.actor == actor) == pose
    value = travel.view(PLAYER, identity)
    assert value["performed_event"] is None and value["can_disclose"]
    for viewer in (ADMIN, OTHER):
        with pytest.raises(WorkflowError):
            travel.view(viewer, identity)
    with ledger.engine.connect() as c:
        assert travel._tasks(c, PLAYER)[0]["pending"]
        assert not travel._tasks(c, ADMIN)
    captured = []
    monkeypatch.setattr(native, "viewer_from_interaction", lambda interaction: PLAYER)

    async def reply(interaction, text, view=None):
        captured.append(view)

    monkeypatch.setattr(native, "reply", reply)
    interaction = SimpleNamespace(user=SimpleNamespace(id=2), channel_id=999)
    asyncio.run(native.open_vatgrown_travel(interaction, travel, identity))
    assert native.clean(account) in "".join(page.body for page in captured[-1].pages())
    unchanged = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        travel.perform(PLAYER, str(uuid4()), identity, before.revision)
    assert state(game).model_dump_json() == unchanged
    disclosure = (
        PLAYER,
        "actual-travel-disclosure",
        identity,
        state(game).revision,
        "I explicitly tell the actual Handler about my original attempt",
    )
    travel.disclose(*disclosure)
    assert travel.view(ADMIN, identity)["can_judge"]
    with pytest.raises(WorkflowError):
        travel.view(OTHER, identity)
    # Punishment is the real Handler's optional judgment about the attempt, before travel.
    judged = controls.judge_violation(
        ADMIN,
        "actual-optional-travel-punishment",
        result["violation"],
        state(game).revision,
        True,
        "I choose a real Punishment for the disclosed attempt",
    )
    discipline = vat.find(state(game), vat.Discipline, judged["punishment"])
    role = RolePunishmentService(game)

    def change(viewer, **values):
        return role.change(
            viewer,
            str(uuid4()),
            discipline.case,
            role.get(viewer, discipline.case)["revision"],
            **values,
        )

    details = Details(kind="quality_time", tag="Actual unchaperoned conduct consequence")
    change(
        ADMIN, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(ADMIN, scene="The actual Handler performs the chosen Quality Time at base")
    change(PLAYER, attest=True)
    change(ADMIN, execute=True, account="Actual performed source Punishment")
    assert any(tag.label == details.tag for tag in state(game).sheets["2"].tags)
    move = (PLAYER, "actual-source-bound-departure", identity, state(game).revision)
    moved = travel.perform(*move)
    assert travel.perform(*move) == moved
    actual_pose = next(value for value in state(game).placements if value.actor == actor)
    assert actual_pose.girl_cell == (1, 0) and actual_pose.frame_cell == pose.frame_cell
    assert actual_pose.vessel_id == pose.vessel_id
    assert actual_pose.frame_instance == pose.frame_instance
    final = travel.view(PLAYER, identity)
    assert final["performed_event"] and final["judgment_event"] and not final["can_perform"]
    with ledger.engine.connect() as c:
        violation = vat.find(state(game), vat.Violation, result["violation"])
        assert prove_violation_source(game, c, state(game), violation).id == identity
        assert not travel._tasks(c, PLAYER)[0]["pending"]
    asyncio.run(native.open_vatgrown_travel(interaction, travel, identity))
    assert "Actual movement: Recorded" in "".join(page.body for page in captured[-1].pages())
    assert len(rules.records(state(game), rules.Attempt)) == 1
    assert len(rules.records(state(game), rules.Movement)) == 1


def test_actual_native_companion_authorizes_both_real_moves_with_private_receipt_and_retry(
    ledger, tmp_path, monkeypatch
):
    game, _, _, _ = ready(ledger, tmp_path, monkeypatch)
    source = VatgrownTravelService(game)
    actor, companion = current_ref(state(game), 2), current_ref(state(game), 3)
    before = state(game)
    poses = {pose.actor.token: pose for pose in before.placements}
    captured = []
    viewers = {2: PLAYER, 3: OTHER}
    for module in (native, movement_native):
        monkeypatch.setattr(
            module, "viewer_from_interaction", lambda current: viewers[current.user.id]
        )

    async def reply(interaction, text, view=None):
        captured.append((text, view))

    monkeypatch.setattr(native, "reply", reply)
    monkeypatch.setattr(movement_native, "reply", reply)
    owner = SimpleNamespace(id=84001, user=SimpleNamespace(id=2), channel_id=900)
    recipient = SimpleNamespace(id=84002, user=SimpleNamespace(id=3), channel_id=999)
    asyncio.run(movement_native.open_movement(owner, MovementService(game)))
    movement_form = captured[-1][1]
    owner_account = "I propose to walk with this actual companion throughout the trip outside base"
    proposed = asyncio.run(
        movement_form.submit_action(
            owner,
            dict(
                actor=(actor.token,),
                mode=("body",),
                x=("1",),
                y=("0",),
                intent=("chaperoned",),
                companion=(companion.token,),
                account=owner_account,
            ),
        )
    )
    assert "Both move when" in proposed
    assert state(game).placements == before.placements
    journey = rules.records(state(game), rules.ChaperonedProposal)[0]
    assert journey.owner.actor == actor and journey.companion_snapshot.actor == companion
    with pytest.raises(WorkflowError):
        source.view(ADMIN, journey.id)
    with ledger.engine.connect() as c:
        assert not source._tasks(c, PLAYER)[0]["pending"]
        assert source._tasks(c, OTHER)[0]["pending"]
        assert not source._tasks(c, ADMIN)
    asyncio.run(native.open_vatgrown_travel(owner, source, journey.id))
    assert "cancel" in dict(captured[-1][1].fields[0].options)
    unchanged = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        source.respond_chaperoned(
            PLAYER,
            str(uuid4()),
            journey.id,
            state(game).revision,
            accept=True,
            frame=False,
            account="I cannot authorize another controller's body",
        )
    with pytest.raises(WorkflowError):
        source.respond_chaperoned(
            OTHER,
            str(uuid4()),
            journey.id,
            before.revision,
            accept=True,
            frame=False,
            account="A stale card must not move either body",
        )
    assert state(game).model_dump_json() == unchanged
    asyncio.run(native.open_vatgrown_travel(recipient, source, journey.id))
    response_form = captured[-1][1]
    assert native.clean(owner_account) in "".join(page.body for page in response_form.pages())
    companion_account = "I walk with the original Vatgrown and accompany them throughout this trip"
    values = dict(operation=("accept",), mode=("body",), account=companion_account)
    result = asyncio.run(response_form.submit_action(recipient, values))
    assert "Both actual original bodies moved" in result
    committed = state(game)
    assert asyncio.run(response_form.submit_action(recipient, values)) == result
    assert state(game).model_dump_json() == committed.model_dump_json()
    for actual in (actor, companion):
        original = poses[actual.token]
        moved = next(pose for pose in committed.placements if pose.actor == actual)
        assert moved.girl_cell == (1, 0) and moved.frame_cell == original.frame_cell
        assert moved.vessel_id == original.vessel_id and moved.mode == original.mode
        assert moved.frame_instance == original.frame_instance
    assert rules.records(committed, rules.ChaperonedProposal) == (journey,)
    assert len(rules.records(committed, rules.JointMovement)) == 1
    assert tuple(vat.records(committed, vat.Violation)) == tuple(vat.records(before, vat.Violation))
    assert committed.role_punishments == before.role_punishments
    with ledger.engine.connect() as c:
        assert prove_chaperoned(game, c, committed, journey.id) == journey
        events = c.execute(
            sa.select(t.events.c.payload_json).where(
                t.events.c.campaign_id == ledger.campaign_id,
                t.events.c.kind == "m3.physical_moved",
            )
        ).scalars()
        assert (
            sum(json.loads(payload).get("vatgrown_journey") == journey.id for payload in events)
            == 1
        )
        assert all(row["phase"] == "resolved" for row in source._tasks(c, OTHER))
    asyncio.run(native.open_vatgrown_travel(recipient, source, journey.id))
    readback = "".join(page.body for page in captured[-1][1].pages)
    assert native.clean(owner_account) in readback and native.clean(companion_account) in readback
    assert "Journey result: accepted" in readback
