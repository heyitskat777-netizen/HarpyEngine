"""Real original Core mandatory Defeat: printed restraint, own body and shared Frame."""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_harpy_defeat import choose
from test_janus_battery import connected
from test_janus_battery import start as start_battery
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_harpy_bond_void as sin
from girlframe.engine import m3_janus
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.engine.m3_actors import frame_position
from girlframe.engine.m3_adjudication_state import CoreRestriction, Required
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_harpy_resources import assets as actual_assets
from girlframe.services.m3_adjudication import AdjudicationService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_harpy_bond_void import HarpyBondVoidService
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch, *, personal=False):
    """Admission and actual Handler damage, with no invented Harpy/source work."""
    game, worker, gateway, core, contact = connected(store, tmp_path, monkeypatch)
    from test_cast_service import change as cast_change

    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    casts = CastService(ActorService(MissionService(store)))
    battery = start_battery(game, core)
    tick(worker, gateway, 3)
    pass_tags(game)
    if any(x["kind"] == "mockingbird_risk" for x in game.choices(PLAYER)):
        answer(game, PLAYER, "mockingbird_risk")
    answer(
        game,
        PLAYER,
        "janus_select",
        options=("identities", "question"),
        text="Establish this actual private brain channel",
    )
    answer(
        game, OTHER, "janus_answer", text="My actual Core mind answers through this brain channel"
    )
    assert game.inspect(PLAYER, battery)["state"] == "complete"
    tick(worker, gateway, 5)
    assert next(x for x in state(game).neural_connections if x.id == contact).phase == "connected"
    cast_change(casts, ADMIN, "join", active_handler(state(game)))
    approved(store, game, tmp_path, monkeypatch, extra=(m3_janus.CORE, m3_janus.BATTERY, sin.RULE))
    if personal:
        with store.transaction() as c:
            prior = state(game)
            event = str(uuid4())
            prior = set_depth(prior, core, current_ref(prior, 2), 1, event)
            game.event(
                c,
                1,
                str(uuid4()),
                "synthetic.prior_actual_core_personal_bond",
                prior,
                event_id=event,
            )
    effects = HandlerPlayService(store)
    frame_assets = [x.id for x in actual_assets(state(game), core) if x.family == "frame"]
    assert frame_assets
    for number, asset in enumerate(frame_assets):
        grant = effects.start(
            ADMIN, f"actual-core-source-hit-{number}", state(game).revision, (core,)
        )
        effects.submit(
            ADMIN,
            f"actual-core-damage-{number}",
            grant["id"],
            state(game).revision,
            "mess",
            Effect(
                kind="damage",
                target=core,
                asset=asset,
                account="Actual damage reaches the original Core's shared Frame capability",
            ),
        )
    service = HarpyDefeatService(store, game)
    with store.engine.connect() as c:
        work = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.campaign_id == store.campaign_id,
                    t.m3["m3_required_work"].c.kind == "harpy_defeat",
                    t.m3["m3_required_work"].c.owner_id == str(OTHER.user_id),
                )
            )
            .mappings()
            .one()["id"]
        )
    return service, game, GameWorker(game), Gateway(), core, work, grant["id"]


def manual(service, game, worker, gateway, core, work, total):
    calls = game.dice.calls
    body = m3_janus.core(state(game), core)
    action = service.begin(OTHER, "actual-restrained-original-core-defeat", work, channel=900)[
        "action_id"
    ]
    with game.store.engine.connect() as c:
        required = Required.model_validate_json(
            json.dumps(game.action(c, action)["data"]["adjudication"])
        )
        assert isinstance(required.prohibition, CoreRestriction)
        assert required.actor == required.prohibition.core == core
        assert required.patient_controller == OTHER.user_id
        assert required.prohibition.tag == body.baseline_tags["restrained"]
        assert required.prohibition.source_event == body.state_event
        assert "surgery" not in required.prohibition.model_dump()
    tick(worker, gateway, 3)
    assert service.inspect(OTHER, action)["state"] == "awaiting_adjudication"
    assert game.dice.calls == calls
    with game.store.engine.connect() as c:
        row = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_choices"].c.action_id == action,
                    t.m2["m2_choices"].c.kind == "manual_adjudication",
                )
            )
            .mappings()
            .one()
        )
    adjudications = AdjudicationService(game.store)
    view = adjudications.get(ADMIN, row["id"])
    assert (
        view["prohibition_kind"] == "core_restriction"
        and "Restrained" in view["restriction_reason"]
    )
    reason = "The actual printed restraint forbids rolling; the source GM assigns this whole total"
    with pytest.raises(WorkflowError):
        adjudications.submit(
            OTHER, "core-cannot-assign-own-total", row["id"], view["revision"], total, reason
        )
    result = adjudications.submit(
        ADMIN, "actual-owned-core-manual-total", row["id"], view["revision"], total, reason
    )
    assert (
        adjudications.submit(
            ADMIN, "actual-owned-core-manual-total", row["id"], view["revision"], total, reason
        )
        == result
    )
    receipt = result["receipt"]
    assert receipt["faces"] is None and receipt["pre_total"] == total and receipt["heat"] == 0
    assert receipt["rng_source"] == "manual_adjudication" and game.dice.calls == calls
    for viewer in (PLAYER, OTHER, ADMIN):
        choose(service, game, viewer, "tag_window", options=("pass",))
    return action, receipt


def test_actual_restrained_core_manual_message_waits_for_true_girl_void_and_preserves_frame(
    ledger, tmp_path, monkeypatch
):
    service, game, worker, gateway, core, work, grant = ready(
        ledger, tmp_path, monkeypatch, personal=True
    )
    before = state(game)
    body = m3_janus.core(before, core)
    calls = game.dice.calls
    action, receipt = manual(service, game, worker, gateway, core, work, 8)
    girl = current_ref(state(game), 2)
    choose(
        service,
        game,
        OTHER,
        "harpy_defeat_select",
        options=("message",),
        fields={"girl": girl.token},
        text="The actual Core sends her final message while escaping",
    )
    escaped = m3_janus.core(state(game), core)
    assert not escaped.attached and not escaped.linked and escaped.custody == "free"
    assert escaped.cell is None and escaped.frame_cell == frame_position(
        before, body.frame_owner, body.frame_instance
    )
    assert escaped.body_vessel == body.body_vessel and escaped.alive
    assert all(x.phase == "ended" for x in state(game).neural_connections if x.battery == core)
    assert state(game).sheets == before.sheets
    assert state(game).placements == before.placements
    assert service.inspect(OTHER, action)["state"] != "complete"
    effect = next(x for x in sin.cases(state(game)) if x.source_action == action)
    assert effect.actor == girl and effect.controller == PLAYER.user_id and effect.harpy == core
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "harpy_bond_void")
    view = HarpyBondVoidService(game).view(PLAYER, effect.id)
    asset = next(x["id"] for x in view["assets"] if x["family"] == "girl")
    answer = ChoiceAnswer(
        options=(asset,), text="Actual Girl-owned Void from the original Core's final message"
    )
    with pytest.raises(WorkflowError):
        game.respond(OTHER, "core-cannot-answer-girl-void", row["id"], row["revision"], answer)
    result = game.respond(
        PLAYER, "actual-owned-core-message-void", row["id"], row["revision"], answer
    )
    assert (
        game.respond(PLAYER, "actual-owned-core-message-void", row["id"], row["revision"], answer)
        == result
    )
    actual = state(game)
    assert sin.get(actual, effect.id).phase == "complete"
    assert service.inspect(OTHER, action)["state"] == "complete"
    assert service.inspect(OTHER, action)["receipt"] == receipt and game.dice.calls == calls
    assert next(x for x in actual.handler_plays if x.id == grant).state == "complete"
    assert actual.sheets["3"] == before.sheets["3"] and actual.placements == before.placements
    assert [x for x in actual.sheets["2"].assets if x.family == "frame"] == [
        x for x in before.sheets["2"].assets if x.family == "frame"
    ]
    assert m3_janus.core(actual, core).heat == body.heat
    assert m3_janus.has_tag(m3_janus.core(actual, core), "restrained")


def test_actual_restrained_core_manual_death_marks_original_dead_and_tags_actual_killer(
    ledger, tmp_path, monkeypatch
):
    service, game, worker, gateway, core, work, _ = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    calls = game.dice.calls
    action, receipt = manual(service, game, worker, gateway, core, work, 4)
    killer = active_handler(before)
    choose(
        service,
        game,
        OTHER,
        "harpy_defeat_select",
        options=("death",),
        fields={"killer": killer.token, "tag": "Killed the actual original Core"},
        text="This actual original Core dies here",
    )
    assert m3_janus.core(state(game), core).alive
    choose(
        service,
        game,
        ADMIN,
        "harpy_killer_fact",
        flag=True,
        text="This original Handler caused the actual original Core's death",
    )
    actual = state(game)
    assert not m3_janus.core(actual, core).alive
    assert m3_janus.core(actual, core).attached == m3_janus.core(before, core).attached
    assert m3_janus.core(actual, core).linked == m3_janus.core(before, core).linked
    assert all(x.phase == "ended" for x in actual.neural_connections if x.battery == core)
    assert actual.handler_tags[-1].giver_actor == core
    assert actual.handler_tags[-1].label == "Killed the actual original Core"
    assert actual.sheets == before.sheets and actual.placements == before.placements
    assert service.inspect(OTHER, action)["receipt"] == receipt and game.dice.calls == calls
    assert service.inspect(OTHER, action)["state"] == "complete"
