"""Actual held award, real memory scene/Play, both printed returns and private source history."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_handler_advancements import native_claim, source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_deep_brain_spikes import open_spikes
from girlframe.discord_adapter.m3_handler_advancements import open_advancement
from girlframe.engine import m3_deep_brain_spikes as rules
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.services.inbox import InboxService
from girlframe.services.m3_deep_brain_spikes import DeepBrainSpikesService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError


def begin_native(service, acquisition, subject, number, *, mode="watching", period="offscreen"):
    async def run():
        own = current(1, number)
        await own.response.defer(ephemeral=True)
        await open_spikes(own, service, acquisition)
        scenes = own.edit_original_response.call_args.kwargs["view"]
        with service.store.engine.connect() as c:
            scene = service.game.scene(c, 900)
        scenes.values.update(scene=(scene["id"],))
        next_step = current(1, number + 1)
        await scenes.confirm.callback(next_step)
        assert scenes.completed
        setup = next_step.edit_original_response.call_args.kwargs["view"]
        setup.values.update(
            subject=(subject.token,),
            mode=(mode,),
            period=(period,),
            beginning="PRIVATE remembered offscreen briefing before the alarm",
            circumstances="PRIVATE present alarm signal has the same rhythm",
        )
        result = current(1, number + 2)
        await setup.confirm.callback(result)
        assert setup.completed, result.edit_original_response.call_args_list

    asyncio.run(run())
    return rules.memories(state(service.game))[-1].id


def memory_native(service, identity, viewer, number, **values):
    async def run():
        inbox = InboxService(service.store)
        item = next(
            x
            for x in inbox.items(viewer)
            if x.task == "m3_deep_brain_spikes" and x.identity == identity
        )
        own = current(viewer.user_id, number)
        own.channel_id = 999
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        result = current(viewer.user_id, number + 1)
        await form.confirm.callback(result)
        assert form.completed, result.edit_original_response.call_args_list

    asyncio.run(run())


def test_real_memory_context_current_play_relevance_and_discrepancy_return_keep_present(
    ledger, tmp_path, monkeypatch
):
    strain, game, awards, award = source(ledger, tmp_path, monkeypatch, 6)
    approved(ledger, game, tmp_path, monkeypatch, extra=(*advancement.RULES, rules.RULE))
    native_claim(awards, award, 41000)
    held = state(game)
    spikes = DeepBrainSpikesService(ledger)

    async def acquire():
        own = current(1, 41010)
        await own.response.defer(ephemeral=True)
        await open_advancement(own, awards, award)
        grant = own.edit_original_response.call_args.kwargs["view"]
        button = next(x for x in grant.children if x.label == "Acquire Deep-Brain-Spikes instead")
        step = current(1, 41011)
        await step.response.defer(ephemeral=True)
        await button.callback(step)
        form = step.edit_original_response.call_args.kwargs["view"]
        form.values.update(award=(award,), account="PRIVATE genuine Deep-Brain-Spikes acquisition")
        await form.confirm.callback(current(1, 41012))
        assert form.completed

    asyncio.run(acquire())
    acquisition = rules.acquisitions(state(game))[0]
    revision = held.revision
    assert (
        spikes.buy(
            ADMIN, "41012", award, revision, "PRIVATE genuine Deep-Brain-Spikes acquisition"
        )["id"]
        == acquisition.id
    )
    assert len(rules.acquisitions(state(game))) == 1
    assert advancement.awards(state(game))[0].acquired_rule == rules.RULE
    subject = current_ref(state(game), 2)
    # A genuine current Tag supplies the same-source quota identity. Its already-used
    # present-scene bookkeeping is fixture state; the memory mark is a real owned Play choice.
    plays = HandlerPlayService(ledger)
    grant = plays.start(ADMIN, str(uuid4()), state(game).revision, (subject,))
    plays.submit(
        ADMIN,
        str(uuid4()),
        grant["id"],
        state(game).revision,
        "mess",
        Effect(
            kind="tag",
            target=subject,
            tag="PRIVATE old briefing",
            account="Actual known shared memory",
        ),
    )
    with ledger.transaction() as c:
        present = game.scene(c, 900)
        canon = state(game)
        tag = next(x for x in canon.sheets["2"].tags if x.label == "PRIVATE old briefing")
        tag.scene_used = present["id"]
        tag_id = tag.id
        game.event(c, 1, str(uuid4()), "synthetic.actual_present_tag_quota", canon)
    before = state(game)
    worker, gateway = GameWorker(game), Gateway()
    identity = begin_native(spikes, acquisition.id, subject, 41020)
    active = state(game)
    memory = rules.memories(active)[0]
    assert (
        active.sheets == before.sheets
        and active.world == before.world
        and active.placements == before.placements
    )
    assert game.scene_info(PLAYER, 900)["memory"]["present_scene"] == present["id"]
    with ledger.engine.connect() as c:
        assert game.scene(c, 900)["id"] == memory.scene != present["id"]
    with pytest.raises(WorkflowError, match="return|Return|relevance"):
        game.close_scene(ADMIN, str(uuid4()), 900)
    memory_native(
        spikes,
        identity,
        PLAYER,
        41030,
        operation=("contribute",),
        account="PRIVATE I remember speaking during that offscreen briefing",
    )
    # A genuine current-actor response to disturbing memory has a real cost and result.
    game.dice = Dice((3, 3))
    sheet = state(game).sheets["2"]
    chosen = next(x.id for x in sheet.identities if not x.marked)
    heat = sheet.heat + 1 if sheet.heat >= 5 else 1
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        sheet.revision,
        PlayInput(
            play="keep_your_head",
            identity=chosen,
            gain=1,
            heat=heat,
            context="Disturbing remembered experience affects my actual composure",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    with pytest.raises(WorkflowError, match="Play|permissions|consequences"):
        spikes.return_present(
            ADMIN,
            str(uuid4()),
            identity,
            state(game).revision,
            "relevance_clear",
            "Pending Play cannot be discarded",
        )
    for viewer in (PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(
        game,
        ADMIN,
        "tag_window",
        options=("tag",),
        denied=(tag_id,),
        number=1,
        text="The actual remembered briefing bears on current composure",
    )
    answer(game, PLAYER, "actor_keep", options=("tough", "sexy"), denied=("in_control",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual current Girl's Keep result")
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert (
        next(x for x in state(game).sheets["2"].tags if x.id == tag_id).scene_used == memory.scene
    )
    memory_native(
        spikes,
        identity,
        PLAYER,
        41040,
        operation=("contribute",),
        action=action,
        account="PRIVATE My actual composure response clarifies what that memory means",
    )
    after_play = state(game)
    revision = after_play.revision
    memory_native(
        spikes,
        identity,
        ADMIN,
        41050,
        operation=("return",),
        cause=("relevance_clear",),
        account="PRIVATE That briefing's alarm instruction explains our present signal",
    )
    returned = state(game)
    result = spikes.return_present(
        ADMIN,
        "41051",
        identity,
        revision,
        "relevance_clear",
        "PRIVATE That briefing's alarm instruction explains our present signal",
    )
    assert result["scene"] == present["id"] and state(game) == returned and game.dice.calls == 1
    assert returned.world == before.world and returned.placements == before.placements
    assert returned.sheets["2"].heat == after_play.sheets["2"].heat
    assert next(x for x in returned.sheets["2"].identities if x.id == chosen).marked
    restored_tag = next(x for x in returned.sheets["2"].tags if x.id == tag_id)
    assert restored_tag.marked and restored_tag.scene_used == present["id"]
    assert game.scene_info(PLAYER, 900)["memory"] is None
    with ledger.engine.connect() as c:
        assert game.scene(c, 900)["id"] == present["id"]
    # Second printed cause: actual discrepancies, with no mandatory roll/acknowledgment.
    second = begin_native(
        spikes, acquisition.id, subject, 41060, mode="there", period="before_game"
    )
    before_return = state(game)
    memory_native(
        spikes,
        second,
        ADMIN,
        41070,
        operation=("return",),
        cause=("major_discrepancy",),
        account="PRIVATE The remembered equipment predates its invention; discrepancy is too major",
    )
    final = state(game)
    assert final.sheets == before_return.sheets and final.world == before_return.world
    assert final.placements == before_return.placements and game.dice.calls == 1
    assert [x.return_cause for x in rules.memories(final)] == [
        "relevance_clear",
        "major_discrepancy",
    ]
    assert len(advancement.awards(final)) == 1 and advancement.awards(final)[0].phase == "spent"
    assert len(rules.acquisitions(final)) == 1

    async def history():
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(PLAYER)
            if x.task == "m3_deep_brain_spikes" and x.identity == second
        )
        own = current(2, 41080)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(own, item)
        assert "major_discrepancy" in own.edit_original_response.call_args.kwargs["content"]

    asyncio.run(history())
    with ledger.engine.connect() as c:
        assert "PRIVATE" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
