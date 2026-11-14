"""Inbox selection and native Keep choices within the bounded campaign bridge."""

import asyncio
from uuid import uuid4

import test_p1_native_campaign_bridge as journey
from test_inbox import request
from test_ledger import ledger as ledger_fixture

from girlframe.discord_adapter import onboarding
from girlframe.discord_adapter.inbox import InboxView, RequestSelect
from girlframe.discord_adapter.m2_forms import FormSelect, NarrativeModal, NativeForm
from girlframe.services.inbox import InboxService

ledger = ledger_fixture


def test_campaign_play_choices_reopen_through_inbox_and_native_selectors(ledger, monkeypatch):
    # Isolate transport throttling from this sequential mocked interaction journey.
    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    visited = []

    def answer_from_inbox(game, viewer, kind, **values):
        decision = next(x for x in game.choices(viewer) if x["kind"] == kind)

        def click(custom_id=None):
            interaction = request(viewer, int(uuid4()), custom_id)
            interaction.channel_id = 900
            return interaction

        async def run():
            inbox = InboxView(InboxService(ledger), viewer.user_id)
            inbox.category = "plays"
            await inbox.present(click())
            item = next(x for x in inbox.page.window if x.identity == decision["id"])
            assert item.task == "m2_choice"
            selector = next(x for x in inbox.children if isinstance(x, RequestSelect))
            selector._values = [item.key]
            await selector.callback(click())
            assert inbox.page.item.identity == decision["id"] and not inbox.overview
            opened = click(inbox.primary.custom_id)
            await inbox.primary.callback(opened)
            form = opened.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm)
            for index, field in enumerate(form.fields):
                assert form.index == index
                value = values[field.key]
                if field.options:
                    menu = next(x for x in form.children if isinstance(x, FormSelect))
                    selected = ("yes" if value else "no",) if field.key == "flag" else value
                    assert set(selected) <= {option.value for option in menu.options}
                    menu._values = list(selected)
                    await menu.callback(click())
                else:
                    modal = NarrativeModal(form, field)
                    modal.input._value = value
                    await modal.on_submit(click())
                if index + 1 < len(form.fields):
                    await form.next.callback(click())
            # Selecting and reviewing alone must not save the decision.
            assert any(x["id"] == decision["id"] for x in game.choices(viewer))
            await form.confirm.callback(click())
            assert form.completed
            assert not any(x["id"] == decision["id"] for x in game.choices(viewer))
            reopened = InboxService(ledger)
            assert not any(x.identity == decision["id"] for x in reopened.items(viewer))
            visited.append(kind)

        asyncio.run(run())

    monkeypatch.setattr(journey, "answer", answer_from_inbox)
    journey.test_native_mission_inbox_recovery_bridges_preserve_campaign_loop(ledger, monkeypatch)
    assert visited == ["actor_keep", "handler_keep"]
