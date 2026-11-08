import asyncio

from test_director_service import configure, ready
from test_ledger import ADMIN
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_director import open_context, open_review
from girlframe.services.inbox import InboxService

ledger = ledger_fixture


def test_handler_native_context_review_uses_own_two_names_and_zero_heat_without_pilot(ledger):
    svc, _, _, game, _, _, work = ready(ledger)

    async def run():
        viewer = current(1)
        await viewer.response.defer(ephemeral=True)
        await open_review(viewer, svc, work)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2))
        assert form.fields[0].options == (("yes", "My Handler is in the Director's presence"),)
        form.values["present"] = ("yes",)
        form.controls()
        assert {x.key for x in form.fields} == {"present", "identity1", "identity2", "account"}
        form.values.update(identity1="Afraid", identity2="Defiant", account="I am actually present")
        await form.confirm.callback(current(1, 980))
        assert form.completed and state(game).handler_heat == 0 and "1" not in state(game).sheets
        assert any(x.task == "m3_director_context" for x in InboxService(ledger).items(ADMIN))

    asyncio.run(run())


def test_actual_director_native_departure_and_handler_private_resource_view(ledger):
    svc, _, _, game, _, director, work = ready(ledger)
    configure(svc, work)
    context = state(game).director_contexts[0]

    async def run():
        handler = current(1)
        await handler.response.defer(ephemeral=True)
        await open_context(handler, svc, context.id)
        output = handler.edit_original_response.call_args.kwargs
        assert "Afraid" in output["content"] and "Heat: 0" in output["content"]
        viewer = current(director.user_id, 981)
        await viewer.response.defer(ephemeral=True)
        await open_context(viewer, svc, context.id)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert "Afraid" not in form.text() and not await form.interaction_check(current(1))
        form.values.update(npc=("director",), account="I leave the Handler's presence")
        await form.confirm.callback(current(director.user_id, 982))
        assert form.completed and not state(game).director_contexts[0].active

    asyncio.run(run())
