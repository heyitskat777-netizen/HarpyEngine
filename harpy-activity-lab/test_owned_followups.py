"""Private Activity follow-ups against synthetic HarpyEngine campaigns."""

import asyncio
from uuid import uuid4

import mission_lab
import pytest
from handler_punishments import HandlerPunishments
from off_duty_followups import OffDutyFollowups
from owned_followups import OwnedFollowups
from strain_preparation import FACT_LABELS
from test_final_handler_workflows import (  # initializes the bundled engine path
    ADMIN,
    OTHER,
    PLAYER,
    bundled_registry,  # noqa: F401
    prepared,
    state,
)
from test_final_handler_workflows import (
    ledger as ledger,
)
from test_handler_plays import begin
from test_m2_game import Gateway
from test_strain_effect_service import selected
from test_strain_service import D6, ready
from test_world import initial
from test_world_service import ready as ready_world

from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError


def call(desk, who, card, answer, *, key=None):
    request = {
        k: v
        for k, v in card.items()
        if k in ("id", "revision", "work_revision", "action", "expected")
    }
    return desk.perform(who, key or str(uuid4()), request | {"answer": answer})


def off_duty(desk, actor, action, answer, *, key=None, visible=None):
    data = visible or desk.view(actor)
    request = {k: data[k] for k in ("period", "game_revision", "revision")}
    return desk.perform(actor, key or str(uuid4()), request | {"action": action, "answer": answer})


def test_delegated_off_duty_work_reassigns_attendance_and_consultation(ledger):
    cycle, game, _ = prepared(ledger)
    off = OffDutyFollowups(game)
    off_duty(off, ADMIN, "activate_period", {})
    off_duty(
        off,
        ADMIN,
        "set_handler_scene",
        {
            "kind": "punish",
            "summary": "Synthetic Handler assignment",
            "participants": [str(PLAYER.user_id)],
            "recipient": str(PLAYER.user_id),
            "context": None,
        },
    )
    off_duty(off, ADMIN, "acknowledge_handler_scene", {})
    off_duty(off, PLAYER, "acknowledge_handler_scene", {})
    desk = HandlerPunishments(game)
    work = next(row for row in desk.view(ADMIN) if row["action"] == "apply_off_duty_punishment")
    passing = next(row for row in work["forms"] if row["kind"] == "passing_responsibility")
    assert passing["fields"][0]["options"][0][0] == str(OTHER.user_id)
    call(
        desk,
        ADMIN,
        work,
        {"kind": "passing_responsibility", "delegate": str(OTHER.user_id)},
    )
    assert all(row["id"] != work["id"] for row in desk.view(ADMIN))
    scene = next(row for row in desk.view(OTHER) if row["action"] == "propose_punishment_scene")
    with pytest.raises(WorkflowError):
        call(desk, ADMIN, scene, {"summary": "Not the new owner"})
    call(
        desk,
        OTHER,
        scene,
        {"summary": "The two assigned pilots play the discipline scene"},
    )
    for actor in (OTHER, PLAYER):
        attendance = next(
            row for row in desk.view(actor) if row["action"] == "attest_punishment_scene"
        )
        call(desk, actor, attendance, {})
    work = next(row for row in desk.view(OTHER) if row["action"] == "apply_off_duty_punishment")
    call(
        desk,
        OTHER,
        work | {"action": "request_punishment_consult"},
        {
            "kind": "strict_regulations",
            "regulation": "Keep the archive sealed",
            "disclosed": True,
        },
    )
    review = next(row for row in desk.view(ADMIN) if row["action"] == "answer_punishment_consult")
    call(desk, ADMIN, review, {"approve": True})
    approved = next(row for row in desk.view(OTHER) if row["action"] == "apply_approved_punishment")
    call(desk, OTHER, approved, {})
    assert not desk.view(OTHER)
    assert state(game).regulations[-1].rule == "Keep the archive sealed"


def test_starting_strain_rolls_persist_and_effects_gate_activation(ledger):
    _, game = ready(ledger)
    mission_lab.enable_private_subsystems(game)
    desk = OffDutyFollowups(game)
    world = initial()
    desk.strain.world.initialize(
        ADMIN,
        "test-world",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    with ledger.transaction() as c:
        current = state(game)
        for sheet in current.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, ADMIN.user_id, "strain-test-baseline", "synthetic.baseline", current)
    period = desk.periods.begin(ADMIN, "prepare")
    assert desk.view(PLAYER) is None
    off_duty(desk, ADMIN, "strain_configure", {"scenario": "business_as_usual", "high": []})
    card = desk.view(ADMIN)["closing"]["strain"]["cards"][0]
    report = {
        "id": card["id"],
        "facts": dict.fromkeys(FACT_LABELS, False),
        "account": "Recorded synthetic triggers",
    }
    with pytest.raises(WorkflowError):
        off_duty(desk, PLAYER, "strain_prepare", report, visible=desk.view(ADMIN))
    off_duty(desk, ADMIN, "strain_prepare", report)
    desk.strain.service.dice = D6(1)
    original_view = desk.view(ADMIN)
    first = next(
        row
        for row in original_view["closing"]["strain"]["cards"]
        if row["label"].startswith("Void")
    )
    request = {k: first[k] for k in ("id", "revision")}
    key = str(uuid4())
    saved = off_duty(desk, ADMIN, "strain_roll", request, key=key, visible=original_view)
    assert off_duty(desk, ADMIN, "strain_roll", request, key=key, visible=original_view) == saved
    column = next(
        row
        for row in OffDutyFollowups(game).view(ADMIN)["closing"]["strain"]["cards"]
        if row["id"] == first["id"]
    )
    assert column["face"] == 1 and len(column["columns"]) == 2
    off_duty(
        desk,
        ADMIN,
        "strain_column",
        {"id": column["id"], "revision": column["revision"], "column": 1},
    )
    effect = next(
        row
        for row in desk.view(ADMIN)["closing"]["strain"]["cards"]
        if row["action"] == "strain_effect"
    )
    off_duty(
        desk,
        ADMIN,
        "strain_effect",
        {
            "id": effect["id"],
            "revision": effect["revision"],
            "effect": selected().model_dump(mode="json"),
        },
    )
    assert EffectService(desk.strain.service).get(ADMIN, effect["id"])["state"] == "resolved"
    assert desk.strain.service.dice.calls == 1
    assert not desk.view(ADMIN)["closing"]["strain"]["ready"]
    assert desk.periods.get(ADMIN, period["id"])["phase"] == "preparing"
    for track, face, column, effect_payload in (
        (
            "rebellion",
            1,
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="A new rebel group",
                target="city0",
                faction=Faction(
                    id="western-cell",
                    name="Western Cell",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Local dissent",
                ),
            ),
        ),
        (
            "budget",
            5,
            2,
            Choice(
                rule_id="strain.budget.low.5.2",
                account="Rooms reassigned",
                rooms=((2, 3),),
            ),
        ),
    ):
        request = next(row for row in state(game).strain.requests if row.track == track)
        desk.strain.service.dice.face = face
        off_duty(desk, ADMIN, "strain_roll", {"id": request.id, "revision": 1})
        off_duty(
            desk,
            ADMIN,
            "strain_column",
            {"id": request.id, "revision": 2, "column": column},
        )
        if track == "budget":
            request_fields = {"id": request.id + ":effect", "revision": 1, "values": {}}
            form = off_duty(desk, ADMIN, "strain_effect_fields", request_fields)
            assert {spec["key"] for spec in form["fields"]} == {
                "room:2",
                "room:3",
                "account",
            }
            with pytest.raises(WorkflowError):
                off_duty(
                    desk,
                    OTHER,
                    "strain_effect_fields",
                    request_fields,
                    visible=desk.view(ADMIN),
                )
            request_fields["values"] = {
                "room:2": ["0"],
                "room:3": ["0"],
                "account": "Rooms reassigned",
            }
            off_duty(desk, ADMIN, "strain_effect_submit", request_fields)
            continue
        off_duty(
            desk,
            ADMIN,
            "strain_effect",
            {
                "id": request.id + ":effect",
                "revision": 1,
                "effect": effect_payload.model_dump(mode="json"),
            },
        )
    assert desk.view(ADMIN)["closing"]["strain"]["ready"]
    off_duty(desk, ADMIN, "activate_period", {})
    assert desk.periods.get(ADMIN, period["id"])["phase"] == "active"


@pytest.mark.parametrize("kind", ("sedation", "frame_disassembly"))
@pytest.mark.parametrize("legacy", (False, True))
def test_punishment_materializes_an_owned_canonical_followup(ledger, kind, legacy, monkeypatch):
    _, game = ready_world(ledger, frame="PROJECT ANKOU" if kind == "sedation" else "JANUS")
    policy = ledger.policy
    ledger.policy = policy.model_copy(
        update={
            "m3_approval": policy.m3_approval.model_copy(
                update={"subsystems": policy.m3_approval.subsystems | {"plays"}}
            )
        }
    )
    with ledger.transaction() as c:
        current = state(game)
        sheet = current.sheets[str(PLAYER.user_id)]
        if kind == "sedation":
            for identity in sheet.identities[2:]:
                identity.marked = True
            details = {"identities": [identity.id for identity in sheet.identities[:2]]}
        else:
            frames = [asset for asset in sheet.assets if asset.family == "frame"]
            for asset in frames[1:]:
                asset.void = True
            details = {"asset": frames[0].id}
        game.event(c, ADMIN.user_id, "before-punishment", "synthetic.baseline", current)
    service = HandlerPlayService(ledger)
    source = begin(service, game)
    current = state(game)
    service.submit(
        ADMIN,
        "file-punishment",
        source,
        current.revision,
        "punish",
        Effect(
            kind="punish",
            account="Synthetic instruction",
            target=current_ref(current, PLAYER.user_id),
            executor=current_ref(current, ADMIN.user_id),
        ),
    )
    desk = HandlerPunishments(game)
    if legacy:
        from girlframe.services import m3_ankou_feedback_sequences, m3_punishments

        if kind == "sedation":
            monkeypatch.setattr(m3_ankou_feedback_sequences, "start", lambda *args, **kwargs: None)
        else:
            original_related = m3_punishments.related
            monkeypatch.setattr(
                m3_punishments,
                "related",
                lambda *args: original_related(*args) if args[6] != "void_threshold" else None,
            )
    for actor, step, answer in (
        (ADMIN, "instruct", {"kind": kind, **details}),
        (ADMIN, "scene", "The two original actors record what happened"),
        (PLAYER, "attest", True),
        (ADMIN, "execute", "Apply the selected effect"),
    ):
        call(
            desk,
            actor,
            next(row for row in desk.view(actor) if row["action"] == step),
            answer,
        )
    if legacy:
        import json

        import sqlalchemy as sa

        from girlframe.database import tables
        from girlframe.services.m3_work import related

        work = tables.m3["m3_required_work"]
        legacy_id = str(uuid4())
        with ledger.transaction() as c:
            source = (
                c.execute(
                    sa.select(work).where(
                        work.c.campaign_id == ledger.campaign_id,
                        work.c.kind == "punishment",
                        work.c.state == "resolved",
                    )
                )
                .mappings()
                .one()
            )
            assert json.loads(source["body_json"])["punishment"]["kind"] == kind
            token = "ankou_feedback" if kind == "sedation" else "void_threshold_check"
            related(
                c,
                ledger,
                dict(source),
                legacy_id,
                PLAYER.user_id,
                PLAYER.user_id,
                "punishment_" + token,
                dict(
                    kind=token,
                    owner=PLAYER.user_id,
                    source_pdf=84 if kind == "sedation" else 19,
                    details={},
                    immediate=True,
                    source_work=source["id"],
                ),
                source["event_id"],
            )
        card = next(row for row in desk.view(PLAYER) if row["id"] == legacy_id)
        with pytest.raises(WorkflowError):
            call(desk, OTHER, card, {})
        key = str(uuid4())
        receipt = call(desk, PLAYER, card, {}, key=key)
        assert call(desk, PLAYER, card, {}, key=key) == receipt
        assert len(receipt["followups"]) == 1
        assert not any(row["id"] == legacy_id for row in desk.view(PLAYER))
    followups = OwnedFollowups(game, lambda: {900: ("test", "Synthetic scene")})
    if kind == "sedation":
        card = next(row for row in followups.view(PLAYER) if row["action"] == "feedback_activate")
        assert not followups.view(OTHER)
        call(
            followups,
            PLAYER,
            card,
            {
                "channel": "900",
                "account": "Continue the actual Feedback in the joined scene",
            },
        )
        assert asyncio.run(SourcePauseWorker(game).tick(Gateway()))
        card = next(row for row in followups.view(PLAYER) if row["action"] == "feedback_choose")
        target = current_ref(state(game), OTHER.user_id).token
        call(
            followups,
            PLAYER,
            card,
            {
                "choice": "purpose",
                "target": target,
                "account": "Ask the peer for purpose",
            },
        )
        prompt = next(row for row in followups.view(OTHER) if row["action"] == "feedback_purpose")
        with pytest.raises(WorkflowError):
            call(
                followups,
                ADMIN,
                prompt,
                {"given": "yes", "account": "Wrong participant"},
            )
        call(
            followups,
            OTHER,
            prompt,
            {"given": "yes", "account": "Hold the western relay"},
        )
        card = next(row for row in followups.view(PLAYER) if row["action"] == "feedback_identity")
        replace = state(game).sheets[str(PLAYER.user_id)].identities[0].id
        call(followups, PLAYER, card, {"replace": replace})
        assert "Hold the western relay" in {
            identity.name for identity in state(game).sheets[str(PLAYER.user_id)].identities
        }
        assert not followups.view(PLAYER)
    else:
        card = next(row for row in followups.view(PLAYER) if row["action"] == "resolve_void")
        assert not followups.view(OTHER)
        op = "propose_occupancy"
        assert op in {entry["id"] for entry in card["operations"]}
        answer = {
            "operation": op,
            "values": {
                "mode": "outside_frame",
                "account": "The pilot was outside the cockpit",
            },
        }
        with pytest.raises(WorkflowError):
            call(followups, OTHER, card, answer)
        call(followups, PLAYER, card, answer)
        reopened = next(row for row in followups.view(ADMIN) if row["action"] == "resolve_void")
        assert "confirm_occupancy" in {entry["id"] for entry in reopened["operations"]}
        call(
            followups,
            ADMIN,
            reopened,
            {
                "operation": "confirm_occupancy",
                "values": {"account": "The Handler observed the pilot outside"},
            },
        )
        saved = followups.void.get(PLAYER, card["id"])
        assert saved["stage"] == "abandoned"
        resolution = next(row for row in followups.view(ADMIN) if row["action"] == "resolve_void")
        frame = followups.void.get(ADMIN, card["id"])["frame_assets"]
        call(
            followups,
            ADMIN,
            resolution,
            {
                "operation": "abandoned",
                "values": {
                    "name": "Western Relay Anomaly",
                    "class": "dormant",
                    "types": ["sentinel"],
                    "core": [frame[0]["id"]],
                    "weakness": "It responds to the original callsign",
                    "account": "The Handler recorded the abandoned Frame's transformation",
                },
            },
        )
        assert followups.void.get(PLAYER, card["id"])["stage"] == "escaped"
