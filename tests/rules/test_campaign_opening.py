"""Agreed campaign settings, the actual introductory scene, and Narrative limits."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_defeat_service import rolled
from test_director_activity_scene import P2Scene
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state
from test_mission_service import service as setup_missions
from test_punishment_service import ended, submit
from test_session_zero import OUTSIDE, approve, group, interaction, reviewed_sheets

from girlframe.ai.model_adapters import ModelActivityBatch
from girlframe.ai.model_transport import ModelLimits, OpenAIResponses
from girlframe.database import tables as t
from girlframe.discord_adapter.m3_defeat import open_decision
from girlframe.discord_adapter.session_zero import GoalsModal, OpeningModal, open_panel
from girlframe.engine.campaign_opening import Opening
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_careers import end
from girlframe.engine.m3_punishments import Details
from girlframe.scenes.campaign_time import Position, ScenePlan
from girlframe.services.activity_session_zero import SessionZeroDesk
from girlframe.services.campaign_difficulty import (
    DEATH_USED,
    EVENT,
    narrative_death_available,
    opening,
)
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.session_zero import SessionZeroService


def ready_plan(store, mode, *, approve_plan=True):
    session = SessionZeroService(store)
    approve(session, group(session))
    for viewer in (PLAYER, OTHER):
        session.attach(viewer, f"attach-{viewer.user_id}", session.view(viewer)["revision"])
    session.goals(
        ADMIN,
        "plan-draft",
        session.view(ADMIN)["revision"],
        "Learn each other's signals and keep the village relay open.",
        mode,
    )
    if approve_plan:
        agree(session)
    return session


def agree(session):
    draft = session.view(PLAYER)["plan_proposal"]
    for viewer in (ADMIN, PLAYER, OTHER):
        session.decide_plan(viewer, f"plan-{viewer.user_id}", draft, approve=True)


def complete(session):
    return session.complete(
        ADMIN,
        "complete-session-zero",
        session.view(ADMIN)["revision"],
        901,
        "Cadre, I'm Anwen. Let's talk about what it will take to keep the relay open.",
    )


@pytest.mark.parametrize("facilitator_only", [False, True], ids=["pilot-reviewer", "reviewer-only"])
def test_activity_session_zero_opens_private_roleplay_and_freezes_approved_seats(
    ledger, facilitator_only
):
    missions, game = setup_missions(ledger)
    game.close_scene(ADMIN, "close-setup-room", 900)
    game.bind_scene(ADMIN, "reserve-activity-opening", 901)
    ledger.join(OUTSIDE, "intro-outsider")
    desk = SessionZeroDesk(SessionZeroService(ledger, group_owner=ADMIN.user_id), 901)

    def view(viewer=ADMIN):
        return desk.read(viewer, "session-zero")

    def command(name, viewer, key, **data):
        return desk.write(viewer, key, "session-zero-" + name, data)

    command("group", ADMIN, "activity-group", revision=0, members=["1", "2", "3"])
    with pytest.raises(WorkflowError, match="Complete Session Zero"):
        missions.offer(ADMIN, "early-incomplete-setup", "Check the relay.", (2, 3))
    command(
        "propose",
        ADMIN,
        "activity-handler",
        revision=view()["revision"],
        profile={
            "member": "1",
            "control": "ai",
            "name": "Anchor",
            "archetype": "Advocate",
            "appearance": "Plain uniform.",
            "personality": "Unhurried.",
        },
    )
    nomination = view()["proposal"]
    for viewer in (ADMIN, PLAYER, OTHER):
        command(
            "handler-vote",
            viewer,
            "handler:" + str(viewer.user_id),
            proposal=nomination,
            approve=True,
        )
    for viewer in (PLAYER, OTHER):
        command("attach", viewer, "sheets:" + str(viewer.user_id), revision=view()["revision"])
    command(
        "plan",
        ADMIN,
        "activity-plan",
        revision=view()["revision"],
        difficulty="hard",
        goals="Find the source of the warning.",
        facilitator="3",
        facilitator_only=facilitator_only,
        seats={
            "player_count": 1 if facilitator_only else 2,
            "ai_pilots": [{"callsign": "Fern", "concept": "Quiet scout."}],
        },
    )
    assert view(OTHER)["is_pilot"] is not facilitator_only
    proposal = view()["plan_proposal"]
    raw_handler = replace(ADMIN, is_administrator=False)
    adapter = P2Scene.reviewed_activity(
        game,
        facilitator_id=ADMIN.user_id,
        opening_channel=901,
        handler_batch=ModelActivityBatch(
            OpenAIResponses(
                model="offline-fixture",
                api_key="offline-fixture",
                limits=ModelLimits(attempts=1, output_tokens=200),
                post=Mock(side_effect=AssertionError("This test makes no model calls.")),
            )
        ),
    )
    with pytest.raises(WorkflowError, match="trial facilitator"):
        adapter.authorize_provider(raw_handler)
    with pytest.raises(WorkflowError, match="trial facilitator"):
        adapter.authorize_provider(OTHER)
    for viewer in (ADMIN, PLAYER, OTHER):
        command("plan-vote", viewer, "plan:" + str(viewer.user_id), proposal=proposal, approve=True)
    args = {"revision": view()["revision"], "introduction": "Check in as you arrive.", "days": 2}
    completed = command("open", ADMIN, "activity-intro", **args)
    assert command("open", ADMIN, "activity-intro", **args) == completed
    ledger.engine.dispose()
    saved = view(PLAYER)["opening"]
    assert saved["handler_control"] == "ai" and saved["difficulty"] == "hard"
    assert saved["seats"]["ai_pilots"][0]["callsign"] == "Fern"
    assert saved["seats"]["player_count"] == (1 if facilitator_only else 2)
    assert saved["first_mission_day"] == 3 and saved["facilitator"] == "3"
    assert saved.get("facilitator_only", False) is facilitator_only
    adapter.authorize_provider(OTHER)
    with pytest.raises(WorkflowError, match="trial facilitator"):
        adapter.authorize_provider(raw_handler)
    anchor = view()["opening_anchor"]
    post = {"anchor": anchor, "text": "I check the readings by the door."}
    with pytest.raises(WorkflowError, match="Only members"):
        command("post", OUTSIDE, "outside", **post)
    receipt = command("post", PLAYER, "roleplay", **post)
    assert command("post", PLAYER, "roleplay", **post) == receipt
    assert [item["text"] for item in view(OTHER)["opening_posts"]] == [post["text"]]
    other_post = post | {"text": "I bring the spare headset."}
    if facilitator_only:
        with pytest.raises(WorkflowError, match="Only the cast"):
            command("post", OTHER, "facilitator-post", **other_post)
    else:
        command("post", OTHER, "facilitator-post", **other_post)
        assert view(PLAYER)["opening_posts"][-1]["text"] == other_post["text"]
    with pytest.raises(WorkflowError, match="first mission starts on Day 3"):
        missions.offer(ADMIN, "early-intro", "Check the relay.", (2, 3))
    command("advance", ADMIN, "day-two", anchor=anchor)
    with pytest.raises(WorkflowError, match="STALE_INTRODUCTION"):
        command("post", PLAYER, "old-day", **post)
    command("advance", ADMIN, "day-three", anchor=view()["opening_anchor"])
    with pytest.raises(WorkflowError, match="The introduction has ended"):
        command("post", PLAYER, "late-post", anchor=view()["opening_anchor"], text="Too late.")
    assert missions.offer_requirements(ADMIN) == (True, False)

    actors = (ADMIN, PLAYER) if facilitator_only else (ADMIN, PLAYER, OTHER)
    bound = game.bind_scene(ADMIN, "review-scene", 902)
    with ledger.engine.connect() as c:
        row = game.scene(c, 902, check_slot=False)
    day_three = Position(day=3, slot="morning")
    scene = bound["scene"]
    CampaignTimeService(ledger).schedule(
        ADMIN,
        "schedule-review",
        902,
        scene,
        row["revision"],
        view()["opening_anchor"],
        ScenePlan(start=day_three, end=day_three, participants=tuple(x.user_id for x in actors)),
    )
    for actor in actors:
        game.join_scene(actor, f"scene-join:{actor.user_id}", 902)
    speaker = next(x for x in adapter.trial_scenes(OTHER)["scenes"] if x["id"] == scene)["speaker"]
    assert speaker == (None if facilitator_only else "pilot")
    assert adapter.trial_scenes(OUTSIDE) == {"scenes": []}
    adapter.write(
        OTHER,
        "review-policy",
        scene,
        "activity-policy-save",
        {
            "revision": 0,
            "enabled": True,
        },
    )
    adapter.write(OTHER, "notice", scene, "configure", {"revision": 0})
    if facilitator_only:
        with pytest.raises(WorkflowError, match="schedule this Pilot"):
            game.join_scene(OTHER, "unbooked-reviewer", 902)
        with pytest.raises(WorkflowError, match="join this scene"):
            adapter.read(OTHER, scene, "timeline")
        with pytest.raises(WorkflowError):
            adapter.write(
                OTHER,
                "outside-consent",
                scene,
                "consent",
                {
                    "policy_revision": 1,
                    "consent": True,
                },
            )
    for actor in actors:
        adapter.write(
            actor,
            f"consent:{actor.user_id}",
            scene,
            "consent",
            {
                "policy_revision": 1,
                "consent": True,
            },
        )
    assert adapter.read(OTHER, scene, "gm-work")["handler_drafts"] == []
    with pytest.raises(WorkflowError):
        adapter.read(PLAYER, scene, "gm-work")


def test_native_completion_opens_private_roleplay_scene_before_character_activation(
    ledger, monkeypatch
):
    reviewed_sheets(ledger)
    ledger.join(OUTSIDE, "outsider")
    session = ready_plan(ledger, "narrative", approve_plan=False)
    stale = session.view(PLAYER)["plan_proposal"]
    session.decide_plan(PLAYER, "early-approval", stale, approve=True)
    session.goals(
        ADMIN,
        "changed-difficulty",
        session.view(ADMIN)["revision"],
        "Learn the rally signals and decide how to protect the relay.",
        "normal",
    )
    assert session.view(PLAYER)["plan_approvals"] == 0
    with pytest.raises(WorkflowError, match="STALE_PLAN"):
        session.decide_plan(OTHER, "stale-difficulty", stale, approve=True)
    with pytest.raises(WorkflowError, match="Every group member"):
        complete(session)
    agree(session)

    async def allowed(*args):
        return True

    monkeypatch.setattr("girlframe.discord_adapter.session_zero.action_gate", allowed)

    async def run():
        owner = interaction(ADMIN.user_id)
        await open_panel(owner, session)
        view = owner.edit_original_response.call_args.kwargs["view"]
        assert not view.complete.disabled
        assert {x.value for x in GoalsModal(view).mode.options} == {"narrative", "normal", "hard"}
        click = interaction(ADMIN.user_id, 601)
        click.response.send_modal = AsyncMock()
        await view.complete.callback(click)
        modal = click.response.send_modal.call_args.args[0]
        assert isinstance(modal, OpeningModal)
        assert [x["component"]["type"] for x in modal.to_components()] == [8, 4, 3]

    asyncio.run(run())
    expected = session.view(ADMIN)["revision"]
    result = complete(session)
    ledger.engine.dispose()
    restarted = SessionZeroService(ledger)
    assert (
        restarted.complete(
            ADMIN,
            "complete-session-zero",
            expected,
            901,
            "Cadre, I'm Anwen. Let's talk about what it will take to keep the relay open.",
        )
        == result
    )
    own = restarted.view(PLAYER)
    assert own["opening_day"] == 1
    assert own["opening"]["first_mission_day"] == 4
    assert "I'm Anwen" in restarted.generate(PLAYER, own["revision"])
    timeline = CampaignTimeService(ledger)
    assert timeline.projection(PLAYER)["scenes"][0]["narrative_only"]
    assert not timeline.projection(PLAYER)["scenes"][0]["joined"]
    assert timeline.projection(OUTSIDE)["scenes"] == []
    with pytest.raises(WorkflowError, match="Only the appointed Handler"):
        restarted.advance_opening(PLAYER, "not-authorized", own["opening_anchor"])
    with ledger.engine.connect() as c:
        with pytest.raises(WorkflowError, match="reserved for roleplay"):
            timeline.game.scene(c, 901)


def test_hard_campaign_has_three_roleplay_days_and_simple_first_mission_then_extra_stakes(ledger):
    missions, game = setup_missions(ledger)
    game.close_scene(ADMIN, "close-fixture-scene", 900)
    session = ready_plan(ledger, "hard")
    before = state(game)
    complete(session)
    for day in (1, 2, 3):
        view = session.view(ADMIN)
        assert view["opening_day"] == day
        with pytest.raises(WorkflowError, match="first mission starts on Day 4"):
            missions.offer(ADMIN, "early-mission", "Deliver the relay battery", (2, 3))
        receipt = session.advance_opening(ADMIN, f"advance-{day}", view["opening_anchor"])
        assert receipt["anchor"]["position"]["day"] == day + 1
        assert session.advance_opening(ADMIN, f"advance-{day}", view["opening_anchor"]) == receipt
    assert state(game) == before

    assert missions.offer_requirements(ADMIN) == (True, False)
    with pytest.raises(WorkflowError, match="simple objective"):
        missions.offer(
            ADMIN, "too-much", "Deliver the battery", (2, 3), hard_stake="A longer route"
        )
    offer = missions.offer(ADMIN, "first-briefing", "Deliver the relay battery", (2, 3))
    assert missions.get(PLAYER, offer["id"])["mission"]["introductory"]
    accepted = missions.respond(
        PLAYER, "first-pilot-response", offer["id"], offer["revision"], "accept"
    )
    accepted = missions.respond(
        OTHER, "second-pilot-response", offer["id"], accepted["revision"], "accept"
    )
    active = missions.start(ADMIN, "dispatch-first", offer["id"], accepted["revision"])
    assert active["scene"] != session.view(PLAYER)["opening"]["scene"]
    assert active["channel"] == 901
    with ledger.engine.connect() as c:
        assert game.scene(c, 901)["participants"] == []
    game.join_scene(PLAYER, "join-first", 901)
    ended = missions.end(ADMIN, "end-first", active["id"], active["revision"], True)
    if ended["phase"] != "complete":
        discipline = PunishmentService(ledger)
        for work in missions.get(ADMIN, ended["id"])["work"]:
            submit(
                discipline,
                ADMIN,
                work["id"],
                Details(kind="stimulant_injection"),
                "opening-mission-discipline",
            )
        ended = missions.complete(ADMIN, "settle-first", ended["id"], ended["revision"])
    assert ended["phase"] == "complete"
    assert missions.offer_requirements(ADMIN) == (False, True)
    with pytest.raises(WorkflowError, match="extra obstacle"):
        missions.offer(ADMIN, "no-hard-stake", "Evacuate the depot", (2,))
    hard = missions.offer(
        ADMIN,
        "hard-briefing",
        "Evacuate the depot",
        (2,),
        hard_stake="The road is flooded; extraction has to use the rail bridge.",
    )
    assert missions.get(PLAYER, hard["id"])["mission"]["hard_stake"].startswith(
        "The road is flooded"
    )


def narrative_fixture(store):
    # Use an explicit synthetic settings receipt when exercising separate printed-rule fixtures.
    record = Opening(
        scene="synthetic-opening",
        channel=901,
        handler=1,
        audience=(1, 2, 3),
        plan="synthetic-approved-plan",
        goals="Support the cadre.",
        difficulty="narrative",
        introduction="Welcome, cadre.",
        first_mission_day=4,
    )
    with store.transaction() as c:
        store._audit(c, ADMIN.user_id, "synthetic-mode", EVENT, record.model_dump(mode="json"))
        assert opening(c, store.campaign_id) == record


def test_narrative_discipline_rejects_severe_outcomes_and_keeps_nonlethal_choice(ledger):
    service, _, game, _, identity = ended(ledger)
    narrative_fixture(ledger)
    original = state(game)
    preview = service.get(ADMIN, identity)
    assert preview["narrative_limit"]
    for kind in ("execution", "lobotomization", "indefinite_imprisonment"):
        with pytest.raises(WorkflowError, match="NARRATIVE_LIMIT"):
            submit(service, ADMIN, identity, Details(kind=kind), f"blocked-{kind}")
    assert state(game) == original
    submit(service, ADMIN, identity, Details(kind="stimulant_injection"), "nonlethal-punishment")
    assert service.get(ADMIN, identity)["state"] == "resolved"
    assert state(game).sheets["3"].character_id == original.sheets["3"].character_id


def test_narrative_defeat_keeps_the_roll_and_lets_the_player_choose_survival(ledger):
    game, _, _, _, action = rolled(ledger, faces=(1, 1))
    narrative_fixture(ledger)
    original = state(game)
    with pytest.raises(WorkflowError, match="NARRATIVE_LIMIT"):
        with ledger.transaction() as c:
            profile = c.execute(
                sa.select(t.characters.c.id, t.characters.c.revision).where(
                    t.characters.c.campaign_id == ledger.campaign_id,
                    t.characters.c.user_id == str(PLAYER.user_id),
                )
            ).one()
            event = str(uuid4())
            fatal = end(
                original,
                current_ref(original, PLAYER.user_id),
                reason="death",
                source_event=event,
                account="A synthetic fatal combat consequence",
                archive_id=str(uuid4()),
                profile_id=profile.id,
                profile_revision=profile.revision,
            )
            game.event(
                c,
                ADMIN.user_id,
                "fatal-writer",
                "synthetic.fatal_consequence",
                fatal,
                event_id=event,
            )
    assert state(game) == original
    rolled_receipt = game.inspect(PLAYER, action)["receipt"]
    with pytest.raises(WorkflowError, match="NARRATIVE_LIMIT"):
        answer(game, PLAYER, "defeat_select", options=("death",), text="Fatal outcome")
    assert state(game) == original
    assert game.inspect(PLAYER, action)["receipt"] == rolled_receipt
    assert any(x["kind"] == "defeat_select" for x in game.choices(PLAYER))
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("lose_frame_choose_later",),
        text="I survive the wreck and will choose my next Frame later.",
    )
    assert state(game).sheets["2"].frame_scrapped
    assert state(game).sheets["2"].character_id == original.sheets["2"].character_id


def test_narrative_uses_its_single_death_only_for_confirmed_owned_low_defeat(ledger):
    game, *_ = rolled(ledger, faces=(1, 1))
    narrative_fixture(ledger)
    original = state(game)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "defeat_select")
    decision = game.decision(PLAYER, choice["id"])
    assert decision["defeat"]["narrative_death_available"]

    account = "I choose this end for my character."

    async def confirm_through_discord():
        request = interaction(PLAYER.user_id, 981)
        await request.response.defer(ephemeral=True)
        await open_decision(request, game, decision)
        form = request.edit_original_response.call_args.kwargs["view"]
        fields = {field.key: field for field in form.fields}
        assert "death" in dict(fields["options"].options)
        assert not fields["confirm_death"].required
        form.values.update(options=("death",), account=account, confirm_death=("yes",))
        await form.confirm.callback(interaction(PLAYER.user_id, 982))
        assert form.completed

    asyncio.run(confirm_through_discord())
    confirm = ChoiceAnswer(options=("death",), text=account, flag=True)
    args = (PLAYER, "982", choice["id"], choice["revision"], confirm)
    result = game.respond(*args)
    recorded = state(game)
    assert len(recorded.career_archives) == len(original.career_archives) + 1
    assert recorded.career_archives[-1].actor == current_ref(original, PLAYER.user_id)
    assert "3" in recorded.sheets

    ledger.engine.dispose()
    restarted = GameService(ledger)
    assert restarted.respond(*args) == result
    with ledger.engine.connect() as c:
        assert not narrative_death_available(c, ledger.campaign_id, recorded)
        # The private receipt alone still enforces the limit if a projection is rebuilt.
        assert not narrative_death_available(c, ledger.campaign_id, original)
        receipts = list(
            c.scalars(
                sa.select(t.events.c.id).where(
                    t.events.c.campaign_id == ledger.campaign_id,
                    t.events.c.kind == DEATH_USED,
                )
            )
        )
        assert len(receipts) == 1


def test_spent_narrative_death_blocks_another_confirmed_lethal_choice(ledger):
    game, *_ = rolled(ledger, faces=(1, 1))
    narrative_fixture(ledger)
    with ledger.transaction() as c:
        ledger._audit(c, OTHER.user_id, "earlier-death", DEATH_USED, {"archive": "earlier-death"})
    before = state(game)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "defeat_select")
    assert not game.decision(PLAYER, choice["id"])["defeat"]["narrative_death_available"]
    with pytest.raises(WorkflowError, match="already recorded its one death"):
        game.respond(
            PLAYER,
            "attempt-second-narrative-death",
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("death",), text="I choose this end.", flag=True),
        )
    assert state(game) == before
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("lose_frame_choose_later",),
        text="I climb out alive and leave my wrecked Frame behind.",
    )
    assert state(game).sheets["2"].frame_scrapped
