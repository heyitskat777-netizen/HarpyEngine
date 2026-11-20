"""Mission-time acceptance against the actual offline mission and Play workflow."""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_campaign_time import ANCHOR, NIGHT, booked
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_service import service as setup_missions

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput
from girlframe.scenes.campaign_time import Anchor, Cut, ScenePlan
from girlframe.scenes.mission_timing import Deadline, Option, Options, Rejoin, SequenceStart
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.m2_game import GameService
from girlframe.services.mission_timing import MissionTimingService
from girlframe.services.onboarding import WorkflowError

START, CUTOFF = 18 * 60 + 20, 18 * 60 + 40
DEPARTURE = "The evacuation shuttle has left."


def setup(store, *, boundary="before", consequence=DEPARTURE, both=False):
    missions, game = setup_missions(store)
    participants = (2, 3) if both else (2,)
    offered = missions.offer(ADMIN, "offer-timed", "Synthetic evacuation", participants)
    mission = missions.respond(PLAYER, "accept-timed", offered["id"], offered["revision"], "accept")
    if both:
        mission = missions.respond(
            OTHER, "accept-timed-other", mission["id"], mission["revision"], "accept"
        )
    mission = missions.start(ADMIN, "dispatch-timed", mission["id"], mission["revision"])
    timeline = CampaignTimeService(store)
    anchor = timeline.initialize(ADMIN, "campaign-timed", ANCHOR)["receipt"]
    scene = booked(timeline, game, anchor, 900, (2, 3))
    timing = MissionTimingService(store)
    assert "mission_timing" not in timeline.projection(PLAYER)
    opened = timing.open(
        ADMIN,
        "open-clock",
        mission["id"],
        mission["revision"],
        900,
        scene,
        anchor,
        SequenceStart(
            minute=START,
            deadline=Deadline(
                minute=CUTOFF,
                boundary=boundary,
                label="Evacuation closes",
                consequence=consequence,
            ),
        ),
    )
    return timing, timeline, opened, missions, mission, game


def option(label, minutes, *, who=2, estimated=False, play=None):
    return Option(
        id=str(uuid4()), pilot=who, label=label, minutes=minutes, estimated=estimated, play=play
    )


def publish(timing, clock, *options, mode="single"):
    return timing.publish_options(
        ADMIN, str(uuid4()), clock["id"], clock["receipt"], Options(mode=mode, available=options)
    )


@pytest.mark.parametrize(
    "boundary,selected,minute,status,consequence",
    (
        ("before", "tunnel", 1115, "open", False),
        ("before", "escort", 1125, "missed", True),
        ("before", "exact", 1120, "missed", True),
        ("by", "exact", 1120, "at_deadline", False),
    ),
)
def test_stated_routes_and_deadline_boundaries(
    ledger, boundary, selected, minute, status, consequence
):
    timing, timeline, opened, missions, mission, game = setup(ledger, boundary=boundary)
    routes = {
        "tunnel": option("Tunnel", 15),
        "escort": option("Escort", 25, estimated=True),
        "exact": option("Service entrance", 20),
    }
    menu = publish(timing, opened, *routes.values())
    view = timeline.projection(PLAYER)["mission_timing"]
    assert view["minute"] == START
    assert view["deadline"]["boundary"] == boundary
    assert {row["minutes"] for row in view["options"]} == {15, 20, 25}
    assert next(row for row in view["options"] if row["label"] == "Escort")["estimated"]
    quoted = next(row for row in view["options"] if row["id"] == routes[selected].id)
    assert (quoted["arrival_minute"], quoted["projected_deadline_status"]) == (minute, status)
    assert "mission_timing" not in timeline.projection(OTHER)
    with pytest.raises(WorkflowError, match="joined and dispatched"):
        timing.choose(
            OTHER, "foreign-timed-choice", opened["id"], menu["receipt"], routes[selected].id
        )
    cut = Cut(target=Anchor(chapter="After mission", position=NIGHT))
    assert {"kind": "timed_sequence_active", "id": opened["id"]} in (
        timeline.preview_cut(ADMIN, cut)["blockers"]
    )
    with pytest.raises(WorkflowError, match="active timed sequence"):
        missions.end(ADMIN, "premature-mission-end", mission["id"], mission["revision"], True)
    with pytest.raises(WorkflowError, match="active timed sequence"):
        game.close_scene(ADMIN, "premature-close", 900)

    request = (PLAYER, "route-choice", opened["id"], menu["receipt"], routes[selected].id)
    prior_state = state(game)
    result = timing.choose(*request)
    assert result["minute"] == minute and result["deadline_status"] == status
    assert result.get("consequence") == (DEPARTURE if consequence else None)
    ledger.engine.dispose()
    assert MissionTimingService(ledger).choose(*request) == result
    with pytest.raises(WorkflowError, match="STALE_TIMING"):
        timing.choose(
            PLAYER, "duplicate-new-delivery", opened["id"], menu["receipt"], routes[selected].id
        )

    if status in ("missed", "at_deadline"):
        next_option = option("Signal", 1)
        next_menu = publish(timing, result, next_option)
        onward = timing.choose(PLAYER, "onward", opened["id"], next_menu["receipt"], next_option.id)
        assert onward["deadline_status"] == "missed"
        assert onward.get("consequence") == (None if consequence else DEPARTURE)
        result = onward
    assert state(game) == prior_state
    assert timeline.projection(PLAYER)["anchor"] == ANCHOR.model_dump()
    closed = timing.close(ADMIN, "close-timed-sequence", opened["id"], result["receipt"])
    assert closed["status"] == "closed" and "mission_timing" not in timeline.projection(PLAYER)
    game.close_scene(ADMIN, "close-timed-scene", 900)


def test_timed_root_roll_and_required_responses_charge_once_after_reconnect(ledger):
    timing, timeline, opened, _, _, _ = setup(ledger)
    dice = Dice()
    game = GameService(ledger, dice=dice)
    route = option("Tunnel under pressure", 15, play="keep_your_head")
    menu = publish(timing, opened, route)
    selection = timing.choose(PLAYER, "select-timed-play", opened["id"], menu["receipt"], route.id)
    assert selection["status"] == "play_selected" and selection["minute"] == START
    prepared = PlayInput(
        play="keep_your_head",
        context="Commit to the tunnel crossing",
        trigger_confirmed=True,
        heat=0,
    )
    action = game.begin(
        PLAYER,
        "timed-play",
        900,
        state(game).sheets["2"].revision,
        prepared,
        timing_selection=selection["receipt"],
    )["action_id"]
    assert timeline.projection(PLAYER)["mission_timing"]["minute"] == START
    with pytest.raises(WorkflowError, match="LOCK_NOT_ACKNOWLEDGED"):
        game.roll(PLAYER, "early-timed-roll", action)
    assert dice.calls == 0
    with pytest.raises(WorkflowError, match="original attached Play"):
        timing.withdraw_play(PLAYER, "withdraw-active", opened["id"], selection["receipt"])

    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    saved = game.inspect(PLAYER, action)["receipt"]
    assert game.inspect(PLAYER, action)["state"] == "tag_window"
    assert timeline.projection(PLAYER)["mission_timing"]["minute"] == 1115
    ledger.engine.dispose()
    resumed = GameService(ledger, dice=dice)
    assert resumed.roll(PLAYER, "transport-retry", action)["receipt"] == saved
    pass_tags(resumed)
    answer(resumed, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    assert resumed.inspect(PLAYER, action)["state"] != "complete"
    during_followup = timeline.projection(ADMIN)["mission_timing"]
    with pytest.raises(WorkflowError, match="pending Play"):
        publish(
            timing,
            {"id": during_followup["id"], "receipt": during_followup["revision"]},
            option("Push on", 1),
        )
    answer(resumed, ADMIN, "handler_keep", flag=True, text="The tunnel is clear.")
    assert resumed.inspect(PLAYER, action)["state"] == "complete"
    assert dice.calls == 1
    assert timeline.projection(PLAYER)["mission_timing"]["minute"] == 1115

    with ledger.engine.connect() as c:
        evidence = list(
            c.scalars(
                sa.select(t.events.c.payload_json).where(
                    t.events.c.campaign_id == ledger.campaign_id,
                    t.events.c.kind == "timeline.mission_clock",
                    sa.func.json_extract(t.events.c.payload_json, "$.transition") == "advanced",
                )
            )
        )
    assert len(evidence) == 1
    assert json.loads(evidence[0])["play_receipt"] == saved["id"]


def test_uncertain_timing_saves_ruling_and_requires_fresh_player_commitment(ledger, monkeypatch):
    timing, timeline, opened, _, _, game = setup(ledger, consequence=None)
    calendar = timeline.projection(ADMIN)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)
    with pytest.raises(WorkflowError, match="active timed sequence"):
        timeline.schedule(
            ADMIN,
            "move-active-timed-scene",
            900,
            scene["id"],
            scene["revision"],
            calendar["anchor_receipt"],
            ScenePlan(start=NIGHT, end=NIGHT, participants=(2, 3)),
        )
    unknown = option("Uncharted service access", None)
    menu = publish(timing, opened, unknown)
    args = (PLAYER, "request-duration", opened["id"], menu["receipt"], unknown.id)
    pending = timing.choose(*args)
    assert pending["status"] == "ruling_required" and pending["reason"] == "unknown_duration"
    assert timing.choose(*args) == pending
    assert timeline.projection(ADMIN)["mission_timing"]["ruling"]["option"] == unknown.id

    known = option("Surveyed service access", 25)
    menu = publish(timing, pending, known)
    pending = timing.choose(PLAYER, "needs-consequence", opened["id"], menu["receipt"], known.id)
    assert pending["reason"] == "unknown_consequence" and pending["minute"] == START
    fixed = timing.declare_consequence(
        ADMIN, "deadline-ruling", opened["id"], pending["receipt"], DEPARTURE
    )
    assert fixed["minute"] == START
    assert timeline.projection(PLAYER)["mission_timing"]["minute"] == START
    with pytest.raises(WorkflowError, match="STALE_TIMING"):
        timing.choose(PLAYER, "old-form", opened["id"], menu["receipt"], known.id)
    commit = (PLAYER, "fresh-confirmation", opened["id"], fixed["receipt"], known.id)
    record = timing._record

    def fail_before_commit(*args, **kwargs):
        record(*args, **kwargs)
        raise RuntimeError("Simulated failure after the clock event was written")

    with monkeypatch.context() as patch:
        patch.setattr(timing, "_record", fail_before_commit)
        with pytest.raises(RuntimeError, match="Simulated failure"):
            timing.choose(*commit)
    assert timeline.projection(PLAYER)["mission_timing"]["minute"] == START
    result = timing.choose(*commit)
    assert result["minute"] == 1125 and result["consequence"] == DEPARTURE


def test_parallel_actions_share_anchor_and_handler_commits_explicit_rejoin(ledger):
    timing, timeline, opened, _, _, _ = setup(ledger, both=True)
    first, second = option("Hold passage", 10), option("Disable blast door", 15, who=3)
    menu = publish(timing, opened, first, second, mode="parallel")
    assert second.label not in json.dumps(timeline.projection(PLAYER))
    first_saved = timing.choose(PLAYER, "parallel-first", opened["id"], menu["receipt"], first.id)
    ledger.safety(OTHER, "pause-timed", ledger.status(OTHER)["revision"], pause=True)
    assert first_saved == timing.choose(
        PLAYER, "parallel-first", opened["id"], menu["receipt"], first.id
    )
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        timing.choose(OTHER, "parallel-second", opened["id"], menu["receipt"], second.id)
    assert timeline.projection(PLAYER)["mission_timing"]["minute"] == START
    ledger.safety(OTHER, "resume-timed", ledger.status(OTHER)["revision"], pause=False)
    second_saved = timing.choose(OTHER, "parallel-second", opened["id"], menu["receipt"], second.id)
    assert first_saved["minute"] == second_saved["minute"] == START
    rejoin = Rejoin(minute=START + 18, account="The doors cycle after both actions finish.")
    with pytest.raises(WorkflowError, match="STALE_TIMING"):
        timing.resolve_parallel(
            ADMIN, "parallel-stale", opened["id"], first_saved["receipt"], rejoin
        )
    with pytest.raises(WorkflowError, match="appointed campaign Handler"):
        timing.resolve_parallel(
            PLAYER, "parallel-unauthorized", opened["id"], second_saved["receipt"], rejoin
        )
    result = timing.resolve_parallel(
        ADMIN, "parallel-rejoin", opened["id"], second_saved["receipt"], rejoin
    )
    assert result["minute"] == 1118 and result["deadline_status"] == "open"
    assert timeline.projection(OTHER)["mission_timing"]["minute"] == 1118
    assert timeline.projection(OTHER)["anchor"] == ANCHOR.model_dump()
