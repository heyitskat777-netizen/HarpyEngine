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


def test_actual_pilot_native_records_original_handler_file_question_and_private_reopen(
    ledger, tmp_path, monkeypatch
):
    import test_creation_review
    import test_m2_game
    from test_m2_game import Gateway
    from test_mission_service import service as actual_service
    from test_physical_operations import place
    from test_world import initial

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.discord_adapter.m3_am_code import open_code
    from girlframe.discord_adapter.m3_am_records import open_records_source
    from girlframe.engine.drafts import DraftInput
    from girlframe.services.inbox import InboxService

    seed, selected = test_creation_review.seed, test_m2_game.selected

    def actual_seed(target, viewer=PLAYER):
        if viewer != OTHER:
            return seed(target, viewer)
        target.join(viewer, "join-3")
        target.save_draft(
            viewer,
            "draft-3",
            0,
            DraftInput(
                callsign="Actual record learner",
                girl_playbook="MOCKINGBIRD",
                frame_playbook="THE ENFORCER",
                notes="PRIVATE_OPERATOR_NOTE",
            ),
        )

    monkeypatch.setattr(test_creation_review, "seed", actual_seed)
    monkeypatch.setattr(
        test_m2_game, "selected", lambda *_: selected("MOCKINGBIRD", "THE ENFORCER")
    )
    _, game = actual_service(ledger, girl="AM", frame="THE ENFORCER")
    approved(ledger, game, tmp_path, monkeypatch, extra=(am.RULE, code.RULE))
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2, mode="outside_frame"), 3, mode="outside_frame")
        game.event(c, 1, str(uuid4()), "synthetic.actual_original_records_circuit_bodies", canon)
    service, documents = CodeService(game), RecordsService(game)
    operator = current_ref(state(game), 3)
    subject = current_ref(state(game), 2)
    candidate = next(
        x
        for x in service.menu(PLAYER, 900)["operators"]
        if x["ref"] == operator.model_dump(mode="json")
    )
    interaction_id = 986000

    def interaction(human):
        nonlocal interaction_id
        interaction_id += 1
        value = current(human, interaction_id)
        value.channel_id = 900
        return value

    async def source_form(human, operation, values):
        owner = interaction(human)
        await owner.response.defer(ephemeral=True)
        await open_code(owner, service, channel=900)
        menu = owner.edit_original_response.call_args.kwargs["view"]
        menu.values.update(source=(operation,))
        chosen = interaction(human)
        await menu.confirm.callback(chosen)
        form = chosen.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        actual = interaction(human)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)

    asyncio.run(
        source_form(
            2,
            "operator:" + candidate["id"],
            dict(account="Actual original Pilot hands accessing my real circuits"),
        )
    )
    maintenance = code.sessions(state(game))[0]
    asyncio.run(source_form(3, "records_request:" + maintenance.id, dict(subject=(subject.token,))))
    maintenance = code.session(state(game), maintenance.id)
    record = records.access(state(game), maintenance.records_access)
    assert record.learner == operator and record.subject == subject and record.phase == "requested"
    with pytest.raises(WorkflowError, match="Handler"):
        service.confirm(
            OTHER,
            str(uuid4()),
            maintenance.id,
            state(game).revision,
            "Actual circuit contact before the file exists",
        )
    assert game.dice.calls == 0 and code.session(state(game), maintenance.id).root is None
    with pytest.raises(WorkflowError):
        documents.prepare_document(
            OTHER, str(uuid4()), record.id, state(game).revision, DOCUMENT, REFERENCE, True
        )
    assert any(x.identity == record.id and x.incoming for x in InboxService(ledger).items(ADMIN))
    assert not any(x.identity == record.id for x in InboxService(ledger).items(OTHER))

    preparation_revision = state(game).revision

    async def prepare_file():
        handler = interaction(1)
        await handler.response.defer(ephemeral=True)
        await open_records_source(handler, documents, record.id)
        form = handler.edit_original_response.call_args.kwargs["view"]
        form.values.update(document=DOCUMENT, reference=REFERENCE, complete=("yes",))
        actual = interaction(1)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)
        return str(actual.id)

    preparation_key = asyncio.run(prepare_file())
    saved_revision = state(game).revision
    assert documents.prepare_document(
        ADMIN, preparation_key, record.id, preparation_revision, DOCUMENT, REFERENCE, True
    ) == dict(id=record.id)
    assert state(game).revision == saved_revision
    prepared = records.access(state(game), record.id)
    assert prepared.gm == 1 and prepared.appointment and prepared.prepared_event
    with pytest.raises(WorkflowError):
        documents.document(OTHER, record.id)
    asyncio.run(
        source_form(
            3,
            "confirm:" + maintenance.id,
            dict(account="My actual hands have access to this same AM's circuits"),
        )
    )
    maintenance = code.session(state(game), maintenance.id)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=code.PLAY,
            parent=maintenance.root,
            source_work=maintenance.id,
            target_actor=operator,
            heat=0,
            trigger_confirmed=True,
            context="The actual Pilot operates these actual AM circuits",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for human in (PLAYER, OTHER, ADMIN):
        if any(x["kind"] == "tag_window" for x in game.choices(human)):
            answer(game, human, "tag_window", options=("pass",))
    assert game.inspect(PLAYER, action)["receipt"]["faces"] == [4, 5]

    async def response(human, kind, values):
        viewer = {1: ADMIN, 2: PLAYER, 3: OTHER}[human]
        row = next(x for x in game.choices(viewer) if x["kind"] == kind)
        owner = interaction(human)
        owner.followup.send = AsyncMock()
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        actual = interaction(human)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)
        return owner, row

    asyncio.run(response(3, "am_code_options", dict(options=("records",))))
    question, _ = asyncio.run(response(3, "am_code_records_question", dict(account=QUESTION)))
    delivered = question.followup.send.call_args.kwargs
    assert delivered["ephemeral"] and DOCUMENT in delivered["file"].fp.getvalue().decode()
    assert game.inspect(PLAYER, action)["state"] != "complete"
    asyncio.run(response(1, "am_code_records_answer", dict(account=ANSWER, honest=("yes",))))
    learned = documents.document(OTHER, record.id)
    assert (learned["document"], learned["question"], learned["answer"]) == (
        DOCUMENT,
        QUESTION,
        ANSWER,
    )
    assert code.session(state(game), maintenance.id).phase == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, maintenance.root)["state"] == "complete"
    with pytest.raises(WorkflowError):
        documents.document(PLAYER, record.id)
    tick(worker, gateway, 5)
    public = json.dumps(list(gateway.messages.values()))
    assert DOCUMENT not in public and QUESTION not in public and ANSWER not in public
    assert game.dice.calls == 1
