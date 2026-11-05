"""An actual recursive Endgame, real period and roll precede explicit collective consent."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from test_budget_persistent_tag import source as endgame_source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, roll_for
from test_world import gorgon, initial

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_collective_handler_tags import open_collective
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Asset, CorePlan, Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_collective_handler_tags import CollectiveTagService
from girlframe.services.m3_handler_tags import HandlerTagService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def source(store, *, roll=True):
    _, game, strain, endgame, period = endgame_source(store, option=6)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    world = initial()
    WorldService(strain.missions).initialize(
        ADMIN,
        "actual-collective-world",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    # A possible established prior world fact, not a mocked current roll/result:
    # the actual High Void3.1 consumer below revives this existing original body.
    with store.transaction() as c:
        canon = state(game)
        dead = canon.world.gorgons[0].model_copy(
            update={
                "alive": False,
                "assets": tuple(
                    x.model_copy(update={"damaged": True}) for x in canon.world.gorgons[0].assets
                ),
            }
        )
        second = gorgon("benevolent", "actual-second-prior-defeat", cell=(2, 1)).model_copy(
            update={"alive": False}
        )
        canon.world = update(canon.world, gorgons=(dead, second))
        game.event(
            c, 1, "established-prior-gorgon-defeat", "synthetic.established_prior_defeat", canon
        )
    service = CollectiveTagService(store)
    service.install(ADMIN, "actual-collective-endgame-install", endgame, state(game).revision)
    complete_start(strain, game)
    cycle = CycleService(strain.periods)
    activate(cycle, game, period)
    identity = endgame + ":period:" + period
    if roll:
        roll_for(cycle, game, period, PLAYER, (2, 2))
    return service, game, cycle, endgame, period, identity


def complete_start(strain, game):
    effects = EffectService(strain)
    for request in tuple(state(game).strain.requests):
        if request.track == "void":
            strain.dice.face, column = 3, 1
            dead = next(x for x in state(game).world.gorgons if not x.alive)
            new = tuple(
                Asset(
                    id=request.id + ":returned:" + str(i),
                    name="Returned capability " + str(i),
                    description="Actual new source capability",
                    family="gorgon",
                )
                for i in range(2)
            )
            choice = Choice(
                rule_id="strain.void.high.3.1",
                account="The previously defeated original Gorgon returns with its new resources",
                target=dead.id,
                new_assets=new,
                new_type="leviathan",
                core_plan=CorePlan(
                    assets=(new[0].id,), weakness="Actual newly required weak state"
                ),
            )
        elif request.track == "rebellion":
            strain.dice.face, column = 1, 1
            choice = Choice(
                rule_id="strain.rebellion.low.1.1",
                account="A real new rebel group",
                target="city0",
                faction=Faction(
                    id="actual-rebels:" + request.id,
                    name="Actual source rebels",
                    kind="rebel",
                    cells=((0, 4),),
                    description="A source-defined real rebel group",
                ),
            )
        else:
            strain.dice.face, column = 4, 2
            choice = Choice(
                rule_id="strain.budget.low.4.2",
                account="A source-required actual repair shortage for the next dispatch",
            )
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        effects.apply(ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice)


def test_two_actual_periods_offer_distinct_once_only_collective_tags_and_reject_old_forms(ledger):
    from test_strain import facts

    from girlframe.services.m3_strain import StrainService

    service, game, cycle, entitlement, period, identity = source(ledger)
    service.propose(
        PLAYER,
        "first-period-proposal",
        entitlement,
        period,
        state(game).revision,
        "First period Tag",
        "The first actual collective descriptor",
    )
    first = service.respond(
        OTHER, "first-period-agreement", identity, state(game).revision, "agree"
    )
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    roll_for(cycle, game, period, OTHER, (4, 4))
    call(cycle, game, OTHER, period, "scene", None, (), "")
    call(cycle, game, OTHER, period, "recover", RecoveryChoice())
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    second = cycle.periods.begin(ADMIN, "actual-second-period")
    strain = StrainService(cycle.periods, dice=__import__("test_strain_service").D6())
    strain.prepare(
        ADMIN,
        "second-period-start",
        second["id"],
        1,
        state(game).revision,
        facts(at_least_half_have_void=True),
    )
    complete_start(strain, game)
    activate(cycle, game, second["id"])
    with pytest.raises(WorkflowError, match="unavailable"):
        service.propose(
            PLAYER,
            "old-period-cannot-repeat",
            entitlement,
            period,
            state(game).revision,
            "Old",
            "Cannot use an ended period",
        )
    roll_for(cycle, game, second["id"], PLAYER, (4, 4))
    service.propose(
        OTHER,
        "second-period-proposal",
        entitlement,
        second["id"],
        state(game).revision,
        "Second period Tag",
        "The next actual collective descriptor",
    )
    later = entitlement + ":period:" + second["id"]
    second_result = service.respond(
        PLAYER, "second-period-agreement", later, state(game).revision, "agree"
    )
    assert first["tag"] != second_result["tag"]
    assert {x.label for x in state(game).handler_tags} == {"First period Tag", "Second period Tag"}


def test_actual_period_roll_native_exact_agreements_create_one_removable_tag(ledger):
    service, game, cycle, entitlement, period, identity = source(ledger, roll=False)
    inbox = InboxService(ledger)
    assert not any(x.task == "m3_collective_tag" for x in inbox.items(PLAYER))
    roll_for(cycle, game, period, PLAYER, (2, 2))
    available = next(x for x in inbox.items(PLAYER) if x.task == "m3_collective_tag")
    assert available.identity == identity
    before = state(game)
    calls = game.dice.calls

    async def run():
        player = current(2, 820)
        await player.response.defer(ephemeral=True)
        await open_collective(player, service, identity)
        form = player.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(
            tag="PRIVATE_COLLECTIVE_WORDING", account="The actual Girls' exact proposed descriptor"
        )
        await form.confirm.callback(current(2, 821))
        assert not state(game).handler_tags
        assert "PRIVATE_COLLECTIVE_WORDING" not in str(inbox.items(ADMIN))
        other = current(3, 822)
        await other.response.defer(ephemeral=True)
        await open_collective(other, service, identity)
        agreement = other.edit_original_response.call_args.kwargs["view"]
        assert all(word in agreement.instructions for word in ("PRIVATE", "COLLECTIVE", "WORDING"))
        assert not await agreement.interaction_check(current(1, 823))
        agreement.values["decision"] = ("agree",)
        await agreement.confirm.callback(current(3, 824))

    asyncio.run(run())
    assert state(game).sheets == before.sheets
    assert game.dice.calls == calls
    tag = state(game).handler_tags[-1]
    assert tag.label == "PRIVATE_COLLECTIVE_WORDING" and set(tag.observers) == {2, 3}
    handler_tags = HandlerTagService(game)
    girl = current_ref(state(game), 2)
    view = handler_tags.view(PLAYER, 900, girl)
    used = handler_tags.use(
        PLAYER,
        "use-ordinary-collective-tag",
        900,
        girl,
        view["source_sha256"],
        tag.id,
        "attention",
        "The actual collective descriptor is used",
    )
    assert not used.get("persistent") and not any(x.id == tag.id for x in state(game).handler_tags)
    with pytest.raises(WorkflowError, match="STALE"):
        service.propose(
            PLAYER,
            "no-second-tag-same-period",
            entitlement,
            period,
            state(game).revision,
            "Repeated",
            "Cannot duplicate source",
        )
    with ledger.engine.connect() as c:
        assert not [
            x
            for x in cycle.periods._pending(c, period)
            if x["kind"] == "collective_handler_tag_vote"
        ]


def test_decline_or_withdraw_resolves_actual_vote_work_without_forging_a_tag(ledger):
    service, game, cycle, entitlement, period, identity = source(ledger)
    service.propose(
        PLAYER,
        "first-real-proposal",
        entitlement,
        period,
        state(game).revision,
        "First descriptor",
        "Actual first collective proposal",
    )
    with ledger.engine.connect() as c:
        assert any(
            x["kind"] == "collective_handler_tag_vote" for x in cycle.periods._pending(c, period)
        )
    service.respond(PLAYER, "withdraw-real-proposal", identity, state(game).revision, "withdraw")
    with ledger.engine.connect() as c:
        assert not [
            x
            for x in cycle.periods._pending(c, period)
            if x["kind"] == "collective_handler_tag_vote"
        ]
    assert not state(game).handler_tags
    service.propose(
        OTHER,
        "new-exact-proposal",
        entitlement,
        period,
        state(game).revision,
        "New descriptor",
        "All Girls must respond again",
    )
    service.respond(PLAYER, "actual-girl-declines", identity, state(game).revision, "decline")
    assert not state(game).handler_tags
    assert service.view(PLAYER, identity)["state"] == "declined"


def test_observation_without_a_real_go_off_duty_roll_does_not_create_the_optional_trigger(ledger):
    from test_m2_game import Dice
    from test_observation_service import roll_for as roll_observation

    from girlframe.services.m3_observation import ObservationService

    service, game, cycle, entitlement, period, identity = source(ledger, roll=False)
    observation = ObservationService(cycle.periods)
    view = cycle.review(ADMIN, period)
    observation.order(
        ADMIN,
        "actual-observation-only",
        period,
        view["revision"],
        state(game).revision,
        2,
        True,
        "An actual source Observation order",
    )
    game.dice = Dice((1, 1))
    roll_observation(observation, game, period)
    assert game.dice.calls == 1
    with pytest.raises(WorkflowError, match="Go Off-Duty"):
        service.view(PLAYER, identity)
    assert not any(x.task == "m3_collective_tag" for x in InboxService(ledger).items(PLAYER))


def test_actual_proposal_blocks_period_completion_until_real_human_decision(ledger):
    service, game, cycle, entitlement, period, identity = source(ledger)
    service.propose(
        PLAYER,
        "actual-pending-collective",
        entitlement,
        period,
        state(game).revision,
        "Actual pending descriptor",
        "Each Girl must make her own decision",
    )
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    roll_for(cycle, game, period, OTHER, (4, 4))
    call(cycle, game, OTHER, period, "scene", None, (), "")
    call(cycle, game, OTHER, period, "recover", RecoveryChoice())
    call(
        cycle,
        game,
        ADMIN,
        period,
        "handler_scene",
        "routine",
        (1, 2),
        "Actual source routine scene",
    )
    call(cycle, game, ADMIN, period, "acknowledge", None)
    call(cycle, game, PLAYER, period, "acknowledge", None)
    with ledger.engine.connect() as c:
        pending = cycle.periods._pending(c, period)
        assert {x["kind"] for x in pending} == {
            "collective_handler_tag_vote",
            "off_duty_status_review",
        }
    with pytest.raises(WorkflowError, match="actual work"):
        call(
            cycle,
            game,
            ADMIN,
            period,
            "review_status",
            (3, 2),
            "Cannot waive the pending real vote",
        )
    service.respond(OTHER, "actual-vote-before-phase-end", identity, state(game).revision, "agree")
    call(cycle, game, ADMIN, period, "review_status", (3, 2), "Actual review after the vote")
    result = call(cycle, game, ADMIN, period, "finish", movement(game))
    assert result["phase"] == "complete"


def test_unused_optional_opportunity_never_blocks_real_period_completion(ledger):
    service, game, cycle, entitlement, period, identity = source(ledger)
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    roll_for(cycle, game, period, OTHER, (4, 4))
    call(cycle, game, OTHER, period, "scene", None, (), "")
    call(cycle, game, OTHER, period, "recover", RecoveryChoice())
    finish_routine(cycle, game, period)
    assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"
    assert not state(game).handler_tags
    with pytest.raises(WorkflowError, match="unavailable"):
        service.view(PLAYER, identity)


def test_wrong_human_stale_pause_replay_and_actual_vote_work_are_source_bound(ledger):
    service, game, cycle, entitlement, period, identity = source(ledger)
    before = state(game)
    with pytest.raises(WorkflowError, match="actual original Girl"):
        service.propose(
            ADMIN,
            "handler-cannot-propose",
            entitlement,
            period,
            before.revision,
            "FORGED",
            "Not her decision",
        )
    with pytest.raises(WorkflowError, match="STALE"):
        service.propose(
            PLAYER,
            "stale-proposal",
            entitlement,
            period,
            before.revision - 1,
            "STALE",
            "An old form",
        )
    ledger.safety(OTHER, "collective-pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.propose(
            PLAYER,
            "paused-proposal",
            entitlement,
            period,
            before.revision,
            "PAUSED",
            "Paused source",
        )
    ledger.safety(OTHER, "collective-resume", ledger.status(OTHER)["revision"], pause=False)
    first = service.propose(
        PLAYER,
        "actual-one-proposal",
        entitlement,
        period,
        before.revision,
        "Actual descriptor",
        "Actual explicit proposal",
    )
    assert (
        service.propose(
            PLAYER,
            "actual-one-proposal",
            entitlement,
            period,
            before.revision,
            "Actual descriptor",
            "Actual explicit proposal",
        )
        == first
    )
    expected = state(game).revision
    with pytest.raises(WorkflowError, match="actual living original Girl"):
        service.respond(ADMIN, "handler-cannot-agree", identity, expected, "agree")
    actual = service.respond(OTHER, "actual-one-agreement", identity, expected, "agree")
    assert service.respond(OTHER, "actual-one-agreement", identity, expected, "agree") == actual
    assert len(state(game).handler_tags) == 1


def test_rollback_after_actual_proposal_and_final_gift_leaves_no_partial_tag_or_votes(
    ledger, monkeypatch
):
    service, game, cycle, entitlement, period, identity = source(ledger)
    before = state(game)
    original = service.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Synthetic canonical/outbox boundary failure")

    monkeypatch.setattr(service.game, "event", fail)
    with pytest.raises(RuntimeError):
        service.propose(
            PLAYER,
            "actual-retry-proposal",
            entitlement,
            period,
            before.revision,
            "Actual descriptor",
            "Actual proposal",
        )
    assert state(game) == before
    monkeypatch.setattr(service.game, "event", original)
    service.propose(
        PLAYER,
        "actual-retry-proposal",
        entitlement,
        period,
        before.revision,
        "Actual descriptor",
        "Actual proposal",
    )
    before_vote = state(game)
    monkeypatch.setattr(service.game, "event", fail)
    with pytest.raises(RuntimeError):
        service.respond(OTHER, "actual-retry-vote", identity, before_vote.revision, "agree")
    assert state(game) == before_vote
    with ledger.engine.connect() as c:
        assert any(
            x["kind"] == "collective_handler_tag_vote" for x in cycle.periods._pending(c, period)
        )
    monkeypatch.setattr(service.game, "event", original)
    service.respond(OTHER, "actual-retry-vote", identity, before_vote.revision, "agree")
    assert len(state(game).handler_tags) == 1


def test_receipt_is_immutable_and_tampered_period_projection_cannot_invent_a_roll(ledger):
    import json

    service, game, cycle, entitlement, period, identity = source(ledger)
    progress = cycle.periods._get
    with ledger.engine.connect() as c:
        action = progress(c, period).progress["2"].action_id
        receipts = t.m2["m2_receipts"]
        raw = json.loads(
            c.scalar(sa.select(receipts.c.body_json).where(receipts.c.action_id == action))
        )
        raw["faces"] = [6, 6]
    with pytest.raises(IntegrityError, match="append-only"), ledger.transaction() as c:
        c.execute(
            receipts.update()
            .where(receipts.c.action_id == action)
            .values(body_json=json.dumps(raw))
        )
    with ledger.transaction() as c:
        periods = t.m3["m3_off_duty"]
        raw = json.loads(c.scalar(sa.select(periods.c.body_json).where(periods.c.id == period)))
        raw["progress"]["2"]["roll"].update(faces=[6, 6], total=16)
        c.execute(periods.update().where(periods.c.id == period).values(body_json=json.dumps(raw)))
    before = state(game)
    with pytest.raises(WorkflowError, match="provenance"):
        service.propose(
            PLAYER,
            "cannot-use-forged-roll",
            entitlement,
            period,
            before.revision,
            "FORGED",
            "Not the original roll",
        )
    assert state(game) == before


def test_actual_original_handler_death_closes_votes_with_no_successor_consent_or_tag(ledger):
    from girlframe.engine import m3_handler_consequences as handler_rules

    service, game, cycle, entitlement, period, identity = source(ledger)
    service.propose(
        PLAYER,
        "actual-before-ending-proposal",
        entitlement,
        period,
        state(game).revision,
        "Private proposed descriptor",
        "Actual proposal",
    )
    with ledger.transaction() as c:
        canon = state(game)
        event = str(uuid4())
        canon, required = handler_rules.require(
            canon,
            handler_rules.active_handler(canon),
            trigger="asset_damage",
            source_action=None,
            source_work=entitlement,
            source_event="synthetic-established-real-handler-damage",
            opponent=current_ref(canon, 2),
            appointment="synthetic-original-appointment",
        )
        canon = handler_rules.apply(canon, required, "death", "The original Handler dies", event)
        game.event(
            c, 1, str(uuid4()), "synthetic.actual_original_handler_death", canon, event_id=event
        )
    view = service.view(ADMIN, identity)
    assert view["state"] == "ending_review" and view["proposal"] is None
    service.review_endings(ADMIN, "actual-source-ending-review", identity, state(game).revision)
    assert not state(game).handler_tags
    assert service.view(PLAYER, identity)["state"] == "original_ended"
    with ledger.engine.connect() as c:
        assert not [
            x
            for x in cycle.periods._pending(c, period)
            if x["kind"] == "collective_handler_tag_vote"
        ]


def test_original_handler_ending_before_install_does_not_orphan_the_actual_endgame(ledger):
    from girlframe.engine import m3_handler_consequences as handler_rules
    from girlframe.engine.m3_collective_handler_tags import entitlements

    _, game, _, identity, _ = endgame_source(ledger, option=6)
    service = CollectiveTagService(ledger)
    with pytest.raises(WorkflowError, match="actual original Handler's ending"):
        service.close_uninstalled(
            ADMIN, "cannot-close-living-endgame", identity, state(game).revision
        )
    with ledger.transaction() as c:
        canon = state(game)
        event = str(uuid4())
        canon, required = handler_rules.require(
            canon,
            handler_rules.active_handler(canon),
            trigger="asset_damage",
            source_action=None,
            source_work=identity,
            source_event="synthetic-real-preinstall-damage",
            opponent=current_ref(canon, 2),
            appointment="synthetic-original-source-appointment",
        )
        canon = handler_rules.apply(
            canon, required, "death", "The original Handler dies before install", event
        )
        game.event(
            c, 1, str(uuid4()), "synthetic.actual_preinstall_handler_death", canon, event_id=event
        )
    assert service.view(ADMIN, identity)["state"] == "ending_install"
    result = service.close_uninstalled(
        ADMIN, "close-actual-preinstall-ending", identity, state(game).revision
    )
    assert result["state"] == "original_ended" and not entitlements(state(game))
