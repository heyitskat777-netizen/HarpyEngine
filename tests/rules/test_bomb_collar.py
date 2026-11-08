"""Actual paid collars remain permanent Tags; real source Plays survive or end a career."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current
from test_secretary import ready as ordinary_award

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_bomb_collar import open_collar
from girlframe.engine import m3_bomb_collar as rules
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary_rules
from girlframe.engine.m2 import PlayInput
from girlframe.services.inbox import InboxService
from girlframe.services.m3_bomb_collar import BombCollarService, complete_action, work
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    game, _, worker, gateway = ordinary_award(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(ordinary_rules.RULE, rules.RULE))
    service = BombCollarService(store, game)
    held = next(x for x in awards.awards(state(game)) if x.phase == "held")
    revision = state(game).revision

    async def buy():
        own = current(1, 42000)
        await own.response.defer(ephemeral=True)
        await open_collar(own, service)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            award=(held.id,), account="Actual held advancement supplies Cadre collars"
        )
        await form.confirm.callback(current(1, 42001))
        assert form.completed

    asyncio.run(buy())
    assert len(rules.collars(state(game))) == len(state(game).order) == 2
    assert all(x.vessel for x in rules.collars(state(game)))
    with pytest.raises(WorkflowError):
        service.buy(ADMIN, str(uuid4()), held.id, revision, "Never recharge the spent award")
    game.dice = Dice((3, 4))
    return game, service, worker, gateway


def keep(game, viewer, action, enough=True):
    answer(game, viewer, "actor_keep", options=("tough", "sexy"), denied=("in_control",))
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=enough,
        text="Actual detonation escape is sufficient"
        if enough
        else "The actual explosion kills it; its escape was insufficient",
    )
    assert game.inspect(viewer, action)["state"] == "complete"


def trigger(service, game, viewer, channel):
    collar = next(x for x in rules.collars(state(game)) if x.target.entity == str(viewer.user_id))

    async def run():
        own = current(1, int(uuid4().int % 1000000000))
        own.channel_id = channel
        await own.response.defer(ephemeral=True)
        await open_collar(own, service)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            collar=(collar.id,),
            scene=(str(channel),),
            account="Original Handler actually triggers this body's bomb collar",
        )
        confirmed = current(1, int(uuid4().int % 1000000000))
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args

    asyncio.run(run())
    return next(x for x in rules.triggers(state(game)) if x.collar == collar.id)


def respond(service, game, value, viewer, play):
    async def run():
        inbox = InboxService(service.store)
        item = next(
            x for x in inbox.items(viewer) if x.task == "m3_bomb_collar" and x.identity == value.id
        )
        assert item.incoming
        own = current(viewer.user_id, int(uuid4().int % 1000000000))
        own.channel_id = 999
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=(play,),
            gain=("0",),
            heat=("0",),
            piloting=("no",),
            context="My actual original Girl responds to the real detonation",
        )
        confirmed = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args

    asyncio.run(run())
    with service.store.engine.connect() as c:
        actions = t.m2["m2_actions"]
        return c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == service.store.campaign_id,
                sa.func.json_extract(actions.c.body_json, "$.bomb_collar_source.work") == value.id,
            )
        )


def test_actual_collar_repeated_tag_no_resolution_then_genuine_dive_survives(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    collar = next(x for x in rules.collars(state(game)) if x.target.entity == "2")
    for channel in (900, 901):
        if channel == 901:
            game.close_scene(ADMIN, str(uuid4()), 900)
            game.bind_scene(ADMIN, str(uuid4()), channel)
            for viewer in (ADMIN, PLAYER, OTHER):
                game.join_scene(viewer, str(uuid4()), channel)
        action = game.begin(
            PLAYER,
            str(uuid4()),
            channel,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="Actual collar is relevant while resisting an instruction",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        answer(game, PLAYER, "tag_window", options=("pass",))
        answer(
            game,
            OTHER,
            "tag_window",
            options=("tag",),
            denied=(collar.id,),
            number=1,
            text="Its actual bomb collar constrains this rebellious action",
        )
        answer(game, ADMIN, "tag_window", options=("pass",))
        assert not any(x["kind"] in ("tag_resolution", "paired_tag") for x in game.choices(PLAYER))
        keep(game, PLAYER, action)
        tick(worker, gateway, 5)
        current_collar = next(x for x in rules.collars(state(game)) if x.id == collar.id)
        assert current_collar.tag.marked and current_collar.tag.scene_used
        assert all(x.id != collar.id for x in state(game).sheets["2"].tags)
    value = trigger(service, game, PLAYER, 901)
    with pytest.raises(WorkflowError, match="REQUIRED_FOLLOWUP"):
        game.begin(
            PLAYER,
            str(uuid4()),
            901,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head", heat=0, context="Unrelated action", trigger_confirmed=True
            ),
        )
    before = state(game).sheets["2"]
    game.dice.faces = (4, 5)
    action = respond(service, game, value, PLAYER, "dive_deep")
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("void_and_unmark_all",),
        text="Actual flesh communion gets me through detonation",
    )
    asset = next(x for x in before.assets if not x.void and x.family == "girl")
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"asset": asset.id},
        text="Actual flesh takes on the Frame's un-real protection",
    )
    after = state(game)
    outcome = next(x for x in rules.triggers(after) if x.id == value.id)
    assert outcome.phase == "survived" and outcome.action == action
    assert next(x for x in after.sheets["2"].assets if x.id == asset.id).void
    assert not rules.tags(after, 2) and game.inspect(PLAYER, action)["state"] == "complete"
    with ledger.transaction() as c:
        assert work(game, c, value.id)["state"] == "resolved"
        before_replay = state(game).model_dump_json()
        complete_action(
            game, c, game.action(c, action), outcome.result_event, "replayed-completion"
        )
        assert state(game).model_dump_json() == before_replay
    tick(worker, gateway, 5)


def test_actual_keep_survival_and_lethal_failed_escape_end_original_career_history(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    game.dice.faces = (4, 5)
    surviving = trigger(service, game, PLAYER, 900)
    first = respond(service, game, surviving, PLAYER, "keep_your_head")
    tick(worker, gateway, 3)
    pass_tags(game)
    keep(game, PLAYER, first)
    tick(worker, gateway, 5)
    assert next(x for x in rules.triggers(state(game)) if x.id == surviving.id).phase == "survived"
    doomed = trigger(service, game, OTHER, 900)
    original = doomed.target
    second = respond(service, game, doomed, OTHER, "keep_your_head")
    tick(worker, gateway, 3)
    pass_tags(game)
    keep(game, OTHER, second, enough=False)
    actual = state(game)
    value = next(x for x in rules.triggers(actual) if x.id == doomed.id)
    archive = next(x for x in actual.career_archives if x.id == value.archive)
    assert value.phase == "death" and archive.actor == original and archive.ending == "death"
    assert "3" not in actual.sheets and 3 not in actual.order
    assert service.menu(OTHER, value.id)["body"]["archive"] == archive.id
    tick(worker, gateway, 5)

    async def history():
        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(OTHER) if x.task == "m3_bomb_collar" and x.identity == value.id
        )
        assert not item.incoming
        own = current(3, 42300)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 3).route(own, item)
        assert "death" in str(own.edit_original_response.call_args)

    asyncio.run(history())
