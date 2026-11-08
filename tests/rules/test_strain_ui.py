import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_off_duty import open_credit
from girlframe.discord_adapter.m3_strain import FACT_LABELS, open_strain, open_work
from girlframe.engine.m3_strain_catalog import ENDGAMES, ROWS
from girlframe.services.inbox import InboxService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_scenario_dropdown_does_not_initialize_or_roll_until_handler_confirms(ledger):
    svc, game = ready(ledger)

    async def run():
        viewer = current(1)
        await viewer.response.defer(ephemeral=True)
        await open_strain(viewer, svc)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and len(form.fields[0].options) == 4
        assert not await form.interaction_check(current(2))
        assert state(game).strain is None and svc.dice.calls == 0
        form.values.update(scenario=("business_as_usual",), high=())
        await form.confirm.callback(current(1, 501))
        assert state(game).strain.scenario == "business_as_usual"
        assert svc.dice.calls == 0

    asyncio.run(run())


def test_die_confirmation_and_saved_event_dropdown_are_separate_resumable_steps(ledger):
    svc, game = ready(ledger, face=4)
    prepared(svc, game)
    request = state(game).strain.requests[0]

    async def run():
        viewer = current(1)
        await viewer.response.defer(ephemeral=True)
        await open_work(viewer, svc, request.id)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert form.fields[0].key == "confirm" and svc.dice.calls == 0
        form.values["confirm"] = ("roll",)
        await form.confirm.callback(current(1, 502))
        assert svc.dice.calls == 1
        reopened = current(1, 503)
        await reopened.response.defer(ephemeral=True)
        await open_work(reopened, svc, request.id)
        options = reopened.edit_original_response.call_args.kwargs["view"]
        assert "Saved d6: 4" in options.text() and len(options.fields[0].options) == 2
        assert state(game).strain.events[0].column is None
        options.values["option"] = ("1",)
        await options.confirm.callback(current(1, 504))
        assert svc.dice.calls == 1 and state(game).strain.events[0].column == 1

    asyncio.run(run())


def test_start_trigger_form_requires_all_explicit_human_answers(ledger):
    svc, game = ready(ledger)
    svc.configure(ADMIN, "scenario", state(game).revision, "business_as_usual", frozenset())
    period = svc.periods.begin(ADMIN, "begin")
    identity = period["id"] + ":off_duty_strain_start:1"

    async def run():
        viewer = current(1)
        await viewer.response.defer(ephemeral=True)
        await open_work(viewer, svc, identity)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert len(form.fields) == 12
        form.values["account"] = "No historical triggers; current Void Assets remain canonical."
        await form.confirm.callback(current(1, 505))
        assert not state(game).strain.periods
        form.values.update({key: ("no",) for key in FACT_LABELS})
        await form.confirm.callback(current(1, 506))
        assert state(game).strain.periods == (period["id"],)
        assert len(state(game).strain.requests) == 3 and svc.dice.calls == 0

    asyncio.run(run())


def test_credit_dropdown_is_owner_only_and_inbox_uses_off_duty_category(ledger):
    svc, game = ready(ledger, frame="DOCTORDOCTOR MK. II")
    period = svc.periods.begin(ADMIN, "begin")
    identity = period["id"] + ":doctor_credit:2"
    inbox = InboxService(ledger)
    own = inbox.page(PLAYER, category="off_duty")
    assert own.item.task == "m3_off_duty_credit" and own.item.title == "DoctorDoctor credit sharing"
    other = inbox.page(OTHER, category="off_duty")
    assert other.total == 1 and other.item.task == "m3_frame_reward"
    assert "DoctorDoctor" not in other.item.title
    assert inbox.page(ADMIN, category="missions").total == 0

    async def run():
        viewer = current(2)
        await viewer.response.defer(ephemeral=True)
        await open_credit(viewer, svc.periods, identity)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert {x[0] for x in form.fields[0].options} == {"none", "3"}
        assert state(game).sheets["3"].permissions == 0
        form.values.update(recipient=("3",), account="PRIVATE_CREDIT_UI_ACCOUNT")
        await form.confirm.callback(current(2, 507))
        assert state(game).sheets["3"].permissions == 1
        other = current(3, 508)
        with pytest.raises(WorkflowError):
            await open_credit(other, svc.periods, identity)
        assert "PRIVATE_CREDIT_UI_ACCOUNT" not in str(inbox.items(ADMIN))

    asyncio.run(run())


def test_all_source_column_labels_and_endgame_slots_fit_discord_selects():
    assert len(ROWS) == 6 and all(len(rows) == 6 for rows in ROWS.values())
    assert sum(len(row) for rows in ROWS.values() for row in rows) == 72
    assert sum(len(options) for options in ENDGAMES.values()) == 22
    assert all(0 < len(label) <= 100 for rows in ROWS.values() for row in rows for label in row)
