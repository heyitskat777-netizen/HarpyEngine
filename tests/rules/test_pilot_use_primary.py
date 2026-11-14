"""Actual native Girl non-Play use, then the original Newgirl's owned Bond."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_easy_target import _npc_protection_native, ready, source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_easy_target import open_easy_target
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actors import resolve
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_easy_target import EasyTargetService, prove_npc_use
from girlframe.services.m3_easy_target_pilot_use import primary as validate_pilot_body
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def test_native_pilot_use_finishes_before_owned_bond(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    initial = state(game)
    pilot = current_ref(initial, OTHER.user_id)
    newgirl = current_ref(initial, PLAYER.user_id)
    action = source(game, worker, gateway)
    work = rules.identity(action, pilot)
    receipt = game.inspect(PLAYER, action)["receipt"]

    def row(viewer, kind):
        return next(x for x in game.choices(viewer) if x["kind"] == kind + ":" + pilot.token)

    def submit(viewer, kind, values, interaction_id):
        choice = row(viewer, kind)
        asyncio.run(
            _npc_protection_native(
                GameService(ledger, dice=game.dice), viewer.user_id, choice, values, interaction_id
            )
        )

    submit(
        OTHER,
        "easy_target_react",
        dict(
            urge=("use",),
            context="My actual Girl uses her as an audience for an ordinary rehearsal",
            account="PRIVATE_PILOT_USE I choose ordinary use with no triggered Play",
        ),
        99840,
    )
    reaction = rules.get(state(game), rules.Reaction, work)
    assert reaction.actor == reaction.performer == pilot
    assert reaction.play is None and reaction.child is None
    validation = row(ADMIN, "easy_target_validate")
    detail = game.decision(ADMIN, validation["id"])["detail"]
    assert detail["pilot_use"] and not detail["npc_use"] and not detail["handler_use"]
    submit(
        ADMIN,
        "easy_target_validate",
        dict(
            yes=("yes",),
            account="This real exterior-body rehearsal triggers no Play or separate effect",
        ),
        99850,
    )
    choice = row(OTHER, "easy_target_child")
    before = state(game)
    original_depth = depth(before, newgirl, pilot)
    assert not rules.records(before, rules.NpcUse)
    assert not any(x["kind"].startswith("easy_target_bond") for x in game.choices(PLAYER))
    assert any(x.identity == choice["id"] for x in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(text="The Handler cannot perform for the actual Girl"),
        )
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(text="Invent a benefit", fields={"bonus": "1"}),
        )
    with ledger.engine.connect() as c:
        body = resolve(
            before,
            pilot,
            snapshot_profiles(c, ledger.campaign_id, before),
            require_current_profile=False,
        )
    original = rules.get(before, rules.Session, action)
    with pytest.raises(WorkflowError):
        validate_pilot_body(
            before,
            rules.get(before, rules.Reaction, work),
            original,
            original.cast,
            body.model_copy(update=dict(inside_frame=True, subsumed=True, vitals_active=False)),
        )
    assert state(game) == before
    submit(
        OTHER,
        "easy_target_child",
        dict(account="PRIVATE_PILOT_USE I actually finish my ordinary rehearsal for her"),
        99860,
    )
    performed = state(game)
    use = rules.records(performed, rules.NpcUse)[-1]
    # Legacy record names preserve the original Pilot instead of creating an NPC.
    assert use.actor == pilot and use.controller == OTHER.user_id
    assert use.target == newgirl and use.handler == current_ref(initial, ADMIN.user_id)
    assert use.actor_position == body.position_sha256 and use.actor_vessel == body.vessel_id
    assert rules.get(performed, rules.Reaction, work).performance_event == use.event
    assert performed.sheets == before.sheets and performed.world == initial.world
    assert depth(performed, newgirl, pilot) == original_depth
    assert not rules.get(performed, rules.Reaction, work).completed_event
    assert game.inspect(PLAYER, action)["state"] != "complete"
    bond = row(PLAYER, "easy_target_bond")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            bond["id"],
            bond["revision"],
            ChoiceAnswer(flag=True, text="The performer cannot choose her Bond"),
        )
    assert state(game) == performed
    with ledger.engine.connect() as c:
        assert prove_npc_use(game, c, performed, use.id) == use
        forged = performed.model_copy(deep=True)
        rules.put(forged, use.model_copy(update=dict(account="Invented performance")))
        with pytest.raises(WorkflowError, match="canonical original"):
            prove_npc_use(game, c, forged, use.id)
    submit(
        PLAYER,
        "easy_target_bond",
        dict(yes=("yes",), account="PRIVATE_PILOT_USE My own choice to deepen our actual Bond"),
        99870,
    )
    actual = state(game)
    reaction = rules.get(actual, rules.Reaction, work)
    assert reaction.completed_event and reaction.consequence == "bond"
    assert not reaction.child and not reaction.harm and not reaction.protection_event
    assert depth(actual, newgirl, pilot) == original_depth + 1
    assert len(rules.records(actual, rules.NpcUse)) == 1
    assert not rules.records(actual, rules.HandlerUse) and not rules.records(actual, rules.Harm)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert actual.world == initial.world and actual.handler_tags == initial.handler_tags
    assert actual.handler_heat == initial.handler_heat
    assert actual.sheets["2"].heat == initial.sheets["2"].heat - 1
    assert actual.sheets["3"].heat == initial.sheets["3"].heat
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt and game.dice.calls == 1
    with ledger.engine.connect() as c:
        for name in ("m2_actions", "m2_receipts"):
            assert (
                c.scalar(
                    sa.select(sa.func.count())
                    .select_from(t.m2[name])
                    .where(t.m2[name].c.campaign_id == ledger.campaign_id)
                )
                == 1
            )
        assert "PRIVATE_PILOT_USE" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    with pytest.raises(WorkflowError):
        controls.view(GuildViewer(4, 200, True, False), work)
    tick(worker, gateway, 6)
    assert "PRIVATE_PILOT_USE" not in json.dumps(gateway.messages)
    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER):
        game.join_scene(viewer, str(uuid4()), 900)
    later = state(game)

    def no_live_profiles(*args, **kwargs):
        raise AssertionError("Historical use must retain its original profile bindings")

    monkeypatch.setattr("girlframe.services.m3_easy_target.profiles", no_live_profiles)
    with ledger.engine.connect() as c:
        assert prove_npc_use(game, c, later, use.id) == use
    shown = EasyTargetService(GameService(ledger)).view(OTHER, work)
    assert shown["npc_use"][0]["actor"] == pilot.model_dump(mode="json")

    async def reopen():
        opened = current(OTHER.user_id, 99880)
        opened.channel_id = 999
        await opened.response.defer(ephemeral=True)
        await open_easy_target(opened, EasyTargetService(GameService(ledger)), work)
        history = opened.edit_original_response.call_args.kwargs["view"]
        assert use.account in "".join(x.body for x in history.pages)

    asyncio.run(reopen())
