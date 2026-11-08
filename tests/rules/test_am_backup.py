"""Genuine backup choices and original-AM-owned restorations, with immutable history."""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_am_code import rolled
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_am_code import open_code
from girlframe.engine import m3_am as am
from girlframe.engine import m3_am_backup as backup
from girlframe.engine import m3_am_code as code
from girlframe.engine import m3_am_memory as memory
from girlframe.engine.m2 import ChoiceAnswer, GameState, Obligation, mark_identity
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_am_backup import BackupService, prove
from girlframe.services.m3_am_code import CodeService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError

MEMORY = "SYNTHETIC_BACKUP_MEMORY_CANARY: I remember the courier's actual blue door."


def test_mid_native_genuine_snapshot_restore_keeps_limiter_marks_work_privacy_and_replay(
    ledger, tmp_path, monkeypatch
):
    game, maintenance, root, action, worker, gateway, selected = rolled(
        ledger, tmp_path, monkeypatch, (4, 5), marked=True, choose_identity=False
    )
    before = state(game)
    actor = current_ref(before, 2)

    async def choose_backup():
        row = next(x for x in game.choices(ADMIN) if x["kind"] == "am_code_options")
        operator = current(1, 907001)
        await operator.response.defer(ephemeral=True)
        await open_choice(operator, game, row["id"])
        form = operator.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and form.fields[0].maximum == 2
        assert "backup" in dict(form.fields[0].options)
        form.values["options"] = ("backup", "identities")
        await form.confirm.callback(current(1, 907002))
        assert form.completed

    asyncio.run(choose_backup())
    saved = backup.backup(state(game), code.session(state(game), maintenance).backup)
    assert saved.identities == tuple(before.sheets["2"].identities)
    assert saved.actor == actor and saved.captured_revision == before.revision
    assert not saved.memory_losses and saved.memory_baseline is None
    service = BackupService(game)
    with pytest.raises(WorkflowError, match="actions/scene locks"):
        service.restore(PLAYER, str(uuid4()), saved.id, state(game).revision)
    answer(
        game,
        ADMIN,
        "am_code_edit",
        options=("edit",),
        fields={selected.id: "Later Actual Self", "memory_scope": "selected", "memories": MEMORY},
        text="The actual operator changes original Identity content and removes this real memory",
    )
    assert game.inspect(PLAYER, root)["state"] == "complete"
    tick(worker, gateway, 5)
    # Trusted synthetic later sources create a real later Limiter, mark charge and required work.
    with ledger.transaction() as c:
        actual = state(game)
        session = code.session(actual, maintenance)
        event = str(uuid4())
        sheet = actual.sheets["2"]
        limited = next(x for x in sheet.identities if x.slot == 1)
        proof = am.Limiter(
            id="actual-later-limiter",
            actor=actor,
            identity=limited.id,
            slot=1,
            freedom="expression",
            discoverer=session.operator,
            controller=1,
            discovery="actual-later-discovery",
            action=action,
            source_event=event,
            before_json=limited.model_dump_json(),
        )
        sheet.identities = [
            x.model_copy(update=dict(name=am.DEFAULTS[1], protected=True, am_limiter=proof.id))
            if x.id == limited.id
            else x
            for x in sheet.identities
        ]
        actual.facts.append(dict(kind="am_limiter", id=proof.id, body=proof.model_dump_json()))
        charged = next(x for x in sheet.identities if x.slot == 2)
        mark_identity(sheet, charged.id, 2, state=actual)
        sheet.sedation_locked = (charged.id,)
        actual.obligations.append(
            Obligation(
                id="actual-later-obligation",
                kind="synthetic_required_work",
                owner=2,
                action=action,
                details={"source": "actual later mandatory consequence"},
            )
        )
        game.event(
            c, 1, str(uuid4()), "synthetic.actual_later_consequences", actual, event_id=event
        )
        related(
            c,
            game.store,
            dict(campaign_id=ledger.campaign_id, campaign_context=True),
            "actual-later-work",
            1,
            2,
            "synthetic_required_work",
            dict(source=event),
            event,
        )
    before_restore = state(game)
    assert not memory.can_recall(before_restore, actor, MEMORY, learned_revision=before.revision)
    # State reconstruction proves no transient in-memory snapshot is used.
    restarted = GameService(game.store, dice=game.dice)
    service = BackupService(restarted)
    preview = service.preview(PLAYER, saved.id)
    assert len(preview["retained"]) == 1 and "Limited" in preview["retained"][0]["reason"]
    assert preview["retained"][0]["slot"] == 1
    with pytest.raises(WorkflowError):
        service.restore(ADMIN, str(uuid4()), saved.id, preview["revision"])
    with pytest.raises(WorkflowError):
        service.get(OTHER, saved.id)
    tampered = GameState.model_validate_json(before_restore.model_dump_json())
    forged = saved.model_copy(update=dict(captured_revision=0))
    tampered.facts = [
        dict(kind="am_backup", id=saved.id, body=forged.model_dump_json())
        if x.get("kind") == "am_backup"
        else x
        for x in tampered.facts
    ]
    with ledger.engine.connect() as c, pytest.raises(WorkflowError, match="immutable"):
        prove(restarted, c, tampered, saved.id)

    async def revert():
        owner = current(2, 907010)
        await owner.response.defer(ephemeral=True)
        await open_code(owner, CodeService(restarted), channel=999)
        menu = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(menu, NativeForm)
        assert ("backup:" + saved.id) in dict(menu.fields[0].options)
        menu.values["source"] = ("backup:" + saved.id,)
        chosen = current(2, 907011)
        chosen.followup.send = AsyncMock()
        await menu.confirm.callback(chosen)
        attachment = chosen.followup.send.call_args.kwargs
        assert attachment["ephemeral"]
        contents = json.loads(attachment["file"].fp.getvalue())
        assert (
            contents["saved_snapshot"]["identities"] == service.get(PLAYER, saved.id)["identities"]
        )
        assert contents["actual_restore"]["retained"] == preview["retained"]
        form = chosen.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and "Current Limited" in form.instructions
        form.values["revert"] = ("yes",)
        await form.confirm.callback(current(2, 907012))
        assert form.completed

    asyncio.run(revert())
    actual = state(restarted)
    reverted = backup.latest(actual, actor)
    assert reverted and reverted.retained[0].slot == 1
    owned = restarted.sheet(PLAYER)["am_runtime"]
    assert owned["backups"] == [dict(id=saved.id, captured_revision=saved.captured_revision)]
    assert owned["memory_reversion"] == reverted.model_dump(mode="json")
    assert "am_runtime" not in restarted.sheet(OTHER, 2)
    sheet = actual.sheets["2"]
    restored = next(x for x in sheet.identities if x.slot == selected.slot)
    assert (restored.id, restored.name, restored.marked) == (selected.id, selected.name, True)
    assert next(x for x in sheet.identities if x.slot == 1).am_limiter == "actual-later-limiter"
    assert next(x for x in sheet.identities if x.slot == 2).marked
    assert sheet.sedation_locked == before_restore.sheets["2"].sedation_locked
    assert sheet.heat == before_restore.sheets["2"].heat
    assert sheet.assets == before_restore.sheets["2"].assets
    assert sheet.permissions == before_restore.sheets["2"].permissions
    assert sheet.frame_runtime == before_restore.sheets["2"].frame_runtime
    assert actual.placements == before_restore.placements
    assert actual.obligations == before_restore.obligations and actual.order == before_restore.order
    assert memory.can_recall(actual, actor, MEMORY, learned_revision=before.revision)
    assert not memory.can_recall(
        actual, actor, "Actual later experience", learned_revision=before_restore.revision
    )
    assert memory.can_recall(
        actual, actor, "Genuinely learned now", learned_revision=actual.revision
    )
    assert backup.backup(actual, saved.id) == saved
    assert all(x in actual.facts for x in before_restore.facts)
    revision = actual.revision
    replay = service.restore(PLAYER, "907012", saved.id, preview["revision"])
    assert replay["id"] == reverted.id and state(restarted).revision == revision
    assert len(backup.reversions(state(restarted), actor)) == 1 and game.dice.calls == 2
    with ledger.engine.connect() as c:
        work = t.m3["m3_required_work"]
        assert (
            c.scalar(sa.select(work.c.state).where(work.c.id == "actual-later-work")) == "pending"
        )
    public = json.dumps(
        [game.sheet(OTHER, 2), CodeService(game).menu(OTHER, 900)] + list(gateway.messages.values())
    )
    assert MEMORY not in public and "am_backup_reversion" not in public


def test_high_backup_only_is_real_and_original_am_can_revert_without_operator_or_new_rng(
    ledger, tmp_path, monkeypatch
):
    game, maintenance, root, _, worker, gateway, _ = rolled(
        ledger, tmp_path, monkeypatch, (6, 6), choose_identity=False
    )
    assert state(game).order[-1] == 2
    before = state(game)
    answer(game, ADMIN, "am_code_options", options=("backup",))
    saved = backup.backup(state(game), code.session(state(game), maintenance).backup)
    assert saved.identities == tuple(before.sheets["2"].identities)
    assert code.session(state(game), maintenance).phase == "complete"
    assert game.inspect(PLAYER, root)["state"] == "complete"
    tick(worker, gateway, 5)
    # The original operator may be absent/dead later; no fresh circuit access is required.
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = actual.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update=dict(alive=False)) if x.id == saved.operator.entity else x
                    for x in actual.world.npcs
                )
            }
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_operator_later_ended", actual)
    service = BackupService(game)
    preview = service.preview(PLAYER, saved.id)
    service.restore(PLAYER, str(uuid4()), saved.id, preview["revision"])
    assert backup.latest(state(game), saved.actor).backup == saved.id
    assert state(game).order[-1] == 2 and game.dice.calls == 2


def test_low_cannot_create_a_backup_and_keeps_actual_order_fulfillment(
    ledger, tmp_path, monkeypatch
):
    game, maintenance, root, _, _, _, _ = rolled(
        ledger, tmp_path, monkeypatch, (1, 1), choose_identity=False
    )
    assert not any(x["kind"] == "am_code_options" for x in game.choices(ADMIN))
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "am_code_order")
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("backup",), text="Pretend a backup exists"),
        )
    answer(game, ADMIN, "am_code_order", text="I speak these actual words")
    answer(game, PLAYER, "am_code_obey", options=("obedient",), text="I speak these actual words")
    assert not backup.backups(state(game)) and code.session(state(game), maintenance).backup is None
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 2
