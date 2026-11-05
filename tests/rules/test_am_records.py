"""Printed Records mid/high/low outcomes through the original maintenance source."""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from test_am_scrutinized import rolled as scrutiny_rolled
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_am_code import open_source
from girlframe.engine import m3_am as am
from girlframe.engine import m3_am_code as code
from girlframe.engine import m3_am_records as records
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_am_code import CodeService
from girlframe.services.m3_am_records import RecordsService
from girlframe.services.onboarding import WorkflowError

DOCUMENT = "SYNTHETIC_RECORD_CANARY: complete Foundation file. Intake: winter. Assignment: archive."
REFERENCE = "Synthetic complete Foundation file F-003; no other records exist in this fixture."
QUESTION = "SYNTHETIC_QUESTION_CANARY: what assignment was recorded?"
ANSWER = "SYNTHETIC_ANSWER_CANARY: the Foundation assigned this person to the archive."


def rolled(store, tmp_path, monkeypatch, faces, *, native=False):
    game, _, npc, discovery, _, _, worker, gateway = scrutiny_rolled(
        store, tmp_path, monkeypatch, (4, 5)
    )
    answer(game, PLAYER, "am_select", options=("secret",), text="Keep the actual adjustment secret")
    tick(worker, gateway, 5)
    approved(store, game, tmp_path, monkeypatch, extra=(am.RULE, code.RULE))
    service = CodeService(game)
    subject = current_ref(state(game), 3)
    identity = service.propose(
        PLAYER,
        str(uuid4()),
        discovery,
        state(game).revision,
        "Actual circuit maintenance with a preselected Foundation-record subject",
        records_subject=subject,
    )["id"]
    # The real GM's complete preparation is mandatory before this source or its RNG exists.
    with pytest.raises(WorkflowError, match="complete unredacted"):
        service.confirm(ADMIN, str(uuid4()), identity, state(game).revision, "Actual access")
    assert game.dice.calls == 1 and code.session(state(game), identity).root is None
    if native:

        async def confirm():
            interaction = current(1, 905001)
            interaction.channel_id = 999
            await interaction.response.defer(ephemeral=True)
            await open_source(interaction, service, identity)
            hub = interaction.edit_original_response.call_args.kwargs["view"]
            hub.values["source"] = ("confirm:" + identity,)
            chosen = current(1, 905002)
            await hub.confirm.callback(chosen)
            form = chosen.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm)
            form.values.update(
                account="Actual physical circuit access",
                document=DOCUMENT,
                reference=REFERENCE,
                complete=("yes",),
            )
            await form.confirm.callback(current(1, 905003))
            assert form.completed

        asyncio.run(confirm())
    else:
        service.confirm(
            ADMIN,
            str(uuid4()),
            identity,
            state(game).revision,
            "Actual physical circuit access",
            records_document=DOCUMENT,
            records_reference=REFERENCE,
            records_complete=True,
        )
    value = code.session(state(game), identity)
    dossier = records.access(state(game), value.records_access)
    assert dossier.subject == subject and dossier.phase == "prepared" and dossier.appointment
    with pytest.raises(WorkflowError):
        RecordsService(game).document(ADMIN, dossier.id)
    tick(worker, gateway, 3)
    game.dice.faces = faces
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=code.PLAY,
            parent=value.root,
            source_work=identity,
            target_actor=npc,
            heat=0,
            context="Actual preconfirmed circuit access",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, identity, value.root, action, worker, gateway, dossier.id


def test_mid_native_complete_private_record_one_question_answer_and_source_closure(
    ledger, tmp_path, monkeypatch
):
    game, identity, root, action, worker, gateway, document = rolled(
        ledger, tmp_path, monkeypatch, (4, 5), native=True
    )

    async def respond(kind, values, interaction_id):
        row = next(x for x in game.choices(ADMIN) if x["kind"] == kind)
        interaction = current(1, interaction_id)
        interaction.followup.send = AsyncMock()
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        await form.confirm.callback(current(1, interaction_id + 1))
        assert form.completed
        return interaction

    asyncio.run(respond("am_code_options", {"options": ("records",)}, 905010))
    question = asyncio.run(respond("am_code_records_question", {"account": QUESTION}, 905020))
    # The acquired complete document is sent only in an ephemeral operator attachment.
    private = question.followup.send.call_args.kwargs
    assert private["ephemeral"] and DOCUMENT in private["file"].fp.getvalue().decode()
    assert game.inspect(PLAYER, root)["state"] != "complete"
    assert game.inspect(PLAYER, action)["state"] != "complete"
    asyncio.run(respond("am_code_records_answer", {"account": ANSWER, "honest": ("yes",)}, 905030))
    actual = RecordsService(game).document(ADMIN, document)
    assert (actual["document"], actual["question"], actual["answer"]) == (
        DOCUMENT,
        QUESTION,
        ANSWER,
    )
    assert records.access(state(game), document).phase == "answered"
    assert code.session(state(game), identity).phase == "complete"
    assert game.inspect(PLAYER, root)["state"] == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    # One focused privacy assertion covers the subject, unrelated player and public delivery.
    projections = []
    for viewer in (PLAYER, OTHER):
        with pytest.raises(WorkflowError):
            RecordsService(game).document(viewer, document)
        projections += [
            game.sheet(viewer),
            game.sheet(viewer, 3),
            CodeService(game).menu(viewer, 900),
        ]
        try:
            projections.append(game.inspect(viewer, action))
        except WorkflowError:
            pass
    exposed = json.dumps(projections + list(gateway.messages.values()))
    assert all(secret not in exposed for secret in (DOCUMENT, QUESTION, ANSWER, REFERENCE))
    assert game.dice.calls == 2


def test_high_two_printed_selections_keep_status_loss_and_wait_for_both_effects(
    ledger, tmp_path, monkeypatch
):
    game, identity, root, action, _, _, document = rolled(ledger, tmp_path, monkeypatch, (6, 6))
    assert state(game).order[-1] == 2
    selected = code.choices(state(game), current_ref(state(game), 2))[0]
    answer(game, ADMIN, "am_code_options", options=("identities", "records"))
    answer(game, ADMIN, "am_code_records_question", text=QUESTION)
    answer(game, ADMIN, "am_code_records_answer", text=ANSWER, flag=True)
    assert game.inspect(PLAYER, action)["state"] != "complete"
    answer(
        game,
        ADMIN,
        "am_code_edit",
        options=("edit",),
        fields={selected.id: "Archive Self"},
        text="Actual original operator rewrite",
    )
    actual = state(game)
    value = code.session(actual, identity)
    assert actual.sheets["2"].identities
    assert (
        next(
            x for x in actual.sheets["2"].identities if x.id == value.replacements[selected.id]
        ).name
        == "Archive Self"
    )
    assert records.access(actual, document).phase == "answered" and value.phase == "complete"
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 2


def test_low_retains_actual_spoken_order_and_grants_no_records(ledger, tmp_path, monkeypatch):
    game, identity, root, action, worker, gateway, document = rolled(
        ledger, tmp_path, monkeypatch, (1, 1)
    )
    assert not any(x["kind"].startswith("am_code_records_") for x in game.choices(ADMIN))
    words = "I am performing the actual original spoken Order"
    answer(game, ADMIN, "am_code_order", text=words)
    assert game.inspect(PLAYER, action)["state"] != "complete"
    answer(game, PLAYER, "am_code_obey", options=("obedient",), text=words)
    value = code.session(state(game), identity)
    assert value.order and value.performance == words and value.phase == "complete"
    assert records.access(state(game), document).phase == "not_granted"
    with pytest.raises(WorkflowError):
        RecordsService(game).document(ADMIN, document)
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 2
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
