"""The apparent Handler Order uses the real Rebel source and the Girl's own response."""

import asyncio
import json

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_strain_void_spread import strain_source

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_rebel_voice import RULE, voices
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.engine.rules_registry import Registry
from girlframe.services.inbox import InboxService
from girlframe.services.m3_access import digest, load_registry
from girlframe.services.m3_npc_orders import NpcOrderService, order, source
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_rebel_voice import VoiceService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_voice_is_review_gated_and_runs_the_native_original_recipient_order(
    ledger, tmp_path, monkeypatch
):
    strain, game, _, _, identity = strain_source(ledger, 5, "rebellion")
    world = WorldService(strain.missions)
    world.faction(
        ADMIN,
        "rebel-group",
        state(game).revision,
        Faction(
            id="group",
            kind="rebel",
            name="Local Group",
            cells=((2, 2),),
        ),
    )
    roster = NpcRoleService(world)
    offer = roster.offer(
        ADMIN,
        "rebel-caller",
        state(game).revision,
        Npc(
            id="original-speaker",
            name="PRIVATE_REBEL_CALLER",
            detail="Controls the source device.",
            jobs=("handler",),
            controller=OTHER.user_id,
            cell=(2, 2),
            faction="group",
        ),
    )
    roster.respond(OTHER, "accept-speaker", offer["id"], state(game).revision, "accept")
    effects = EffectService(strain)
    effects.apply(
        ADMIN,
        "nominate",
        identity,
        1,
        state(game).revision,
        Choice(
            rule_id=RULE,
            account="The actual Rebel operator starts the printed task.",
            target="original-speaker",
        ),
    )
    assert effects.get(ADMIN, identity)["state"] == "pending"
    voice = VoiceService(strain)
    with pytest.raises(WorkflowError, match="original separate Rebel controller"):
        voice.get(PLAYER, identity, 900)
    with pytest.raises(WorkflowError, match="implementation and review"):
        voice.synthesize(OTHER, "default-gate", identity, state(game).revision, "Synthesis fixture")
    assert voices(state(game))[0].prepared is None

    data = load_registry().model_dump(mode="json")
    original = next(x for x in data["entries"] if x["id"] == RULE)
    original.update(
        implementation="implemented",
        source_audit="audited",
        independent_review="approved",
        reviewer="Synthetic test only",
        review_reference="Temporary fixture with no release scope",
        contract=next(
            x["contract"] for x in data["entries"] if x["id"].endswith("personal-firearm")
        ),
        test_evidence=["tests/rules/test_strain_rebel_voice.py"],
    )
    registry = Registry.model_validate_json(json.dumps(data))
    path = tmp_path / "synthetic-reviewed-rebel-voice.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(m3_approval=approval.model_copy(update=dict(registry_sha256=digest(registry))))
    )

    async def native(sender_number, **values):
        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(OTHER) if x.identity == identity and x.task == "m3_rebel_voice"
        )
        assert not any(x.task == "m3_rebel_voice" for x in inbox.items(PLAYER))
        click = current(OTHER.user_id, sender_number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, OTHER.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        confirm = current(OTHER.user_id, sender_number + 1)
        await form.confirm.callback(confirm)
        assert form.completed, confirm.edit_original_response.call_args

    ledger.safety(PLAYER, "pause-voice", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        voice.synthesize(OTHER, "voice-paused", identity, state(game).revision, "Synthesis fixture")
    ledger.safety(PLAYER, "resume-voice", ledger.status(PLAYER)["revision"], pause=False)
    rev = state(game).revision
    asyncio.run(native(89400, account="PRIVATE_SYNTHESIS"))
    assert (
        voice.synthesize(OTHER, "89401", identity, rev, "PRIVATE_SYNTHESIS")["state"] == "resolved"
    )
    assert effects.get(ADMIN, identity)["state"] == "resolved"
    (case,) = voices(state(game))
    assert case.prepared is not None
    assert voice.get(OTHER, identity, 1234)["girls"] == ()

    orders = NpcOrderService(game)
    with pytest.raises(WorkflowError, match="original separate Rebel controller"):
        orders.issue(
            ADMIN,
            "wrong-issuer",
            900,
            case.issuer,
            PLAYER.user_id,
            state(game).revision,
            "Stop.",
            origin_kind="rebel_voice",
            source_effect=identity,
        )
    with pytest.raises(WorkflowError, match="STALE_NPC_ORDER"):
        orders.issue(
            OTHER,
            "old-revision",
            900,
            case.issuer,
            PLAYER.user_id,
            rev,
            "Stop.",
            origin_kind="rebel_voice",
            source_effect=identity,
        )
    revision = state(game).revision
    text = "Hold by the marked door."
    asyncio.run(native(89410, girl=(str(PLAYER.user_id),), order=text))
    saved = orders.issue(
        OTHER,
        "89411",
        900,
        case.issuer,
        PLAYER.user_id,
        revision,
        text,
        origin_kind="rebel_voice",
        source_effect=identity,
    )
    with ledger.engine.connect() as c:
        action = game.action(c, saved["action_id"])
        recorded = order(game, c, action)
        source(game, c, state(game), recorded)
        assert recorded.issuer == case.issuer and recorded.principal == case.handler
        rows = c.scalars(sa.select(t.m2["m2_orders"].c.id)).all()
        assert rows == [saved["order_id"]]

    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "order_response")
    projected = game.decision(PLAYER, row["id"])
    assert projected["order_text"] == text
    assert "PRIVATE_REBEL_CALLER" not in str(projected) and "PRIVATE_SYNTHESIS" not in str(
        projected
    )
    with pytest.raises(WorkflowError):
        game.decision(OTHER, row["id"])

    async def obey():
        click = current(PLAYER.user_id, 89420)
        await click.response.defer(ephemeral=True)
        await open_choice(click, game, row["id"])
        form = click.edit_original_response.call_args.kwargs["view"]
        assert "Actual NPC issuer" not in form.instructions
        assert "disobey" in dict(form.fields[0].options)
        form.values["options"] = ("obedient",)
        await form.confirm.callback(current(PLAYER.user_id, 89421))
        assert form.completed

    asyncio.run(obey())
    tick(worker, gateway, 8)
    assert game.inspect(PLAYER, saved["action_id"])["state"] == "complete"

    second = orders.issue(
        OTHER,
        "second-voice",
        900,
        case.issuer,
        PLAYER.user_id,
        state(game).revision,
        "Follow me.",
        origin_kind="rebel_voice",
        source_effect=identity,
    )
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("disobey",))
    game.dice = Dice((2, 3))
    child = game.begin(
        PLAYER,
        "actual-disobey",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="disobey_orders",
            context="A refusal the Girl chooses.",
            trigger_confirmed=True,
            heat=0,
            order_id=second["order_id"],
            parent=second["action_id"],
            witnessed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, ADMIN, "handler_disobey", flag=True)
    result = game.inspect(PLAYER, child)
    assert result["result"]["can_disobey"] is False and game.dice.calls == 1
    assert game.inspect(PLAYER, second["action_id"])["state"] == "complete"
    tick(worker, gateway, 5)
    game.leave_scene(OTHER, "controller-leaves", 900)
    assert not voice.get(OTHER, identity, 900)["girls"]
    with pytest.raises(WorkflowError, match="authorized to view"):
        orders.issue(
            OTHER,
            "revoked-scene",
            900,
            case.issuer,
            PLAYER.user_id,
            state(game).revision,
            text,
            origin_kind="rebel_voice",
            source_effect=identity,
        )
