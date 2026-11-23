"""M4 acceptance through native messages, mission offers, and actual saved choices."""

import asyncio
import json
from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

import discord
import pytest
import sqlalchemy as sa
from test_actor_service import pc_ref
from test_actor_service import ready as ready_cast
from test_campaign_opening import complete, ready_plan
from test_canon import SECRET, UNSHARED
from test_cast_service import change as change_cast
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, state, tick
from test_mission_service import service as setup_missions
from test_session_zero import FACILITATOR, OUTSIDE

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.bot import ReadOnlyDiscordBot
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.scenes.campaign_time import (
    Anchor,
    Cut,
    Dependency,
    LateSubmission,
    Position,
    ScenePlan,
)
from girlframe.scenes.canon import Proposal, WorldFact
from girlframe.services import campaign_time_history as calendar
from girlframe.services import canon_history as history
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.canon import CanonService
from girlframe.services.canon_briefings import CanonBriefings
from girlframe.services.m2_game import GameService
from girlframe.services.m3_cast import CastService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import ReadOnlyBotService
from girlframe.services.scene_safety import SceneSafety


def with_canon(ledger):
    for viewer in (FACILITATOR, OUTSIDE):
        ledger.join(viewer, f"join-{viewer.user_id}")
    ledger.policy = ledger.policy.model_copy(update={"canon_facilitator_id": FACILITATOR.user_id})
    return CanonService(ledger)


def launch(ledger):
    missions, game = setup_missions(ledger)
    game.close_scene(ADMIN, "close-before-introduction", 900)
    session = ready_plan(ledger, "narrative")
    complete(session)
    return missions, game, session, with_canon(ledger)


def book(timeline, key, channel, anchor, plan):
    with timeline.store.engine.connect() as c:
        scene = timeline.game.scene(c, channel, check_slot=False)
    return timeline.schedule(ADMIN, key, channel, scene["id"], scene["revision"], anchor, plan)[
        "scene"
    ]


def learn_in_opening(canon, statement, key, refs=()):
    window = canon.window(FACILITATOR, 901, facilitator=True)
    fact = canon.establish(FACILITATOR, f"{key}-fact", window, statement, depends_on=refs)
    canon.witness(FACILITATOR, f"{key}-witness", window, fact, PLAYER.user_id)
    canon.report(PLAYER, f"{key}-report", window, fact)
    return fact


def test_m4_003_004_006_knowledge_carries_into_first_mission_and_correction_flags_descendants(
    ledger,
):
    missions, game, session, canon = launch(ledger)
    briefings = CanonBriefings(ledger)
    root = learn_in_opening(canon, SECRET, "signal")
    derivative = learn_in_opening(
        canon, "The courier tuned a receiver to the west relay.", "route", (root,)
    )
    second = learn_in_opening(canon, "A spare flare is in the canteen.", "flare")
    private_window = canon.window(FACILITATOR, 901, facilitator=True)
    secret = canon.establish(FACILITATOR, "gm-only", private_window, UNSHARED)
    with pytest.raises(WorkflowError, match="Handler has learned"):
        briefings.draft(ADMIN, "guess-gm-secret", (secret,))
    draft = briefings.draft(ADMIN, "ready-briefing", (root,))
    dependent_draft = briefings.draft(ADMIN, "dependent-briefing", (derivative,))
    stale_offer_draft = briefings.draft(ADMIN, "other-briefing", (second,))
    assert canon.known(OTHER) == ()
    for day in (1, 2, 3):
        session.advance_opening(ADMIN, f"opening-day-{day}", session.view(ADMIN)["opening_anchor"])

    # A correction after publication keeps the recipient's original record and
    # prevents acceptance or dispatch of the stale offer.
    stale_offer = missions.offer(
        ADMIN,
        "stale-offer",
        "Deliver a battery.",
        (PLAYER.user_id, OTHER.user_id),
        briefing_draft=stale_offer_draft,
    )
    stale_accepted = missions.respond(
        PLAYER, "answer-before-correction", stale_offer["id"], stale_offer["revision"], "accept"
    )
    canon.correct(FACILITATOR, "correct-flare", second, "The canteen has no spare flare.")
    assert missions.get(OTHER, stale_offer["id"])["briefing_needs_review"]
    with pytest.raises(WorkflowError, match="CANON_REVIEW_REQUIRED"):
        missions.respond(
            OTHER, "accept-stale", stale_offer["id"], stale_accepted["revision"], "accept"
        )
    with pytest.raises(WorkflowError, match="CANON_REVIEW_REQUIRED"):
        missions.start(ADMIN, "dispatch-stale", stale_offer["id"], stale_accepted["revision"])
    missions.cancel(ADMIN, "cancel-stale", stale_offer["id"], stale_accepted["revision"])

    offered = missions.offer(
        ADMIN, "first-offer", "Deliver a relay battery.", (OTHER.user_id,), briefing_draft=draft
    )
    identity = offered["id"]
    assert missions.get(OTHER, identity)["briefing"] == [{"statement": SECRET, "status": "current"}]
    with pytest.raises(WorkflowError, match="visible only"):
        missions.get(OUTSIDE, identity)
    assert UNSHARED not in str(canon.known(ADMIN)) + str(canon.known(OTHER))
    learned = next(item for item in canon.known(OTHER) if item.fact_id == root)
    assert learned.method == "briefed" and learned.learned_at.day == 4
    accepted = missions.respond(OTHER, "owner-accepts", identity, offered["revision"], "accept")
    dispatched = missions.start(ADMIN, "dispatch", identity, accepted["revision"])
    assert dispatched["scene"] != private_window.scene_id
    game.join_scene(OTHER, "arrive", dispatched["channel"])
    game.bind_scene(ADMIN, "bind-dependent-scene", 902)
    timeline = CampaignTimeService(ledger)
    briefing_position = Position(day=4, slot="morning")
    dependent_scene = book(
        timeline,
        "book-dependent-scene",
        902,
        session.view(ADMIN)["opening_anchor"],
        ScenePlan(
            start=briefing_position,
            end=briefing_position,
            location="Planning Office",
            participants=(ADMIN.user_id,),
            requires=(Dependency(kind="fact", id=root),),
        ),
    )

    correction = canon.correct(
        FACILITATOR, "correct-signal", root, "The east relay carries the signal."
    )
    ledger.engine.dispose()
    canon = CanonService(ledger)
    world = {fact.fact_id: fact for fact in canon.world(FACILITATOR)}
    assert world[root].statement == SECRET and world[root].status == "superseded"
    assert world[derivative].status == "needs_review" and world[correction].status == "current"
    assert correction not in {fact.fact_id for fact in canon.known(ADMIN)}
    assert missions.get(OTHER, identity)["mission"]["phase"] == "active"
    assert missions.get(OTHER, identity)["briefing_needs_review"]
    assert next(
        scene for scene in timeline.projection(ADMIN)["scenes"] if scene["id"] == dependent_scene
    )["dependency_pending"]
    with pytest.raises(WorkflowError, match="SCENE_DEPENDENCY_PENDING"):
        game.join_scene(ADMIN, "await-corrected-scene-source", 902)
    drafts = {item["id"]: item["needs_review"] for item in briefings.drafts(ADMIN)}
    assert drafts[draft] and drafts[dependent_draft]
    game.join_scene(ADMIN, "arrive-to-hear-correction", dispatched["channel"])
    mission_window = canon.window(FACILITATOR, dispatched["channel"], facilitator=True)
    canon.witness(
        FACILITATOR, "observe-corrected-signal", mission_window, correction, OTHER.user_id
    )
    canon.report(OTHER, "revised-report", mission_window, correction)
    refreshed = briefings.draft(ADMIN, "refreshed-draft", (correction,))
    assert not briefings.drafts(ADMIN)[0]["needs_review"]
    assert briefings.drafts(ADMIN)[0]["id"] == refreshed
    with ledger.engine.connect() as c:
        with pytest.raises(WorkflowError, match="CANON_REVIEW_REQUIRED"):
            briefings.prepare(c, ADMIN, dependent_draft)
        mission_grants = [
            row
            for row, body in calendar.history(c, ledger.campaign_id, history.GRANT)
            if body.get("briefing") and body["briefing"]["mission_id"] == identity
        ]
        assert len(mission_grants) == 1
    assert (
        missions.offer(
            ADMIN, "first-offer", "Deliver a relay battery.", (OTHER.user_id,), briefing_draft=draft
        )
        == offered
    )


def test_m4_005_009_activity_submission_is_immutable_and_uses_current_time(ledger):
    missions, _, session, canon = launch(ledger)

    async def check_discord_registration():
        status = ReadOnlyBotService(ledger.policy, MagicMock())
        async with ReadOnlyDiscordBot(
            ledger.policy, status, None, ledger, activity_only=True
        ) as bot:
            guild = discord.Object(id=200)
            assert bot.tree.get_command("scene", guild=guild) is None
            assert not bot.intents.message_content
            assert (
                bot.tree.get_command(
                    "Propose as canon", guild=guild, type=discord.AppCommandType.message
                )
                is None
            )
            assert bot.tree.get_command("canon", guild=guild) is None

    asyncio.run(check_discord_registration())
    scene_id = session.view(PLAYER)["opening"]["scene"]
    with pytest.raises(WorkflowError, match="actual Pilot or Handler"):
        canon.window_for_scene(OUTSIDE, scene_id)
    window = canon.window_for_scene(PLAYER, scene_id)
    submission_id = str(uuid4())
    statement = "The roster board shows the supply shuttle has landed."
    proposal_id = canon.propose_activity(PLAYER, submission_id, window, statement)
    proposal = canon.proposals(PLAYER)[0]
    assert proposal["status"] == "pending"
    assert proposal["source"] == {"submission_id": submission_id}
    assert canon.world(FACILITATOR) == canon.world(OTHER, public=True) == ()
    assert canon.proposals(ADMIN) == []
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        canon.propose_activity(PLAYER, submission_id, window, "Edited draft text.")

    session.advance_opening(ADMIN, "next-morning", session.view(ADMIN)["opening_anchor"])
    assert canon.propose_activity(PLAYER, submission_id, window, statement) == proposal_id
    fact_id = canon.review(FACILITATOR, "activity-approval", proposal_id, approve=True, public=True)
    (public,) = canon.world(OUTSIDE, public=True)
    assert public.fact_id == fact_id and public.statement == statement
    assert public.established_at.day == 2
    assert canon.known(ADMIN) == ()
    with ledger.engine.connect() as c:
        [(row, data)] = calendar.history(c, ledger.campaign_id, history.PROPOSAL)
        assert row["actor_id"] == str(PLAYER.user_id)
        assert datetime.fromisoformat(row["created_utc"]).tzinfo is not None
        assert Proposal.model_validate_json(json.dumps(data)).window.position.day == 1
        [(_, fact)] = calendar.history(c, ledger.campaign_id, history.FACT)
        assert WorldFact.model_validate_json(json.dumps(fact)).proposal_id == proposal_id

    late = canon.propose_activity(
        PLAYER,
        str(uuid4()),
        canon.window_for_scene(PLAYER, scene_id),
        "The shuttle is moving again.",
    )
    for day in (2, 3):
        session.advance_opening(ADMIN, f"advance-from-{day}", session.view(ADMIN)["opening_anchor"])
    with pytest.raises(WorkflowError, match="original scene is closed"):
        canon.review(FACILITATOR, "approve-after-seal", late, approve=True)
    assert missions.offer_requirements(ADMIN) == (True, False)


def test_legacy_discord_message_proposals_stay_out_of_current_review(ledger):
    _, _, session, canon = launch(ledger)
    scene_id = session.view(PLAYER)["opening"]["scene"]
    window = canon.window_for_scene(PLAYER, scene_id)
    with ledger.transaction() as c:
        legacy_id = ledger._audit(
            c,
            PLAYER.user_id,
            "old-discord-proposal",
            history.PROPOSAL,
            {
                "window": window.model_dump(mode="json"),
                "statement": "Former channel text.",
                "source": {"message_id": 333, "channel_id": 901, "author_id": PLAYER.user_id},
            },
        )
    assert canon.proposals(PLAYER) == canon.proposals(FACILITATOR, facilitator=True) == []
    with pytest.raises(WorkflowError, match="in the Activity"):
        canon.review(FACILITATOR, "try-legacy-approval", legacy_id, approve=True)
    assert canon.world(FACILITATOR) == ()
    with ledger.engine.connect() as c:
        [(row, _)] = calendar.history(c, ledger.campaign_id, history.PROPOSAL)
        assert row["id"] == legacy_id


def test_m4_001_002_007_008_parallel_safety_and_durable_choice_barrier(ledger):
    _, game = setup_missions(ledger)
    with_canon(ledger)
    game.leave_scene(OTHER, "leave-relay", 900)
    timeline = CampaignTimeService(ledger)
    moment = Position(day=8, slot="afternoon")
    anchor = timeline.initialize(ADMIN, "initial-time", Anchor(chapter="Recon", position=moment))[
        "receipt"
    ]
    first = book(
        timeline,
        "relay",
        900,
        anchor,
        ScenePlan(start=moment, end=moment, participants=(2, 1), location="Relay"),
    )
    game.bind_scene(ADMIN, "bind-tower", 901)
    with pytest.raises(WorkflowError, match="overlapping"):
        book(
            timeline,
            "impossible-tower",
            901,
            anchor,
            ScenePlan(start=moment, end=moment, participants=(2,), location="Tower"),
        )
    second = book(
        timeline,
        "tower",
        901,
        anchor,
        ScenePlan(
            start=moment, end=moment, participants=(3,), location="Tower", allow_late_narration=True
        ),
    )
    game.join_scene(OTHER, "arrive-tower", 901)
    game.join_scene(ADMIN, "monitor-tower", 901)

    worker, gateway = GameWorker(game), Gateway()
    order = game.issue_order(ADMIN, "relay-order", 900, PLAYER.user_id, "Check the signal now.")
    tick(worker, gateway)
    (choice,) = game.choices(PLAYER)
    assert choice["kind"] == "order_response"
    game.bind_scene(ADMIN, "bind-briefing", 902)
    book(
        timeline,
        "briefing",
        902,
        anchor,
        ScenePlan(
            start=moment,
            end=moment,
            participants=(1,),
            location="Briefing Room",
            requires=(Dependency(kind="choice", id=choice["id"]),),
        ),
    )
    with pytest.raises(WorkflowError, match="SCENE_DEPENDENCY_PENDING"):
        game.join_scene(ADMIN, "wait-for-order", 902)

    safety = SceneSafety(ledger)
    safety.change(PLAYER, "pause-relay", 900, first, pause=True)
    safety.change(ADMIN, "second-relay-pause", 900, first, pause=True)
    assert not ledger.status(OTHER)["paused"]
    assert next(x for x in timeline.projection(PLAYER)["scenes"] if x["id"] == first)["paused"]
    assert not next(x for x in timeline.projection(OTHER)["scenes"] if x["id"] == second)["paused"]

    action = game.begin(
        OTHER,
        "tower-play",
        901,
        state(game).sheets["3"].revision,
        PlayInput(play="engage", context="Practice the signal", trigger_confirmed=True, heat=0),
    )
    tick(worker, gateway, 3)
    assert game.inspect(OTHER, action["action_id"])["receipt"] is not None
    ledger.engine.dispose()
    restarted = GameService(ledger, dice=game.dice)
    assert restarted.choices(PLAYER) == [choice]
    response = ChoiceAnswer(options=("obedient",))
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        restarted.respond(PLAYER, "answer-order", choice["id"], choice["revision"], response)
    assert restarted.inspect(PLAYER, order["action_id"])["state"] == "awaiting_choices"
    assert safety.change(PLAYER, "resume-only-player", 900, first, pause=False)["paused"]
    assert not safety.change(ADMIN, "resume-handler", 900, first, pause=False)["paused"]
    restarted.respond(PLAYER, "answer-order", choice["id"], choice["revision"], response)
    assert restarted.inspect(PLAYER, order["action_id"])["state"] == "complete"
    assert restarted.join_scene(ADMIN, "after-order", 902)["channel"] == 902


def test_m4_009_late_note_is_current_review_context_and_cannot_grant_retroactive_canon(ledger):
    _, game = setup_missions(ledger)
    canon = with_canon(ledger)
    timeline = CampaignTimeService(ledger)
    now = Position(day=2, slot="morning")
    later = Position(day=4, slot="night")
    receipt = timeline.initialize(ADMIN, "start-time", Anchor(chapter="Cadre", position=now))[
        "receipt"
    ]
    scene = book(
        timeline,
        "late-booking",
        900,
        receipt,
        ScenePlan(start=now, end=now, participants=(1, 2, 3), allow_late_narration=True),
    )
    preview = timeline.preview_cut(ADMIN, Cut(target=Anchor(chapter="Briefing", position=later)))
    assert preview["late_scenes"] == [scene]
    saved = timeline.commit_cut(
        ADMIN,
        "cut-to-briefing",
        Cut(target=Anchor(chapter="Briefing", position=later)),
        preview["token"],
    )
    timeline.record_late(
        ADMIN,
        "late-note",
        scene,
        saved["receipt"],
        LateSubmission(kind="knowledge", account="The supply wheel jammed.", recipients=(2,)),
    )
    projected = next(x for x in timeline.projection(PLAYER)["scenes"] if x["id"] == scene)
    assert projected["entries"][0]["recorded_at"] == later.model_dump()
    assert not next(x for x in timeline.projection(OTHER)["scenes"] if x["id"] == scene)["entries"]
    assert canon.known(PLAYER) == ()
    with pytest.raises(WorkflowError, match="open booked scene"):
        canon.window(PLAYER, 900, facilitator=False)
    with ledger.engine.connect() as c:
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(t.events)
                .where(t.events.c.kind == history.GRANT)
            )
            == 0
        )


def test_m4_upgrade_rehydrates_legacy_grants_and_preserves_saved_command_keys(ledger):
    _, _, _, canon = launch(ledger)
    expected = canon.window(FACILITATOR, 901, facilitator=True).model_copy(
        update={"scene_revision": None}
    )
    window = expected.model_dump(mode="json")

    def save_legacy_fact(c):
        receipt = ledger._audit(
            c,
            FACILITATOR.user_id,
            "old-establish",
            history.FACT,
            {"statement": SECRET, "window": window},
        )
        return {"receipt": receipt}

    result = ledger._write(
        FACILITATOR,
        "old-establish",
        "canon.establish",
        {"statement": SECRET, "window": window},
        save_legacy_fact,
        auto_audit=False,
    )
    with ledger.transaction() as c:
        ledger._audit(
            c,
            FACILITATOR.user_id,
            "old-witness",
            history.GRANT,
            {
                "window": window,
                "fact_id": result["receipt"],
                "recipient": PLAYER.user_id,
                "method": "witnessed",
                "source_grant_id": None,
            },
        )
    assert canon.establish(FACILITATOR, "old-establish", expected, SECRET) == result["receipt"]
    assert [fact.statement for fact in canon.known(PLAYER)] == [SECRET]
    assert canon.known(OTHER) == canon.known(ADMIN) == ()


def test_scene_disclosure_uses_the_actual_cast_pilot(ledger):
    actors, game = ready_cast(ledger)
    canon = with_canon(ledger)
    timing = CampaignTimeService(ledger)
    moment = Position(day=1, slot="morning")
    anchor = timing.initialize(ADMIN, "cast-anchor", Anchor(chapter="Relay", position=moment))
    book(
        timing,
        "cast-booking",
        900,
        anchor["receipt"],
        ScenePlan(start=moment, end=moment, participants=(1, 2, 3)),
    )
    cast = CastService(actors)
    change_cast(cast, PLAYER, "join", ActorRef(kind="npc", entity="secret-npc"))
    staff_window = canon.window(FACILITATOR, 900, facilitator=True)
    fact = canon.establish(FACILITATOR, "cast-fact", staff_window, SECRET)
    canon.witness(FACILITATOR, "original-pilot-witness", staff_window, fact, PLAYER.user_id)
    assert [known.fact_id for known in canon.known(PLAYER)] == [fact]

    change_cast(cast, PLAYER, "withdraw", pc_ref(actors, game))
    with pytest.raises(WorkflowError, match="actual Pilot or Handler"):
        canon.window(PLAYER, 900, facilitator=False)
    staff_window = canon.window(FACILITATOR, 900, facilitator=True)
    other_fact = canon.establish(FACILITATOR, "second-cast-fact", staff_window, UNSHARED)
    with pytest.raises(WorkflowError, match="participating Pilot"):
        canon.witness(FACILITATOR, "wrong-body", staff_window, other_fact, PLAYER.user_id)
    assert [known.fact_id for known in canon.known(PLAYER)] == [fact]
