"""Real private memory readback preserves every rendered character within Discord budgets."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import uuid4

import discord
import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_handler_advancements import native_claim, source
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m3_deep_brain_spikes import open_spikes
from girlframe.discord_adapter.m3_memory_pages import (
    LIMIT,
    MemoryForm,
    MemoryHistory,
    paginate,
    text_units,
)
from girlframe.engine import m3_deep_brain_spikes as rules
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.inbox import InboxService
from girlframe.services.m3_deep_brain_spikes import DeepBrainSpikesService
from girlframe.services.onboarding import WorkflowError


def difficult(label, size):
    beginning = "BEGIN_" + label + " \\_*` [text] <@2> @everyone\n"
    ending = "\nEND_" + label
    middle = "Ω🙂e\u0301👩\u200d🚀\n" * 8 + "MIDDLE_" + label + "\n"
    return beginning + middle + "Q" * (size - len(beginning + middle + ending)) + ending


def payload(interaction):
    if interaction.edit_original_response.called:
        result = interaction.edit_original_response.call_args.kwargs
    else:
        result = next(
            value for kind, value in reversed(interaction.response.events) if kind == "send"
        )
        assert result["ephemeral"] is True
    assert text_units(result["content"]) <= LIMIT
    assert result["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
    assert len(interaction.response.events) <= 1
    return result


def test_rendered_boundaries_empty_exact_fit_over_multiples_and_page_counter_width():
    heading = "Private memory"
    capacity = LIMIT - text_units(heading + " (1/1)\n")
    for count in (0, 1, capacity, capacity + 1, capacity * 2, capacity * 2 + 17):
        text = "Z" * count
        pages = paginate(text, heading)
        assert "".join(x.body for x in pages) == text
        assert all(text_units(x.content) <= LIMIT for x in pages)
        if count <= capacity:
            assert len(pages) == 1
        if count == capacity:
            assert text_units(pages[0].content) == LIMIT
        if count == capacity + 1:
            assert len(pages) == 2
    wide_capacity = LIMIT - text_units(heading + " (12/12)\n")
    pages = paginate("Z" * (wide_capacity * 12), heading)
    assert len(pages) == 12
    assert all(text_units(x.content) == LIMIT for x in pages[9:])
    assert "".join(x.body for x in pages) == "Z" * (wide_capacity * 12)
    assert len(paginate("Z" * (wide_capacity * 12 + 1), heading)) == 13


def test_escaping_unicode_unbroken_tokens_and_whitespace_are_lossless():
    for raw in (
        difficult("ESCAPING", 1800),
        "\\*_*`@everyone\n" * 500,
        "🙂" * 1800,
        "👩\u200d🚀e\u0301🇺🇸" * 600,
        "x" + "\u0301" * 1800,
        "  before\n\n\t" + "Q" * 12000 + "\n after  ",
    ):
        rendered = clean(raw)
        pages = paginate(rendered, "Memory")
        assert "".join(x.body for x in pages) == rendered
        assert all(text_units(x.content) <= LIMIT and len(x.content) <= LIMIT for x in pages)
        assert all(x.content.encode("utf-16-le") for x in pages)  # No split surrogate/code point.
        for page in pages:
            slashes = len(page.body) - len(page.body.rstrip("\\"))
            assert slashes % 2 == 0  # A Markdown escape cannot straddle messages.
        if raw.startswith("👩"):
            assert all(
                not x.body.startswith("\u200d") and not x.body.endswith("\u200d") for x in pages
            )
    assert len(clean("\\_*`" * 300)) > len("\\_*`" * 300)


async def enter(form, key, text):
    target = next(i for i, field in enumerate(form.fields) if field.key == key)
    while form.index < target:
        interaction = current(form.owner, uuid4().int % 1000000000)
        await form.next.callback(interaction)
        payload(interaction)
    modal_interaction = current(form.owner, uuid4().int % 1000000000)
    modal_interaction.response.send_modal = AsyncMock()
    await form.edit.callback(modal_interaction)
    modal = modal_interaction.response.send_modal.call_args.args[0]
    assert modal.input.max_length == 1200
    modal.input._value = text
    submitted = current(form.owner, uuid4().int % 1000000000)
    await modal.on_submit(submitted)
    payload(submitted)


async def collect(form, opening):
    results = [payload(opening)["content"]]
    if isinstance(form, MemoryHistory):
        button, backward = form.next_page, form.previous_page
        size = len(form.pages)
    else:
        button, backward = form.later_context, form.earlier_context
        size = len(form.pages())
    for index in range(1, size):
        interaction = current(form.owner, uuid4().int % 1000000000)
        if index == 1:
            await interaction.response.defer(ephemeral=True)  # Already acknowledged pagination.
        await button.callback(interaction)
        results.append(payload(interaction)["content"])
    assert button.disabled
    if size > 1:
        earlier = current(form.owner, uuid4().int % 1000000000)
        await backward.callback(earlier)
        assert payload(earlier)["content"] == results[-2]
        forward = current(form.owner, uuid4().int % 1000000000)
        await button.callback(forward)
        assert payload(forward)["content"] == results[-1]
    return "".join(value.partition("\n")[2] for value in results)


@pytest.mark.parametrize(
    ("cause", "beginning_size", "deferred"),
    [
        ("relevance_clear", 1200, False),
        ("major_discrepancy", 1800, True),
    ],
)
def test_native_maximum_active_controls_both_returns_history_privacy_and_retry(
    ledger, tmp_path, monkeypatch, cause, beginning_size, deferred
):
    _, game, awards, award = source(ledger, tmp_path, monkeypatch, 6)
    approved(ledger, game, tmp_path, monkeypatch, extra=(*advancement.RULES, rules.RULE))
    native_claim(awards, award)
    service = DeepBrainSpikesService(ledger)
    game.dice = Dice()
    receipt = service.buy(ADMIN, str(uuid4()), award, state(game).revision, "Actual held source")
    beginning, circumstances, returned = (
        difficult(name, size)
        for name, size in (("BEGINNING", beginning_size), ("CIRCUMSTANCES", 1200), ("RETURN", 1200))
    )

    async def begin():
        if beginning_size > 1200:
            return service.begin(
                ADMIN,
                str(uuid4()),
                receipt["id"],
                state(game).revision,
                900,
                current_ref(state(game), 2),
                "watching",
                "offscreen",
                beginning,
                circumstances,
            )["id"]
        opening = current(1, uuid4().int % 1000000000)
        await open_spikes(opening, service, receipt["id"])
        picker = payload(opening)["view"]
        with ledger.engine.connect() as c:
            scene = game.scene(c, 900)["id"]
        picker.values["scene"] = (scene,)
        selected = current(1, uuid4().int % 1000000000)
        await picker.confirm.callback(selected)
        setup = payload(selected)["view"]
        setup.values.update(
            subject=(current_ref(state(game), 2).token,), mode=("watching",), period=("offscreen",)
        )
        await enter(setup, "beginning", beginning)
        await enter(setup, "circumstances", circumstances)
        confirm = current(1, uuid4().int % 1000000000)
        await setup.confirm.callback(confirm)
        payload(confirm)
        assert setup.completed
        return rules.memories(state(game))[-1].id

    identity = asyncio.run(begin())
    before = state(game)
    rolls = game.dice.calls

    async def active():
        opening = current(1, uuid4().int % 1000000000)
        if deferred:
            await opening.response.defer(ephemeral=True)
        await open_spikes(opening, service, identity)
        form = payload(opening)["view"]
        assert isinstance(form, MemoryForm)
        rendered = await collect(form, opening)
        expected = (
            "Played memory in channel 900; saved present "
            + service.menu(ADMIN, identity)["present_scene"]
            + ".\nBeginning: "
            + clean(beginning)
            + "\nCurrent circumstances: "
            + clean(circumstances)
        )
        assert rendered == expected + (
            "\nUse normal Conversation in that scene. "
            "Only genuine legal current-actor Plays affect "
            "current resources. Return when relevance is clear or discrepancies become too major."
        )
        assert state(game) == before and game.dice.calls == rolls
        form.values.update(operation=("contribute",), account="My actual remembered contribution")
        saved = deepcopy(form.values)
        step = form.index
        previous = current(1, uuid4().int % 1000000000)
        await form.earlier_context.callback(previous)
        payload(previous)
        assert form.values == saved and form.index == step and not form.completed
        wrong = current(3, uuid4().int % 1000000000)
        index = form.context_index
        await form.later_context.callback(wrong)
        assert "belongs to another" in payload(wrong)["content"]
        assert form.context_index == index and form.values == saved
        confirmation = current(1, uuid4().int % 1000000000)
        await form.confirm.callback(confirmation)
        payload(confirmation)
        assert form.completed
        assert len(service.menu(ADMIN, identity)["contributions"]) == 1

    asyncio.run(active())

    async def return_memory():
        opening = current(1, uuid4().int % 1000000000)
        await opening.response.defer(ephemeral=True)
        await open_spikes(opening, service, identity)
        form = payload(opening)["view"]
        service.contribute(
            PLAYER,
            str(uuid4()),
            identity,
            state(game).revision,
            "Actual other participant contributes before this old form is confirmed",
        )
        after_contribution = state(game)
        form.values.update(operation=("return",), cause=(cause,), account=returned)
        stale = current(1, uuid4().int % 1000000000)
        await form.confirm.callback(stale)
        assert not form.completed and state(game) == after_contribution
        assert "original Handler" in payload(stale)["content"]
        refreshed = current(1, uuid4().int % 1000000000)
        await open_spikes(refreshed, service, identity)
        form = payload(refreshed)["view"]
        original_revision = service.menu(ADMIN, identity)["revision"]
        form.values.update(operation=("return",), cause=(cause,))
        await enter(form, "account", returned)
        confirmation = current(1, uuid4().int % 1000000000)
        await form.confirm.callback(confirmation)
        payload(confirmation)
        assert form.completed
        snapshot = state(game)
        replay = service.return_present(
            ADMIN, str(confirmation.id), identity, original_revision, cause, returned
        )
        assert replay["phase"] == "returned" and state(game) == snapshot

    asyncio.run(return_memory())
    final = state(game)

    async def history():
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(PLAYER)
            if x.task == "m3_deep_brain_spikes" and x.identity == identity
        )
        opening = current(2, uuid4().int % 1000000000)
        if deferred:
            await opening.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(opening, item)
        view = payload(opening)["view"]
        assert isinstance(view, MemoryHistory)
        actual = await collect(view, opening)
        data = service.menu(PLAYER, identity)
        expected = (
            "Played memory in channel 900; saved present "
            + data["present_scene"]
            + ".\nBeginning: "
            + clean(beginning)
            + "\nCurrent circumstances: "
            + clean(circumstances)
            + "\nReturned because "
            + cause
            + ": "
            + clean(returned)
        )
        assert actual == expected
        assert all(
            clean(marker) in actual
            for marker in ("BEGIN_BEGINNING", "MIDDLE_CIRCUMSTANCES", "END_RETURN")
        )
        wrong = current(3, uuid4().int % 1000000000)
        index = view.index
        await view.previous_page.callback(wrong)
        assert "belongs to another" in payload(wrong)["content"] and view.index == index
        outsider = current(99, uuid4().int % 1000000000)
        with pytest.raises(WorkflowError):
            await open_spikes(outsider, service, identity)
        assert not outsider.response.events and not outsider.edit_original_response.called
        original_menu = DeepBrainSpikesService.menu

        def denied(*args, **kwargs):
            raise WorkflowError("Actual current authorization no longer permits reading")

        monkeypatch.setattr(DeepBrainSpikesService, "menu", denied)
        revoked = current(2, uuid4().int % 1000000000)
        await view.previous_page.callback(revoked)
        assert "unavailable" in payload(revoked)["content"] and view.index == index
        assert "BEGIN" not in payload(revoked)["content"]
        monkeypatch.setattr(DeepBrainSpikesService, "menu", original_menu)
        await view.on_timeout()
        expired = current(2, uuid4().int % 1000000000)
        await view.previous_page.callback(expired)
        assert "expired" in payload(expired)["content"] and view.index == index
        reopened = current(2, uuid4().int % 1000000000)
        await open_spikes(reopened, service, identity)
        assert payload(reopened)["view"].index == 0
        assert state(game) == final and game.dice.calls == rolls

    asyncio.run(history())
    with ledger.engine.connect() as c:
        public = str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert all(
            marker not in public
            for marker in ("BEGIN_BEGINNING", "MIDDLE_CIRCUMSTANCES", "END_RETURN")
        )
