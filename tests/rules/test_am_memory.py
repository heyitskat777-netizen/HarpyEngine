"""Printed memory effects use the original source, choice ownership and private recovery."""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from test_am_code import rolled
from test_am_records import ANSWER, QUESTION
from test_am_records import rolled as records_rolled
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current
from test_regulations import canon as canon

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_am_code import open_source
from girlframe.engine import m3_am_code as code
from girlframe.engine import m3_am_memory as memory
from girlframe.engine import m3_am_records as records
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_am_code import CodeService
from girlframe.services.m3_am_memory import MemoryService
from girlframe.services.onboarding import WorkflowError

FIRST = "SYNTHETIC_MEMORY_CANARY: I met the courier beside the blue door."
SECOND = "I memorized the courier's actual passphrase: winter archive."


def test_mid_native_memory_only_selective_restart_replay_and_private_recovery(
    ledger, tmp_path, monkeypatch
):
    game, identity, root, action, worker, gateway, _ = rolled(
        ledger, tmp_path, monkeypatch, (4, 5), marked=True
    )
    before = state(game)
    actor = current_ref(before, 2)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "am_code_edit")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(
                options=("edit",),
                fields={"memory_scope": "all"},
                text="The AM cannot impersonate the actual circuit operator",
            ),
        )

    async def erase():
        operator = current(1, 906001)
        await operator.response.defer(ephemeral=True)
        await open_choice(operator, game, row["id"])
        form = operator.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(identities=(), memory_scope=("selected",))
        selected = current(1, 906002)
        await form.confirm.callback(selected)
        actual = selected.edit_original_response.call_args.kwargs["view"]
        assert isinstance(actual, NativeForm)
        actual.values.update(memories=FIRST + "\n" + SECOND, account="Actual memory-only operation")
        await actual.confirm.callback(current(1, 906003))
        assert actual.completed

    asyncio.run(erase())
    # Reconstruct the service and canonical state from SQLite, rather than an in-memory result.
    restarted = GameService(game.store, dice=game.dice)
    actual = state(restarted)
    value = code.session(actual, identity)
    loss = memory.losses(actual, actor)[0]
    assert value.memory_erasure == loss.id and loss.memories == (FIRST, SECOND)
    assert (
        loss.actor == actor and loss.operator == value.operator and loss.event == value.effect_event
    )
    assert not memory.can_recall(actual, actor, FIRST, learned_revision=before.revision)
    assert memory.can_recall(
        actual, actor, "The separate green door", learned_revision=before.revision
    )
    assert memory.can_recall(actual, actor, FIRST, learned_revision=actual.revision)
    assert memory.can_recall(actual, value.operator, FIRST, learned_revision=before.revision)
    assert actual.sheets["2"].model_dump_json() == before.sheets["2"].model_dump_json()
    assert actual.placements == before.placements and not value.replacements
    assert all(fact in actual.facts for fact in before.facts if fact.get("kind") != "am_code")
    assert game.inspect(PLAYER, root)["state"] == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    restarted.respond(
        ADMIN,
        "906003",
        row["id"],
        row["revision"],
        ChoiceAnswer(
            options=("edit",),
            fields={"memory_scope": "selected", "memories": FIRST + "\n" + SECOND},
            text="Actual memory-only operation",
        ),
    )
    assert state(restarted).revision == actual.revision
    with pytest.raises(WorkflowError):
        restarted.respond(
            ADMIN,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("edit",), fields={"memory_scope": "all"}, text="Replay"),
        )
    assert memory.losses(state(restarted), actor) == (loss,) and game.dice.calls == 2

    async def recover():
        owner = current(2, 906010)
        await owner.response.defer(ephemeral=True)
        await open_source(owner, CodeService(restarted), identity)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert ("memory:" + loss.id) in dict(form.fields[0].options)
        form.values["source"] = ("memory:" + loss.id,)
        chosen = current(2, 906011)
        chosen.followup.send = AsyncMock()
        await form.confirm.callback(chosen)
        kwargs = chosen.followup.send.call_args.kwargs
        assert kwargs["ephemeral"]
        assert FIRST in kwargs["file"].fp.getvalue().decode()

    asyncio.run(recover())
    assert MemoryService(restarted).get(ADMIN, loss.id)["memories"] == (FIRST, SECOND)
    with pytest.raises(WorkflowError):
        MemoryService(restarted).get(OTHER, loss.id)
    assert restarted.sheet(PLAYER)["am_runtime"]["memory_erasures"] == [
        dict(
            scope="selected",
            memories=[FIRST, SECOND],
            through_revision=loss.through_revision,
            event=loss.event,
        )
    ]
    assert "am_runtime" not in restarted.sheet(OTHER, 2)
    tick(worker, gateway, 5)
    projections = [restarted.sheet(OTHER, 2), CodeService(restarted).menu(OTHER, 900)]
    for viewer in (PLAYER, OTHER):
        try:
            projections.append(restarted.inspect(viewer, action))
        except WorkflowError:
            pass
    public = json.dumps(projections + list(gateway.messages.values()))
    assert FIRST not in public and SECOND not in public


def test_high_all_memories_and_identity_rewrite_are_one_option_alongside_records(
    ledger, tmp_path, monkeypatch
):
    game, identity, root, action, _, _, document = records_rolled(
        ledger, tmp_path, monkeypatch, (6, 6)
    )
    assert state(game).order[-1] == 2
    before = state(game)
    actor = current_ref(before, 2)
    selected = code.choices(before, actor)[0]
    answer(game, ADMIN, "am_code_options", options=("identities", "records"))
    answer(
        game,
        ADMIN,
        "am_code_edit",
        options=("edit",),
        fields={selected.id: "New Archive Self", "memory_scope": "all"},
        text="The original operator changes an Identity and erases all prior memories",
    )
    assert game.inspect(PLAYER, action)["state"] != "complete"
    answer(game, ADMIN, "am_code_records_question", text=QUESTION)
    answer(game, ADMIN, "am_code_records_answer", text=ANSWER, flag=True)
    actual = state(game)
    value = code.session(actual, identity)
    loss = memory.losses(actual, actor)[0]
    assert loss.scope == "all" and not loss.memories
    assert not memory.can_recall(actual, actor, "Any actual former experience", learned_revision=0)
    assert memory.can_recall(actual, actor, FIRST, learned_revision=actual.revision)
    new = next(x for x in actual.sheets["2"].identities if x.id == value.replacements[selected.id])
    assert (new.name, new.marked, new.slot) == ("New Archive Self", selected.marked, selected.slot)
    assert actual.sheets["2"].assets == before.sheets["2"].assets
    assert actual.sheets["2"].frame_runtime == before.sheets["2"].frame_runtime
    assert actual.placements == before.placements
    assert value.selected_options == ("identities", "records") and value.phase == "complete"
    assert records.access(actual, document).phase == "answered"
    assert MemoryService(game).get(PLAYER, loss.id)["scope"] == "all"
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 2


def test_low_has_real_order_only_and_cannot_author_a_memory_erasure(ledger, tmp_path, monkeypatch):
    game, identity, root, _, _, _, _ = rolled(ledger, tmp_path, monkeypatch, (1, 1))
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "am_code_order")
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(text="Forget", fields={"memory_scope": "all"}),
        )
    answer(game, ADMIN, "am_code_order", text="My actual circuits are accessible")
    answer(
        game,
        PLAYER,
        "am_code_obey",
        options=("obedient",),
        text="My actual circuits are accessible",
    )
    assert not memory.losses(state(game))
    assert code.session(state(game), identity).phase == "complete"
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 2


def test_memory_only_remains_available_when_every_identity_is_ineligible(canon):
    # A memory effect does not depend on there being any rewritable Identity.
    from girlframe.engine.m2 import IdentityState
    from girlframe.engine.m3_actor_state import ActorRef, SceneCast
    from girlframe.engine.m3_am import Limiter

    original = canon
    actor = current_ref(original, 2)
    operator = ActorRef(kind="npc", entity="synthetic-operator")
    original.sheets["2"].girl = "AM"
    original.sheets["2"].identities = [
        IdentityState(
            id="limited", name="Tool", marked=True, am_limiter="limiter", protected=True, slot=0
        )
    ]
    proof = Limiter(
        id="limiter",
        actor=actor,
        identity="limited",
        slot=0,
        freedom="refuse",
        discoverer=operator,
        controller=1,
        discovery="discovery",
        action="action",
        source_event="limiter-event",
        before_json=original.sheets["2"].identities[0].model_dump_json(),
    )
    original.facts.append(dict(kind="am_limiter", id=proof.id, body=proof.model_dump_json()))
    code.put(
        original,
        code.Maintenance(
            id="maintenance",
            actor=actor,
            operator=operator,
            owner=2,
            controller=1,
            discovery="discovery",
            cast=SceneCast(id="scene", channel=900, roles=()),
            registry="synthetic",
            proposed_event="proposed",
            proposal="Actual access",
            position="position",
            vessel="vessel",
            frame="frame",
            cell=(0, 0),
            phase="active",
            action="action",
        ),
    )
    assert not code.choices(original, actor)
    actual = code.rewrite(original, "maintenance", {}, "event", memory_scope="all")
    assert actual.sheets["2"] == original.sheets["2"]
    assert memory.losses(actual, actor)[0].scope == "all"
