"""Actual on-scene Punishment and linked work complete the original social Play."""

import pytest
import sqlalchemy as sa
from test_beneath_service import ready, rolled, start
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.database import tables as t
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError


def pending(store):
    game, worker, gateway, identity = rolled(store, (6, 6))
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("tag", "punish"),
        fields={"tag": "PRIVATE_SOCIAL_TAG"},
        text="Actual superior's confrontation",
    )
    choice = game.choices(PLAYER)[0]
    assert choice["kind"] == "beneath_punishment"
    decision = game.decision(PLAYER, choice["id"])
    return PunishmentService(store), game, worker, gateway, identity, decision["body"]["work_id"]


def apply(svc, work, details):
    data = svc.get(PLAYER, work)
    return svc.apply(
        PLAYER, "actual-social-punishment", work, data["revision"], data["game_revision"], details
    )


def test_actual_minor_punishment_finishes_social_play_once_and_releases_chat(ledger):
    svc, game, worker, gateway, identity, work = pending(ledger)
    assert game.inspect(PLAYER, identity)["state"] == "awaiting_choices"
    data = svc.get(PLAYER, work)
    assert data["causes"] == ["put_someone_beneath_you"]
    details = Details(kind="quality_time", tag="PRIVATE_REAL_PUNISHMENT_TAG")
    outcome = svc.apply(
        PLAYER, "one-social-punishment", work, data["revision"], data["game_revision"], details
    )
    assert (
        svc.apply(
            PLAYER, "one-social-punishment", work, data["revision"], data["game_revision"], details
        )
        == outcome
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    assert state(game).sheets["3"].tags[-1].label == "PRIVATE_REAL_PUNISHMENT_TAG"
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        assert "PRIVATE_REAL" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))


def test_actual_moderate_punishment_needs_exact_handler_consultation_inside_held_scene(ledger):
    svc, game, _, _, identity, work = pending(ledger)
    asset = next(x for x in state(game).sheets["3"].assets if x.family == "frame")
    details = Details(kind="frame_disassembly", asset=asset.id)
    with pytest.raises(WorkflowError, match="HANDLER_CONSULT_REQUIRED"):
        apply(svc, work, details)
    data = svc.get(PLAYER, work)
    consultation = svc.consult(
        PLAYER, "social-consult", work, data["revision"], data["game_revision"], details
    )
    pending_review = svc.get(ADMIN, consultation["id"])
    svc.answer_consultation(
        ADMIN, "social-handler-answer", consultation["id"], pending_review["revision"], True
    )
    assert game.inspect(PLAYER, identity)["state"] == "awaiting_choices"
    apply(svc, work, details)
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert not any(x.id == asset.id for x in state(game).sheets["3"].assets)


def test_last_girl_asset_beating_waits_for_actual_frame_context_followup(ledger):
    svc, game, _, _, identity, work = pending(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        assets = [x for x in canon.sheets["3"].assets if x.family == "girl"]
        for asset in assets[1:]:
            asset.damaged = True
        game.event(c, 1, "synthetic-last-girl-asset", "synthetic.state", canon)
    apply(svc, work, Details(kind="beating", asset=assets[0].id, tag="Beaten"))
    assert game.inspect(PLAYER, identity)["state"] == "awaiting_choices"
    table = t.m3["m3_required_work"]
    with ledger.engine.connect() as c:
        child = c.scalar(
            sa.select(table.c.id)
            .where(table.c.campaign_id == ledger.campaign_id, table.c.kind == "punishment_helpless")
            .limit(1)
        )
    data = svc.get(ADMIN, child)
    svc.resolve_helpless(
        ADMIN,
        "actual-social-frame-context",
        child,
        data["revision"],
        data["game_revision"],
        piloting=False,
        evidence="Actual out-of-Frame context",
    )
    assert state(game).sheets["3"].helpless_against == (2,)
    assert game.inspect(OTHER, identity)["state"] == "complete"


def test_low_counter_punishment_can_use_only_its_own_actual_followed_superior_order(ledger):
    game, worker, gateway = ready(ledger, (1, 1))
    order = game.issue_order(ADMIN, "real-counter-order", 900, 3, "Punish the other Girl")
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("obedient",))
    tick(worker, gateway, 5)
    identity = start(game)
    tick(worker, gateway, 3)
    pass_tags(game)
    projection = game.decision(OTHER, game.choices(OTHER)[0]["id"])
    assert projection["beneath"]["orders"][0]["id"] == order["order_id"]
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("punish",),
        fields={"order": order["order_id"]},
        text="Actual ordered counter-Punishment",
    )
    work = game.decision(OTHER, game.choices(OTHER)[0]["id"])["body"]["work_id"]
    svc = PunishmentService(ledger)
    data = svc.get(OTHER, work)
    svc.apply(
        OTHER,
        "actual-ordered-counter",
        work,
        data["revision"],
        data["game_revision"],
        Details(kind="quality_time", tag="Actual ordered Tag"),
    )
    assert state(game).sheets["2"].tags[-1].giver == 3
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
