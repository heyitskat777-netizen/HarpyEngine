"""Paid secret hardware → current location/real Plays → actual removal and site Void."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current
from test_secretary import ready as actual_award

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import AcquireTracker, open_advancement
from girlframe.discord_adapter.m3_handler_plays import open_play
from girlframe.discord_adapter.m3_tracker_implants import open_tracker
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_tracker_implants as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_items import prove_item
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_tracker_implants import TrackerService, prove_tracker_play
from girlframe.services.onboarding import WorkflowError


def interaction(uid=1, channel=900):
    own = current(uid, int(uuid4().int % 1000000000))
    own.channel_id = channel
    return own


def native_acquire(service, game, award):
    async def run():
        own = interaction()
        await own.response.defer(ephemeral=True)
        await open_advancement(own, HandlerAdvancementService(service.store), award.id)
        view = own.edit_original_response.call_args.kwargs["view"]
        # Actual existing award route, at Discord's real maximum row capacity.
        assert len([x for x in view.children if x.row == 2]) == 5
        button = next(x for x in view.children if isinstance(x, AcquireTracker))
        step = interaction()
        await step.response.defer(ephemeral=True)
        await button.callback(step)
        form = step.edit_original_response.call_args.kwargs["view"]
        canon = state(game)
        asset = next(x for x in canon.sheets["2"].assets if x.family == "girl" and not x.void)
        form.values.update(
            award=(award.id,),
            site_0="left hand",
            asset_0=(asset.id,),
            site_1="right ankle",
            asset_1=("none",),
            actual=("actual",),
            account="I actually install the same two distinct secret physical trackers",
        )
        confirmed = interaction()
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args

    asyncio.run(run())


def perform_native(plays, identity, kind, actor, *, detail=None):
    async def run():
        own = interaction()
        await own.response.defer(ephemeral=True)
        await open_play(own, plays, identity)
        picker = own.edit_original_response.call_args.kwargs["view"]
        step = interaction()
        await step.response.defer(ephemeral=True)
        await picker.open_item(step, kind)
        form = step.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            target=(actor.token,),
            account="I actually "
            + (
                "intercept her in this room"
                if kind == "tracker_intercept"
                else "observe the supplied private fictional moment"
            ),
        )
        confirmed = interaction()
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args

    asyncio.run(run())


def dive(game, worker, gateway, viewer, asset):
    game.dice = Dice((4, 5))
    identity = game.begin(
        viewer,
        str(uuid4()),
        900,
        state(game).sheets[str(viewer.user_id)].revision,
        PlayInput(
            play="dive_deep",
            heat=0,
            context="Actual link communion alters this body part",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, viewer, "dive_select", options=("void_and_unmark_all",), text="Actual communion")
    answer(
        game,
        viewer,
        "dive_effect",
        fields={"asset": asset},
        text="Actual Void manifests in my original flesh",
    )
    assert game.inspect(viewer, identity)["state"] == "complete"
    tick(worker, gateway, 6)
    with game.store.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        event = c.scalar(
            sa.select(t.m2["m2_responses"].c.event_id)
            .join(
                t.m2["m2_choices"],
                sa.and_(
                    t.m2["m2_choices"].c.campaign_id == t.m2["m2_responses"].c.campaign_id,
                    t.m2["m2_choices"].c.id == t.m2["m2_responses"].c.choice_id,
                ),
            )
            .where(
                t.m2["m2_choices"].c.action_id == identity,
                t.m2["m2_choices"].c.kind == "dive_effect",
            )
        )
    assert game.dice.calls == 1
    return event


def test_native_secret_tracker_location_both_plays_real_removal_and_exact_site_void(
    ledger, tmp_path, monkeypatch
):
    game, _, worker, gateway = actual_award(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ordinary.RULE, rules.RULE))
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={
                    "subsystems": ledger.policy.m3_approval.subsystems
                    | {"world", "plays", "discipline"}
                }
            )
        }
    )
    casts = CastService(ActorService(MissionService(ledger)))
    handler = current_ref(state(game), 1)
    change(casts, ADMIN, "join", handler)
    service = TrackerService(ledger)
    held = next(x for x in awards.awards(state(game)) if x.phase == "held")
    before = state(game)
    native_acquire(service, game, held)
    source = rules.acquisitions(state(game))[0]
    first, second = source.implants
    assert state(game).sheets == before.sheets and state(game).bonds == before.bonds
    assert len(source.implants) == len(state(game).order)
    assert first.vessel != first.actor.incarnation and second.asset is None
    assert service.menu(ADMIN, source.id)["implants"][0]["cell"] == (0, 0)

    async def establish_initial_presence():
        own = interaction()
        await own.response.defer(ephemeral=True)
        await open_tracker(own, service, source.id)
        picker = own.edit_original_response.call_args.kwargs["view"]
        step = interaction()
        await step.response.defer(ephemeral=True)
        await picker.open_item(step, "presence")
        form = step.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            tracker=(first.id,),
            account="My original Handler body is actually initially present in this room",
        )
        confirmed = interaction()
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args

    asyncio.run(establish_initial_presence())
    with pytest.raises(WorkflowError):
        service.record_initial_presence(
            ADMIN,
            str(uuid4()),
            source.id,
            state(game).revision,
            second.id,
            "Cannot move an already known body",
        )
    assert "implants" not in service.menu(PLAYER)
    with pytest.raises(WorkflowError):
        service.menu(PLAYER, source.id)
    # Existing real physical consumer changes the body's cockpit placement; location
    # is resolved from that new source, never cached at implant acquisition.
    physical = PhysicalService(ledger)
    physical.operate(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        CockpitAction(
            actor=first.actor,
            operation="sit",
            expected_position=physical.preview(PLAYER)["position_sha256"],
            account="I actually enter my parked Frame",
            confirmed=True,
        ),
    )
    assert service.menu(ADMIN, source.id)["implants"][0]["cell"] == (0, 0)
    physical.operate(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        CockpitAction(
            actor=first.actor,
            operation="exit",
            expected_position=physical.preview(PLAYER)["position_sha256"],
            account="I actually leave the cockpit for this room",
            confirmed=True,
        ),
    )
    # Both real Plays finish through actual native HandlerPlay forms.
    plays = HandlerPlayService(ledger)
    contact = service.start_play(
        ADMIN, str(uuid4()), state(game).revision, first.id, "tracker_intercept", 900
    )
    perform_native(plays, contact["id"], "tracker_intercept", first.actor)
    assert "intercept" in plays.notice(PLAYER, contact["id"])["account"]
    text = "PRIVATE_FICTION: I quietly mend the ribbon from my original home."
    moment = service.record_moment(PLAYER, str(uuid4()), state(game).revision, 900, text)
    observed = service.start_play(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        first.id,
        "tracker_voyeur",
        900,
        moment=moment["id"],
    )
    perform_native(plays, observed["id"], "tracker_voyeur", first.actor)
    assert plays.notice(ADMIN, observed["id"])["detail"] == text
    with pytest.raises(WorkflowError):
        plays.notice(OTHER, observed["id"])
    with ledger.engine.connect() as c:
        assert not any(x["id"] == observed["id"] for x in plays._notices(c, PLAYER))
    # Ordinary grants have neither new entitlement; counterfeit source facts do not help.
    basic = plays.start(ADMIN, str(uuid4()), state(game).revision, (first.actor,))["id"]
    with pytest.raises(WorkflowError, match="tracker authority"):
        plays.submit(
            ADMIN,
            str(uuid4()),
            basic,
            state(game).revision,
            "tracker_intercept",
            Effect(
                kind="tracker_intercept", target=first.actor, account="Forged free interception"
            ),
        )
    plays.withdraw(ADMIN, str(uuid4()), basic, state(game).revision)
    forged = next(x for x in state(game).handler_plays if x.id == contact["id"]).model_copy(
        update={"clause": "tracker:" + second.id}
    )
    with ledger.engine.connect() as c, pytest.raises(WorkflowError):
        prove_tracker_play(game, c, state(game), forged)
    # Actual mapped body-part Void is observed automatically, from its genuine Dive source.
    first_event = dive(game, worker, gateway, PLAYER, first.asset)
    alerts = rules.records(state(game), rules.Alert)
    assert (
        len(alerts) == 1 and alerts[0].source_event == first_event and alerts[0].tracker == first.id
    )
    # Unmapped anatomy remains supported without adding an invented starting Asset.
    asset = next(x for x in state(game).sheets["3"].assets if x.family == "girl" and not x.void)
    second_event = dive(game, worker, gateway, OTHER, asset.id)
    assert len(rules.records(state(game), rules.Alert)) == 1
    with pytest.raises(WorkflowError):
        service.record_site_void(
            ADMIN, str(uuid4()), state(game).revision, second_event, asset.id, "right ankle"
        )
    with pytest.raises(WorkflowError):
        service.record_site_void(
            OTHER, str(uuid4()), state(game).revision, source.event, asset.id, "right ankle"
        )
    site_key = str(uuid4())
    site_revision = state(game).revision
    result = service.record_site_void(
        OTHER, site_key, site_revision, second_event, asset.id, "right ankle"
    )
    assert (
        service.record_site_void(
            OTHER, site_key, site_revision, second_event, asset.id, "right ankle"
        )
        == result
    )
    assert len(rules.records(state(game), rules.Alert)) == 2
    # Physical removal by original affected human recovers SAME object, stops new Plays.
    key = str(uuid4())
    revision = state(game).revision
    removed = service.remove(
        PLAYER,
        key,
        revision,
        first.id,
        first.actor,
        "I actually find and remove this implant from my hand",
        actual=True,
    )
    assert (
        service.remove(
            PLAYER,
            key,
            revision,
            first.id,
            first.actor,
            "I actually find and remove this implant from my hand",
            actual=True,
        )
        == removed
    )
    with ledger.engine.connect() as c:
        recovered = prove_item(c, game, state(game), first.id)
        assert (
            recovered.holder == first.actor
            and recovered.origin_event == source.event
            and recovered.asset_id is None
        )
    assert not service.menu(ADMIN, source.id)["implants"][0]["attached"]
    with pytest.raises(WorkflowError):
        service.start_play(
            ADMIN, str(uuid4()), state(game).revision, first.id, "tracker_intercept", 900
        )
    assert len(rules.records(state(game), rules.Alert)) == 3

    async def reopen():
        inbox = InboxService(ledger)
        row = next(
            x
            for x in inbox.items(ADMIN)
            if x.task == "m3_tracker_implants" and x.identity == source.id
        )
        own = interaction(channel=901)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, row)
        content = own.edit_original_response.call_args.kwargs["content"]
        assert "actually removed" in content and second_event in content
        assert not own.edit_original_response.call_args.kwargs["allowed_mentions"].everyone
        observation = next(
            x
            for x in inbox.items(ADMIN)
            if x.identity == observed["id"] and x.task == "m3_handler_notice"
        )
        own = interaction(channel=902)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, observation)
        assert (
            "I quietly mend the ribbon from my original home."
            in own.edit_original_response.call_args.kwargs["content"]
        )

    asyncio.run(reopen())
    with ledger.engine.connect() as c:
        payloads = " ".join(c.scalars(sa.select(t.events.c.payload_json)))
        assert (
            text not in payloads and "left hand" not in payloads and "right ankle" not in payloads
        )
        assert text not in json.dumps(gateway.messages)
    saved = state(game)
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    game.rebuild()
    assert state(game) == saved
    assert TrackerService(ledger).menu(ADMIN, source.id)["alerts"]
