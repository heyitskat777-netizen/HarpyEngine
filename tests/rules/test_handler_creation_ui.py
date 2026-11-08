"""Actual native save/reopen/agreements/activation and complete private long text."""

import asyncio

import pytest
from test_handler_creation import complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_handler_creation import (
    AgreementPages,
    HandlerHistory,
    HandlerMenu,
    open_activation,
    open_agreement,
    open_details,
    open_handler,
    open_starting,
)
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.onboarding import WorkflowError


def test_native_handler_details_starting_requests_and_exact_owned_activation(ledger):
    svc, game = ready(ledger)

    async def run():
        owner = current(1, 25101)
        await owner.response.defer(ephemeral=True)
        await open_handler(owner, svc)
        menu = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(menu, HandlerMenu)
        assert not await menu.interaction_check(current(2))
        await open_details(owner, svc)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert len(dict(form.fields[0].options)) == 7
        form.values.update(
            playbook=("Trainer",),
            name="ACTUAL HANDLER",
            appearance="Private details",
            outfit="Private clothes",
            background="Private job history",
            gear_0=("weapon",),
            description_0="Custom weapon",
            gear_1=("studio",),
            description_1="Described studio",
        )
        await form.confirm.callback(current(1, 25102))
        assert form.completed and state(game).handler_persona is None
        await open_starting(owner, HandlerCreationService(ledger))
        choices = owner.edit_original_response.call_args.kwargs["view"]
        roster = svc.view(ADMIN)["pilots"]
        choices.values.update(
            {
                "0_pilot": (roster[0]["token"],),
                "0_prompt": ("0",),
                "0_history": "Actual shared relationship one",
                "1_pilot": (roster[1]["token"],),
                "1_prompt": ("1",),
                "1_history": "Actual shared relationship two",
            }
        )
        await choices.confirm.callback(current(1, 25103))
        assert choices.completed
        await open_handler(owner, svc)
        menu = owner.edit_original_response.call_args.kwargs["view"]
        await menu.propose.callback(current(1, 25104))
        for viewer in (PLAYER, OTHER):
            task = next(x for x in svc.tasks(viewer) if x["kind"] == "handler_creation_agreement")
            person = current(viewer.user_id, 25105 + viewer.user_id)
            await person.response.defer(ephemeral=True)
            await open_agreement(person, svc, task["id"])
            consent = person.edit_original_response.call_args.kwargs["view"]
            assert consent.owner == viewer.user_id and not await consent.interaction_check(owner)
            consent.values["decision"] = ("accept",)
            await consent.confirm.callback(current(viewer.user_id, 25108 + viewer.user_id))
            assert consent.completed
        await open_activation(owner, svc)
        activation = owner.edit_original_response.call_args.kwargs["view"]
        assert state(game).handler_persona is None
        activation.values["confirm"] = ("yes",)
        await activation.confirm.callback(current(1, 25120))
        assert activation.completed

    asyncio.run(run())
    assert state(game).handler_persona.draft.playbook == "Trainer"
    assert not svc.tasks(PLAYER) and not svc.tasks(OTHER)


def test_shared_long_escaped_history_is_complete_paginated_owned_and_rechecks_membership(ledger):
    svc, _ = ready(ledger)
    draft = complete(svc)
    history = "*" * 1190
    draft = draft.model_copy(
        update={
            "starting": (
                draft.starting[0].model_copy(update={"history": history}),
                draft.starting[1],
            )
        }
    )
    save(svc, draft)
    identities = svc.propose(ADMIN, "long-shared-history", svc.view(ADMIN)["revision"])["ids"]

    async def run():
        person = current(2, 25201)
        await person.response.defer(ephemeral=True)
        await open_agreement(person, svc, identities[0])
        pages = person.edit_original_response.call_args.kwargs["view"]
        assert isinstance(pages, AgreementPages)
        assert not await pages.interaction_check(current(3))
        full = []
        while True:
            content = person.edit_original_response.call_args.kwargs["content"]
            assert len(content) <= 2000
            full.append(content.split("\nPage ")[0])
            if pages.next.disabled:
                break
            pages.index += 1
            await pages.show(person)
        assert clean(history) in "".join(full)
        assert not pages.respond.disabled
        with ledger.transaction() as c:
            from girlframe.database import tables as t

            c.execute(
                t.members.update()
                .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
                .values(active=False)
            )
        with pytest.raises(WorkflowError):
            await pages.show(person)

    asyncio.run(run())


def test_saved_private_sheet_pages_preserve_all_escaped_details_and_former_role_cannot_edit(ledger):
    svc, _ = ready(ledger)
    draft = complete(svc).model_copy(update={"appearance": "*" * 1190})
    save(svc, draft)

    async def run():
        owner = current(1)
        await owner.response.defer(ephemeral=True)
        pages = HandlerHistory(svc, 1)
        full = []
        while True:
            await pages.show(owner)
            content = owner.edit_original_response.call_args.kwargs["content"]
            assert len(content) <= 2000
            full.append(content.split("\nPage ")[0].removeprefix("**Your saved Handler sheet**\n"))
            if pages.next.disabled:
                break
            pages.index += 1
        assert clean(draft.appearance) in "".join(full)
        assert not await pages.interaction_check(current(2))

    asyncio.run(run())
