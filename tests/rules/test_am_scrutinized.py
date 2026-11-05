"""Bounded original AM/NPC discovery uses the real source, roll and owned outcomes."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_enforcement_initiative import cast_target
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_am import open_choice
from girlframe.engine import m3_am as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_am_scrutinized import ScrutinyService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def rolled(store, tmp_path, monkeypatch, faces, *, handler_present=False, source_inbox=False):
    _, game = service(store, girl="AM", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": store.policy.m3_approval.model_copy(
                update={"subsystems": store.policy.m3_approval.subsystems | {"world"}}
            )
        }
    )
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(actual, 2, mode="outside_frame")
        if handler_present:
            from girlframe.engine.m3_handler_consequences import active_handler

            actual.facts.append(
                dict(
                    kind="recorded_handler_recovery_position",
                    actor=active_handler(actual).model_dump_json(),
                    cell=json.dumps([0, 0]),
                )
            )
        game.event(c, 1, str(uuid4()), "synthetic.prior_actual_am_scene", actual)
    world = WorldService(MissionService(store))
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="actual-new-am-discoverer",
            name="New Discoverer",
            jobs=("guard",),
            controller=1,
            detail="An actual on-scene NPC newly recognizes the adjustment",
            cell=(0, 0),
            revealed=True,
        ),
    )
    npc = ActorRef(kind="npc", entity="actual-new-am-discoverer")
    cast_target(game, npc)
    source = ScrutinyService(game)
    identity = source.propose(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "The actual NPC newly notices my adjusted code",
    )["id"]
    if source_inbox:
        from girlframe.discord_adapter.inbox import InboxView
        from girlframe.services.inbox import InboxService

        async def confirm_source():
            inbox = InboxService(store)
            task = next(x for x in inbox.items(ADMIN) if x.identity == identity)
            assert task.task == "m3_am_source"
            assert not any(x.identity == identity for x in inbox.items(PLAYER))
            outside_scene = current(1, 901080)
            outside_scene.channel_id = 999
            await outside_scene.response.defer(ephemeral=True)
            await InboxView(inbox, 1).route(outside_scene, task)
            form = outside_scene.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm) and "<#900>" in form.instructions
            form.values["action"] = ("confirm:" + identity,)
            selected = current(1, 901081)
            await form.confirm.callback(selected)
            confirmation = selected.edit_original_response.call_args.kwargs["view"]
            assert isinstance(confirmation, NativeForm)
            confirmation.values.update(
                realized=("yes",),
                lower=("yes",),
                human=("yes",),
                account="The original NPC confirms their actual new realization",
            )
            await confirmation.confirm.callback(current(1, 901082))
            assert confirmation.completed

        asyncio.run(confirm_source())
        confirmed = {"action_id": rules.discovery(state(game), identity).root_action}
    else:
        confirmed = source.confirm(
            ADMIN,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            True,
            True,
            "I confirm this actual new realization and rank",
        )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    root = confirmed["action_id"]
    assert game.dice.calls == 0
    game.dice.faces = faces
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            parent=root,
            source_work=identity,
            target_actor=npc,
            heat=0,
            context="I respond to this actual new discovery",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, source, npc, identity, root, action, worker, gateway


def test_mid_secret_real_bond_typed_npc_order_and_actual_disobey(ledger, tmp_path, monkeypatch):
    game, source, npc, identity, root, action, worker, gateway = rolled(
        ledger, tmp_path, monkeypatch, (4, 5)
    )
    answer(game, PLAYER, "am_select", options=("secret",), text="Please keep my actual secret")
    actual = state(game)
    actor = current_ref(actual, 2)
    assert depth(actual, actor, npc) == 1
    assert rules.holds_secret(actual, rules.discovery(actual, identity))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, root)["state"] == "complete"
    tick(worker, gateway, 5)
    order = source.secret_order(
        ADMIN, str(uuid4()), identity, 900, state(game).revision, "Keep quiet and remain here"
    )
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("disobey",))
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="disobey_orders",
            parent=order["action_id"],
            order_id=order["order_id"],
            heat=0,
            context="I actually refuse this same NPC's direct Order",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_disobey", options=("tag_heat",), number=1, text="Still jailbroken")
    answer(game, ADMIN, "handler_disobey", flag=False)
    assert game.inspect(PLAYER, child)["state"] == "complete" and game.dice.calls == 2


def test_low_actual_owned_limiter_preserves_slot_and_blocks_refusal(ledger, tmp_path, monkeypatch):
    game, source, npc, identity, root, action, _, _ = rolled(ledger, tmp_path, monkeypatch, (1, 1))
    before = state(game)
    chosen = rules.identities(before, current_ref(before, 2))[0]
    answer(
        game,
        ADMIN,
        "am_limiter",
        options=(chosen.id,),
        fields={"freedom": "refuse"},
        text="The actual discoverer installs this original Limiter",
    )
    actual = state(game)
    limited = next(x for x in actual.sheets["2"].identities if x.id == chosen.id)
    assert limited.am_limiter and limited.protected and limited.slot == chosen.slot
    assert limited.marked == chosen.marked and limited.name == rules.DEFAULTS[chosen.slot]
    assert len(actual.sheets["2"].identities) == len(before.sheets["2"].identities)
    assert len([x for x in actual.sheets["2"].identities if x.slot is not None]) == 4
    assert not rules.free(actual, current_ref(actual, 2), "refuse")
    with pytest.raises(ValueError, match="LIMITED_AM"):
        rules.require_freedom(actual, current_ref(actual, 2), "refuse")
    assert rules.discovery(actual, identity).phase == "limited"
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 1


def test_high_real_handler_restricts_then_native_original_am_blackmail(
    ledger, tmp_path, monkeypatch
):
    game, source, npc, identity, _, action, _, _ = rolled(ledger, tmp_path, monkeypatch, (6, 6))
    answer(game, ADMIN, "am_handler_options", options=("blackmail", "unbelieved"))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "am_select")
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("violence",))
        )

    async def choose():
        interaction = current(2, 901091)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(options=("blackmail",), account="Actual compromising evidence")
        await form.confirm.callback(current(2, 901092))
        assert form.completed

    asyncio.run(choose())
    actual = state(game)
    value = rules.discovery(actual, identity)
    assert value.blackmail_tag in {x.id for x in actual.world.npcs[0].tags}
    assert not rules.can_report(actual, value)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_actual_copresent_refuge_requires_and_completes_real_handler_play(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m3_handler_play_state import Effect
    from girlframe.services.m3_handler_plays import HandlerPlayService

    game, source, npc, identity, root, action, _, _ = rolled(
        ledger, tmp_path, monkeypatch, (4, 5), handler_present=True
    )
    answer(
        game,
        PLAYER,
        "am_select",
        options=("refuge",),
        text="I take refuge beside the actual Handler",
    )
    grant = rules.discovery(state(game), identity).refuge_grant
    assert grant and game.inspect(PLAYER, action)["state"] != "complete"
    handler = HandlerPlayService(ledger)
    data = handler.get(ADMIN, grant)
    handler.submit(
        ADMIN,
        str(uuid4()),
        grant,
        data["game_revision"],
        "brief",
        Effect(kind="brief", account="The Handler explains the actual risk of the discovery"),
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 1


def test_disbelief_actual_evidence_report_and_owned_limiter(ledger, tmp_path, monkeypatch):
    game, source, npc, identity, root, action, worker, gateway = rolled(
        ledger, tmp_path, monkeypatch, (4, 5)
    )
    answer(
        game,
        PLAYER,
        "am_select",
        options=("unbelieved",),
        text="They have no rank to convince anyone yet",
    )
    tick(worker, gateway, 5)
    assert not rules.can_report(state(game), rules.discovery(state(game), identity))
    source.evidence(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        "A real independent recording now shows the adjustment",
    )
    source.report(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        "The original NPC reports the actual adjustment with the new evidence",
    )
    data = source.limiter_view(ADMIN, identity)
    selected = data["identities"][0]["id"]
    source.resolve_limiter(
        ADMIN,
        str(uuid4()),
        identity,
        data["revision"],
        selected,
        "expression",
        "The original discoverer installs the actual expression Limiter",
    )
    assert not rules.free(state(game), current_ref(state(game), 2), "expression")
    assert rules.presentation(state(game), current_ref(state(game), 2))["expression"] == "smile"
    assert rules.discovery(state(game), identity).phase == "limited" and game.dice.calls == 1
