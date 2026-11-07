"""Voluntary Princess tiers retain real owners, source Tags and one actual child."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from handler_award_scenario import ordinary_pr_award
from test_enforcer_requisitions import approved
from test_gender_designation import acquire, assign
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_princess_sex import open_choice, open_princess
from girlframe.engine import m3_gender_designation as gender
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_princess_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.inbox import InboxService
from girlframe.services.m3_gender_designation import GenderDesignationService
from girlframe.services.m3_princess_sex import SexService
from girlframe.services.onboarding import WorkflowError


def setup(store, tmp_path, monkeypatch):
    import test_mission_service

    original = test_mission_service.setup_game
    monkeypatch.setattr(
        test_mission_service,
        "setup_game",
        lambda *a, **kw: original(*a, **(kw | {"girl": "PRINCESS"})),
    )
    game, worker, gateway = ordinary_pr_award(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(ordinary.RULE, rules.RULE, gender.RULE))
    return game, worker, gateway, SexService(game)


def source(service, *, native=False):
    game = service.game
    identity = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(state(game), 3),
        state(game).revision,
        "PRIVATE_ACTUAL voluntary original interaction",
    )["id"]
    if native:

        async def run():
            first = current(3, 83001)
            first.channel_id = 900
            await first.response.defer(ephemeral=True)
            await open_princess(first, service, identity)
            form = first.edit_original_response.call_args.kwargs["view"]
            assert "every actor-owned decision" in form.instructions
            form.values.update(accept=("yes",), account="My actual voluntary source confirmation")
            await form.confirm.callback(current(3, 83002))
            assert form.completed

        asyncio.run(run())
    else:
        service.confirm(
            OTHER,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            "Actual counterpart owns this disclosed voluntary confirmation",
        )
    return identity


def roll(game, worker, gateway, service, faces, *, native=False):
    tick(worker, gateway, 5)
    identity = source(service, native=native)
    game.dice = Dice(faces)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=identity,
            target_actor=current_ref(state(game), 3),
            heat=0,
            context="Actual confirmed voluntary interaction",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    return identity, action


def test_actual_native_princess_tiers_gender_and_true_counterpart_child(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = setup(ledger, tmp_path, monkeypatch)
    own, other = current_ref(state(game), 2), current_ref(state(game), 3)
    before = depth(state(game), own, other)
    identity, low = roll(game, worker, gateway, service, (2, 3), native=True)
    pass_tags(game)
    with pytest.raises(WorkflowError):
        row = next(x for x in game.choices(OTHER) if x["kind"] == "princess_sex_low_tag")
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(text="Cannot author another human's Tag"),
        )
    answer(game, OTHER, "princess_sex_low_tag", text="PRIVATE_LOW imperfection")
    assert depth(state(game), own, other) == max(0, before - 1)
    assert rules.get(state(game), identity).phase == "complete"
    assert game.inspect(PLAYER, low)["state"] == "complete"

    for response, giving in (("agree", False), ("refuse", False), ("refuse", True)):
        identity, action = roll(game, worker, gateway, service, (4, 4))
        pass_tags(game)
        answer(game, PLAYER, "princess_sex_favour", text="PRIVATE_FAVOUR pass the actual note")
        answer(
            game,
            OTHER,
            "princess_sex_favour_reply",
            options=(response,),
            text="My own performed speech: " + response,
        )
        if response == "refuse":
            answer(
                game,
                PLAYER,
                "princess_sex_optional_tag",
                options=("give" if giving else "decline",),
                text="PRIVATE_REFUSED stubborn" if giving else "",
            )
        value = rules.get(state(game), identity)
        assert value.response == response and bool(value.tag) == giving
        assert game.inspect(PLAYER, action)["state"] == "complete"

    designation = GenderDesignationService(ledger)
    acquired = acquire(game)
    assign(designation, acquired, (own,), "man")
    assign(designation, acquired, (other,), "animal")
    partner_tag = next(
        x.id for x in state(game).sheets["3"].tags if x.label == "PRIVATE_REFUSED stubborn"
    )
    identity, parent = roll(game, worker, gateway, service, (4, 4))
    original_receipt = game.inspect(PLAYER, parent)["receipt"]
    answer(game, ADMIN, "tag_window", options=("pass",))
    answer(game, OTHER, "tag_window", options=("pass",))
    answer(game, PLAYER, "tag_window", options=("gender_man",), denied=(partner_tag,))
    with ledger.engine.connect() as c:
        assert game.action(c, parent)["data"]["result"]["total"] == 11
    assert not any(x["kind"] == "princess_sex_direct" for x in game.choices(PLAYER))
    answer(game, OTHER, "gender_animal_tag", text="PRIVATE_ANIMAL actual partner Tag")
    assert (
        next(
            x for x in state(game).sheets["2"].tags if x.label.startswith("PRIVATE_ANIMAL")
        ).giver_actor
        == other
    )
    answer(
        game,
        PLAYER,
        "princess_sex_direct",
        options=("keep_your_head",),
        text="Actual immediate danger: maintain composure under pressure",
    )
    value = rules.get(state(game), identity)
    direction = rules.direction(state(game), value.direction)
    details = service.view(PLAYER, identity)
    assert details["child"]["sheet_revision"] == state(game).sheets["3"].revision
    assert "review" not in details["child"] and "notes" not in details["child"]
    args = (
        PLAYER,
        "83005",
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            source_work=direction.id,
            parent=parent,
            heat=0,
            context=direction.context,
            trigger_confirmed=True,
        ),
    )
    with pytest.raises(WorkflowError):
        game.begin(OTHER, str(uuid4()), *args[2:])

    async def native_child():
        current_choice = next(x for x in game.choices(PLAYER) if x["kind"] == "princess_sex_child")
        first = current(2, 83004)
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await open_choice(first, game, current_choice["id"])
        form = first.edit_original_response.call_args.kwargs["view"]
        form.values.update(heat=("0",), gain=("0",), identity=())
        response = current(2, 83005)
        response.channel_id = 900
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args

    asyncio.run(native_child())
    child = rules.direction(state(game), direction.id).child
    assert game.begin(*args)["action_id"] == child
    observed = []
    actual_actor = gateway.actor

    async def actor(identity):
        observed.append(identity)
        return await actual_actor(identity)

    gateway.actor = actor
    game.dice = Dice((4, 4))
    tick(worker, gateway, 3)
    assert 2 in observed and game.dice.calls == 1
    with ledger.engine.connect() as c:
        actual = game.action(c, child)
        assert actual["actor_id"] == "3" and actual["parent_id"] == parent
        assert actual["data"]["character_ids"]["3"] == other.incarnation
    for owner in (ADMIN, PLAYER):
        own_row = next(
            x
            for x in game.choices(owner)
            if x["kind"] == "tag_window" and x["actor_id"] == str(owner.user_id)
        )
        game.respond(
            owner, str(uuid4()), own_row["id"], own_row["revision"], ChoiceAnswer(options=("pass",))
        )
    row = next(
        x for x in game.choices(PLAYER) if x["kind"] == "tag_window" and x["actor_id"] == "3"
    )
    game.respond(PLAYER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("pass",)))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
    assert not any(x["id"] == row["id"] for x in game.choices(OTHER))
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(PLAYER))
    assert not any(x.identity == row["id"] for x in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("tough", "sexy"), denied=("in_control",)),
        )
    reply = (
        PLAYER,
        str(uuid4()),
        row["id"],
        row["revision"],
        ChoiceAnswer(options=("tough", "sexy"), denied=("in_control",)),
    )
    result = game.respond(*reply)
    assert game.respond(*reply) == result
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual Handler finds this sufficient")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert rules.direction(state(game), direction.id).completed_event
    assert game.inspect(PLAYER, parent)["receipt"] == original_receipt
    assert game.dice.calls == 1
    with pytest.raises(WorkflowError):
        game.begin(PLAYER, str(uuid4()), *args[2:])
    tick(worker, gateway, 8)
    assert not any(
        x in json.dumps(gateway.messages)
        for x in ("PRIVATE_FAVOUR", "PRIVATE_LOW", "PRIVATE_ANIMAL")
    )
    assert any(x.identity == identity for x in InboxService(ledger).items(PLAYER))
    with ledger.engine.connect() as c:
        row = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.id == rules.direction(state(game), direction.id).completed_event,
                    t.events.c.campaign_id == ledger.campaign_id,
                )
            )
            .mappings()
            .one()
        )
        assert row["actor_id"] == "1"  # The Handler's own sufficiency decision stays theirs.
