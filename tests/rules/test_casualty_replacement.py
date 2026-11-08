"""Deferred P1 normal: actual supplied Link, exact payment, original-body control."""

import asyncio
from uuid import uuid4

import pytest
from test_casualty import ready, tags
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_casualty_replacement import open_replacement
from girlframe.engine import m3_casualty as casualty
from girlframe.engine import m3_casualty_replacement as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_casualty import prove_parts
from girlframe.services.m3_casualty_replacement import ReplacementService, prove_replacement
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def native(service, viewer, identity=None, *, operation, **values):
    async def run():
        opened = current(viewer.user_id, int(uuid4().int % 1000000000))
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_replacement(opened, service, identity)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        assert not await menu.interaction_check(current(3 if viewer == PLAYER else 2, 82999))
        menu.values["operation"] = (operation,)
        selected = current(viewer.user_id, int(uuid4().int % 1000000000))
        selected.channel_id = 900
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submitted = current(viewer.user_id, int(uuid4().int % 1000000000))
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        return str(submitted.id)

    return asyncio.run(run())


def test_actual_removed_link_supplied_native_install_payment_history_and_real_repilot(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, piloting=True)
    actor = current_ref(state(game), 2)
    original = state(game)
    controls.damage_part(
        ADMIN,
        str(uuid4()),
        original.revision,
        actor,
        "link",
        "removed",
        "The actual Handler removes this real Link as a performed fictional consequence",
    )
    missing = state(game)
    assert casualty.part_state(missing, actor, "link") == "removed"
    assert not casualty.can_pilot(missing, actor)
    assert next(x for x in missing.placements if x.actor == actor).mode != "piloting"
    body = casualty.body(missing, actor)
    assert body is not None
    removal = [x for x in casualty.records(missing, casualty.PartChange) if x.part == "link"][-1]
    physical = PhysicalService(ledger)
    with ledger.engine.connect() as c:
        position = resolve(missing, actor, profiles(c, ledger.campaign_id)).position_sha256
    with pytest.raises(WorkflowError):
        physical.operate(
            PLAYER,
            str(uuid4()),
            missing.revision,
            CockpitAction(
                actor=actor,
                operation="pilot",
                expected_position=position,
                account="Attempting actual control without a Link",
                confirmed=True,
            ),
        )
    with pytest.raises(WorkflowError):
        controls.repair_part(PLAYER, str(uuid4()), missing.revision, "link")
    replacement = ReplacementService(game)
    native(
        replacement,
        PLAYER,
        operation="request:link",
        account="I request an actually supplied replacement for this removed Link",
    )
    request = rules.records(state(game), rules.Request)[-1]
    assert request.actor == actor and request.vessel == body.vessel and request.cause == removal.id
    with pytest.raises(WorkflowError):
        replacement.view(OTHER, request.id)
    with pytest.raises(WorkflowError):
        replacement.quote(
            OTHER,
            str(uuid4()),
            state(game).revision,
            request.id,
            "Cannot invent supply",
            "No physical component",
            "No source Handler",
            1,
        )
    native(
        replacement,
        ADMIN,
        request.id,
        operation="quote",
        name="Identified ideal Link module K-19",
        description="The actual compatible newly supplied module is prepared beside this body",
        procurement="The actual Handler's supplied K-19 package costs two Permissions",
        price="2",
    )
    quote = rules.records(state(game), rules.Quote)[-1]
    assert quote.price == 2 and quote.part == "link" and quote.component
    before = state(game)
    with pytest.raises(WorkflowError, match="STALE"):
        replacement.install(
            PLAYER, str(uuid4()), before.revision - 1, quote.id, "Stale installation"
        )
    with pytest.raises(WorkflowError):
        replacement.install(
            OTHER, str(uuid4()), before.revision, quote.id, "Another body's decision"
        )
    assert state(game) == before and casualty.part_state(before, actor, "link") == "removed"
    install_key = native(
        replacement,
        PLAYER,
        request.id,
        operation="install",
        account="I actually receive K-19 at this body's recorded position and install this module",
    )
    after = state(game)
    installed = rules.records(after, rules.Installation)[-1]
    replay = replacement.install(
        PLAYER,
        install_key,
        before.revision,
        quote.id,
        "I actually receive K-19 at this body's recorded position and install this module",
    )
    assert replay["id"] == installed.id and state(game) == after
    assert after.sheets["2"].permissions == before.sheets["2"].permissions - 2
    assert after.sheets["2"].identities == before.sheets["2"].identities
    assert after.sheets["2"].assets == before.sheets["2"].assets
    assert after.sheets["3"] == before.sheets["3"]
    assert removal in casualty.records(after, casualty.PartChange)
    repaired = casualty.body(after, actor)
    assert repaired is not None and repaired.vessel == body.vessel
    assert next(x for x in repaired.parts if x.id == "link").component == quote.component
    assert next(x for x in repaired.parts if x.id == "link").condition == "intact"
    assert next(x for x in after.placements if x.actor == actor).mode != "piloting"
    assert casualty.can_pilot(after, actor)
    with ledger.engine.connect() as c:
        assert prove_replacement(game, c, after, installed.id) == installed
        assert prove_parts(game, c, after, actor) == repaired
    assert replacement.view(PLAYER, request.id)["installation"]["component"] == quote.component
    assert replacement.view(ADMIN, request.id)["phase"] == "complete"
    with pytest.raises(WorkflowError):
        replacement.install(PLAYER, str(uuid4()), after.revision, quote.id, "Cannot install twice")
    assert state(game) == after
    with ledger.engine.connect() as c:
        position = resolve(after, actor, profiles(c, ledger.campaign_id)).position_sha256
    physical.operate(
        PLAYER,
        str(uuid4()),
        after.revision,
        CockpitAction(
            actor=actor,
            operation="pilot",
            expected_position=position,
            account="I actually retake control using my installed K-19 Link",
            confirmed=True,
        ),
    )
    assert next(x for x in state(game).placements if x.actor == actor).mode == "piloting"
    game.dice.faces = (3, 4)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="Maintaining real control after replacement",
            trigger_confirmed=True,
            piloting=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] == "ready_to_roll":
        game.roll(PLAYER, str(uuid4()), action)
    tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The real original-body recovery holds")
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
