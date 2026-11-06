"""Performed PR truth survives failed results and shared-cap/deferred award decisions."""

import asyncio
from uuid import uuid4

import pytest
from test_handler_ordinary import replace_starting, session_native, setup
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import open_advancement
from girlframe.discord_adapter.m3_handler_pr import open_pr
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary_rules
from girlframe.engine import m3_handler_pr as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_handler_pr import HandlerPRService
from girlframe.services.onboarding import WorkflowError


def plan(service, game, label):
    return service.plan(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "Foundation media fundraiser — " + label,
        "Actual public photoshoot and Foundation presentation",
        tuple(current_ref(state(game), uid) for uid in state(game).order),
    )["id"]


def native_action(service, identity, viewer, number, **values):
    async def run():
        inbox = InboxService(service.store)
        item = next(
            x for x in inbox.items(viewer) if x.task == "m3_handler_pr" and x.identity == identity
        )
        own = current(viewer.user_id, number)
        own.channel_id = 999
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        await form.confirm.callback(current(viewer.user_id, number + 1))
        assert form.completed

    asyncio.run(run())


def performed(service, game, identity, number):
    native_action(
        service,
        identity,
        ADMIN,
        number,
        operation=("host",),
        account="I actually hosted and presented this Foundation fundraiser",
    )
    native_action(
        service,
        identity,
        PLAYER,
        number + 2,
        account="My original Girl posed and described its Foundation work in the public feature",
    )
    native_action(
        service,
        identity,
        OTHER,
        number + 4,
        account="My original Girl actually performed the accompanying public interview",
    )
    native_action(
        service,
        identity,
        ADMIN,
        number + 6,
        operation=("submit",),
        account="The actual public material and hosted Cadre appearance are complete",
    )


def fill_identity_slot(game, ordinary, worker, gateway, session):
    starting = tuple(x.id for x in state(game).sheets["2"].identities)
    channel = 900
    for index, identity in enumerate(starting):
        channel = replace_starting(game, worker, gateway, identity, index, channel)
    review = ordinary.request_review(
        ADMIN,
        str(uuid4()),
        session,
        state(game).revision,
        current_ref(state(game), 2),
        "Actual completed starting Identity changes",
    )["id"]
    ordinary.disclose(
        PLAYER,
        str(uuid4()),
        review,
        state(game).revision,
        True,
        "Share actual replacements with the original Handler",
    )
    data = ordinary.menu(ADMIN, review)
    return ordinary.grant_identity_award(
        ADMIN,
        str(uuid4()),
        review,
        data["revision"],
        {x["id"]: "This actual replacement helps my Handler's work" for x in data["identities"]},
        "Actual useful replacement accomplishment",
    )["id"]


def test_actual_pr_failure_cross_session_truth_shared_cap_deferred_claim_real_spend(
    ledger, tmp_path, monkeypatch
):
    game, ordinary, worker, gateway = setup(ledger, tmp_path, monkeypatch)
    pr = HandlerPRService(ledger)
    first_session = session_native(ordinary, "Actual opening PR Session", 37000)
    failed = plan(pr, game, "first actual event")
    before = state(game)
    with pytest.raises(WorkflowError):
        pr.submit_result(
            ADMIN, str(uuid4()), failed, before.revision, "A plan is not a performed event"
        )
    assert not awards.awards(state(game))
    native_action(
        pr,
        failed,
        ADMIN,
        37010,
        operation=("host",),
        account="I actually hosted the opening public presentation",
    )
    native_action(
        pr, failed, PLAYER, 37012, account="My Girl actually posed for the Foundation media feature"
    )
    ordinary.end_session(
        ADMIN,
        str(uuid4()),
        first_session,
        state(game).revision,
        "Actual facilitator ends this Session while event conduct continues later",
    )
    current_session = session_native(ordinary, "Actual continuing PR Session", 37020)
    native_action(
        pr,
        failed,
        OTHER,
        37022,
        account="My original Girl completed its real public interview in this later Session",
    )
    native_action(
        pr,
        failed,
        ADMIN,
        37024,
        operation=("submit",),
        account="The performed event has reached its actual public result",
    )
    native_action(
        pr,
        failed,
        ADMIN,
        37026,
        result=("failure",),
        account="The actual public feature failed the Foundation fundraising objective",
    )
    assert not awards.awards(state(game)) and not ordinary_rules.marks(state(game))
    assert next(x for x in rules.events(state(game)) if x.id == failed).successful is False
    assert (
        state(game).sheets == before.sheets
        and state(game).world == before.world
        and state(game).placements == before.placements
    )
    identity_award = fill_identity_slot(game, ordinary, worker, gateway, current_session)
    assert awards.awards(state(game))[0].id == identity_award
    successful = plan(pr, game, "second genuinely performed event")
    performed(pr, game, successful, 37040)
    result_args = (
        ADMIN,
        "37049",
        successful,
        state(game).revision,
        True,
        "PRIVATE_PUBLIC_RESULT: the actual fundraiser achieved its Foundation objective",
    )
    native_action(pr, successful, ADMIN, 37048, result=("success",), account=result_args[-1])
    saved = next(x for x in rules.events(state(game)) if x.id == successful)
    assert (
        saved.successful is True
        and saved.award is None
        and saved.award_blocked == "session_slot_used"
    )
    assert pr.resolve(*result_args) == dict(
        id=successful, phase="complete", successful=True, award=None
    )
    with pytest.raises(WorkflowError):
        pr.claim(ADMIN, str(uuid4()), successful, state(game).revision)
    assert next(x for x in rules.events(state(game)) if x.id == successful).successful is True
    ordinary.end_session(
        ADMIN,
        str(uuid4()),
        current_session,
        state(game).revision,
        "Actual Session end does not erase completed successful PR",
    )
    award_session = session_native(ordinary, "Actual later free award Session", 37060)
    claim_revision = state(game).revision
    native_action(pr, successful, ADMIN, 37062, claim=("claim",))
    value = next(x for x in rules.events(state(game)) if x.id == successful)
    assert (
        value.award
        and value.planned_session == current_session
        and value.award_session == award_session
    )
    assert pr.claim(ADMIN, "37063", successful, claim_revision) == dict(
        id=successful, phase="complete", award=value.award
    )
    assert {x.trigger for x in ordinary_rules.marks(state(game))} == {
        "identities_useful",
        "public_relations",
    }
    before_permissions = state(game).sheets["2"].permissions

    async def spend():
        service = HandlerAdvancementService(ledger)
        own = current(1, 37070)
        await own.response.defer(ephemeral=True)
        await open_advancement(own, service, value.award)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(girls=(current_ref(state(game), 2).token,))
        step = current(1, 37071)
        await form.confirm.callback(step)
        amounts = step.edit_original_response.call_args.kwargs["view"]
        amounts.values.update(
            {current_ref(state(game), 2).token: ("2",)},
            account="Real saved successful PR award grants two actual Permissions",
        )
        await amounts.confirm.callback(current(1, 37072))
        assert amounts.completed
        await open_advancement(own, service, value.award)
        assert "Ordinary public-relations" in own.edit_original_response.call_args.kwargs["content"]

    asyncio.run(spend())
    assert state(game).sheets["2"].permissions == before_permissions + 2
    later = plan(pr, game, "real event after criterion mark")
    performed(pr, game, later, 37080)
    native_action(
        pr,
        later,
        ADMIN,
        37088,
        result=("success",),
        account="Another actual event succeeded despite the permanent criterion mark",
    )
    marked_success = next(x for x in rules.events(state(game)) if x.id == later)
    assert (
        marked_success.successful is True
        and marked_success.award is None
        and marked_success.award_blocked == "criterion_marked"
    )
    assert len(awards.awards(state(game))) == 2

    async def history():
        own = current(1, 37100)
        own.channel_id = 999
        await own.response.defer(ephemeral=True)
        await open_pr(own, pr, successful)
        assert "successful" in own.edit_original_response.call_args.kwargs["content"]

    asyncio.run(history())
    assert HandlerAdvancementService(ledger).view(ADMIN, value.award)["phase"] == "spent"
