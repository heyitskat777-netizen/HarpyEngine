"""Authored P1 normal: native Relay Dive interrupts one actual known-result Play."""

import json
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_physical_operations import place
from test_required_plays import native, submit
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_ankou import open_ankou, open_choice
from girlframe.discord_adapter.m3_dive import open_dive
from girlframe.engine import m3_ankou as ankou
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, TagState
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_native_interrupt_dive_real_tag_cost_owned_table_answers_and_known_parent(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, frame=ankou.FRAME)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ankou.RELAY, "play.basic.dive_deep"))
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        actual.sheets["2"].heat = 3
        actual.sheets["3"].heat = 1
        actual.sheets["3"].tags.append(
            TagState(id="relay-interrupt-cost", label="Unsteady", giver=2, observers=(1, 2, 3))
        )
        game.event(c, 1, str(uuid4()), "synthetic_original_relay_people_and_actual_tag", actual)
    controls = AnkouService(game)
    worker, gateway = GameWorker(game), Gateway()
    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        ("interrupt", "sense"),
        "I activate my original emotional relay",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "death",
        "Actual later NPC death hearing, not a fabricated consequence",
    )
    game.dice.faces = (3, 4)
    parent = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            heat=1,
            context="I face an actual danger while her emotional relay is active",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    receipt = game.roll(OTHER, str(uuid4()), parent)["receipt"]
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_interrupt")
    before = state(game)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(
                flag=True,
                options=("dive_deep",),
                fields={"tag": "relay-interrupt-cost"},
                text="Another actor cannot choose her interruption",
            ),
        )
    assert state(game).model_dump_json() == before.model_dump_json()
    native(
        lambda i: open_choice(i, game, game.decision(PLAYER, row["id"])),
        accept=("yes",),
        play=("dive_deep",),
        tag=("relay-interrupt-cost",),
        text="I erase the acting person's actual Tag to take a chance to interrupt",
    )
    task = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source_action == parent and x.kind == "interrupt"
    )
    assert task.options == ("dive_deep",)
    assert task.source_tag == "relay-interrupt-cost" and task.selected_event
    assert "relay-interrupt-cost" not in {x.id for x in state(game).sheets["3"].tags}
    assert game.dice.calls == 1
    assert game.inspect(OTHER, parent)["receipt"] == receipt

    before = state(game)
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            before.sheets["2"].revision,
            PlayInput(
                play="dive_deep",
                source_work=task.id,
                parent=parent,
                target_actor=task.target,
                heat=1,
                context="An interrupted person is not the target of my own Dive",
                trigger_confirmed=True,
            ),
        )
    assert state(game).model_dump_json() == before.model_dump_json()
    form = native(lambda i: open_ankou(i, controls, task.id), operation=("child",))
    submit(
        form,
        play=("dive_deep",),
        heat=("1",),
        identity=(),
        gain=("0",),
        pair_share=("0",),
        piloting=("no",),
        witnessed=("no",),
        trigger=("yes",),
        context="I commune with my own Vital Frame during the genuine interruption",
    )
    child = ankou.get(state(game), ankou.Task, task.id).child
    assert child
    with ledger.engine.connect() as c:
        action = game.action(c, child)
        assert action["parent_id"] == parent
        assert action["data"]["ankou_effect_child"]["id"] == task.id
        assert action["data"]["prepared"]["target_actor"] is None
        assert action["data"]["dive"]["actor"] == task.actor.model_dump(mode="json")
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, child)["state"] == "ready_to_roll":
        game.roll(PLAYER, str(uuid4()), child)
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_select")
    native(
        lambda i: open_dive(i, game, row["id"]),
        option=("erase_identity_and_table_question",),
        account="My actual interruption Dive",
    )
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_effect")
    identity = state(game).sheets["2"].identities[1]
    question = "PRIVATE_RELAY_INTERRUPT_DIVE_QUESTION"
    native(lambda i: open_dive(i, game, row["id"]), identity=(identity.id,), text=question)
    assert identity.id not in {x.id for x in state(game).sheets["2"].identities}
    for viewer in (PLAYER, OTHER, ADMIN):
        assert not ankou.get(state(game), ankou.Task, task.id).completed_event
        assert game.inspect(OTHER, parent)["state"] != "complete"
        assert not any(x["kind"] == "actor_keep" for x in game.choices(OTHER))
        row = next(x for x in game.choices(viewer) if x["kind"] == "dive_table_answer")
        native(
            lambda i, row=row: open_dive(i, game, row["id"], reviewed=True),
            user=viewer.user_id,
            text="My independently authored table answer " + str(viewer.user_id),
        )
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert ankou.get(state(game), ankou.Task, task.id).completed_event
    assert game.inspect(OTHER, parent)["receipt"] == receipt
    assert game.dice.calls == 2
    answer(game, OTHER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The original Keep performance succeeds")
    assert game.inspect(OTHER, parent)["state"] == "complete"
    assert game.roll(OTHER, str(uuid4()), parent)["receipt"] == receipt
    assert game.dice.calls == 2
    assert state(game).sheets["2"].heat == before.sheets["2"].heat - 1
    assert state(game).sheets["3"].heat == before.sheets["3"].heat
    assert "relay-interrupt-cost" not in {x.id for x in state(game).sheets["3"].tags}
    tick(worker, gateway, 6)
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == json.loads(
        json.dumps(gateway.original)
    )
    assert question not in json.dumps(gateway.messages)
