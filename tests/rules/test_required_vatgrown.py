"""One native Vatgrown nomination episode; worker-authored, root-run only."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_physical_operations import place
from test_required_plays import native, submit
from test_vatgrown_plays import native_choice
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_ankou import _child
from girlframe.discord_adapter.m3_required_plays import open_required
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_required_plays as rules
from girlframe.engine import m3_vatgrown_plays as vatgrown
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_required_plays import RequiredPlayService, prove
from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import projection


def test_native_vatgrown_nomination_consent_cancel_relink_real_questions_and_restore(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="VATGROWN", frame=ankou.FRAME)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(ankou.RELAY, vatgrown.SEX, vatgrown.EXPERIMENT, vatgrown.INVESTMENT),
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "strain", "playbooks"}}
            )
        }
    )
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        event = str(uuid4())
        actual = set_depth(actual, current_ref(actual, 2), current_ref(actual, 3), 2, event)
        game.event(c, 1, event, "synthetic.initial_vatgrown_ankou_intense_relationship", actual)
    world = WorldService(MissionService(ledger))
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="original-investor",
            name="Actual starting scientist",
            jobs=("scientist",),
            detail="Actual original scientist",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    slot = state(game).sheets["2"].review.creation.npc_bonds[0].slot
    world.import_starting_npc(PLAYER, str(uuid4()), state(game).revision, slot, "original-investor")
    worker, gateway = GameWorker(game), Gateway()
    controls, sex, required = (
        AnkouService(game),
        VatgrownPlaysService(game),
        RequiredPlayService(game),
    )
    relay = controls.activate_relay(
        PLAYER, str(uuid4()), 900, state(game).revision, ("speech", "touch"), "Actual relay"
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "Actual Intense partners nominate",
    )
    nomination = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "nominate"
    )
    assert vatgrown.PLAY in controls.view(OTHER, nomination.id)["nomination_options"]
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        vatgrown.PLAY,
        "Nominate her own source without consenting for anyone",
    )
    task = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "perform"
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "held"

    async def open_nomination(interaction):
        await _child(
            interaction, game, {"body": {"allowed": (vatgrown.PLAY,), "source_work": task.id}}
        )
        rendered = interaction.edit_original_response.call_args.kwargs["view"].text()
        assert "actual counterpart confirms their own source" in rendered
        assert "self-Dose" not in rendered
        assert "cocktail" not in rendered

    source_menu = native(open_nomination, operation=("invite_vatgrown",))
    invitation = submit(source_menu, source=("invite",))
    submit(
        invitation,
        target=(current_ref(state(game), 3).token,),
        account="PRIVATE_OWN_VATGROWN actual voluntary source",
    )
    recipe = vatgrown.records(state(game), vatgrown.Session)[-1]
    assert not required.menu(PLAYER, task.id)["accepted"]
    with pytest.raises(WorkflowError):
        required.link(PLAYER, str(uuid4()), task.id, recipe.id, state(game).revision)
    sex.respond(
        OTHER,
        str(uuid4()),
        recipe.id,
        state(game).revision,
        True,
        "My independent voluntary answer",
    )
    native(lambda i: open_required(i, game, task.id), operation=("link:" + recipe.id,))
    selected = rules.records(state(game))[-1]
    assert selected.rule == vatgrown.SEX
    with pytest.raises(WorkflowError):
        required.menu(OTHER, task.id)

    def start():
        form = native(lambda i: open_required(i, game, task.id), operation=("play",))
        submit(
            form,
            heat=("0",),
            gain=("1",),
            share=("0",),
            context="PRIVATE_OWN_VATGROWN actually confirmed nominated performance",
        )
        with ledger.engine.connect() as c:
            action = game.action(c, game.lock(c, 900)["action_id"])
        assert action["data"]["vatgrown_sex"]["session"] == recipe.id
        assert action["data"]["ankou_effect_child"]["id"] == task.id
        assert action["data"]["prepared"]["target_actor"] is None
        return action["id"]

    abandoned = start()
    before, calls = state(game), game.dice.calls
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    assert saved["cancellable"] and not saved["rolled"]
    args = PLAYER, str(uuid4()), abandoned, saved["revision"]
    result = recovery.recover(*args, cancel=True)
    assert recovery.recover(*args, cancel=True) == result
    restored = vatgrown.get(state(game), recipe.id)
    assert restored.phase == "accepted" and restored.action is None and restored.bound_event is None
    assert restored.consent_event == vatgrown.get(before, recipe.id).consent_event
    assert game.dice.calls == calls and state(game).sheets["2"].heat == before.sheets["2"].heat
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), selected.id).retired_event
    linked = required.link(PLAYER, str(uuid4()), task.id, recipe.id, state(game).revision)
    action = start()
    game.dice.faces = (4, 5)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    native_choice(
        game,
        PLAYER,
        "vat_sex_learn",
        effects=("plans", "good"),
        plans="PRIVATE_OWN_VATGROWN What are your actual plans?",
        good="PRIVATE_OWN_VATGROWN How can I be good for you?",
        account="My two printed mid choices",
    )
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    native_choice(game, OTHER, "vat_sex_plans", account="My actual plan")
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    native_choice(game, OTHER, "vat_sex_good", account="My actual answer")
    final = state(game)
    assert vatgrown.get(final, recipe.id).phase == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert ankou.get(final, ankou.Task, task.id).completed_event
    with ledger.engine.connect() as c:
        assert prove(game, c, final, linked["id"]).completed_event
    assert game.dice.calls == calls + 1
    tick(worker, gateway, 7)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "closed"
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == gateway.original
    assert "PRIVATE_OWN_VATGROWN" not in json.dumps(gateway.messages)
