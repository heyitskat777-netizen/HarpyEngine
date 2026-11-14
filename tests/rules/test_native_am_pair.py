"""Two actually created native AMs use owned no-roll entry without a fabricated lesson."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from m3_policy_scenario import configure_m3_fixture
from test_bonded_am import actual_three
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_am_sex import open_am_sex
from girlframe.engine import m3_am_sex as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_am_sex import SexService, prove_learned
from girlframe.services.onboarding import WorkflowError


def test_native_am_pair_owned_entry_consent_performances_and_private_completion(
    ledger, tmp_path, monkeypatch
):
    game = actual_three(ledger)
    configure_m3_fixture(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    game.join_scene(OTHER, str(uuid4()), 900)
    with ledger.transaction() as connection:
        original = state(game)
        original.world = initial()
        for owner in (2, 3, 4):
            original = place(original, owner, mode="outside_frame", cell=(0, 0))
        game.event(connection, 1, str(uuid4()), "synthetic.native_am_body_positions", original)
    service = SexService(game)
    before = state(game)
    target = current_ref(before, FOUR.user_id)
    assert before.sheets["3"].girl == before.sheets["4"].girl == "AM"
    assert {x["id"] for x in service.native_menu(OTHER, 900)["targets"]} == {target.token}
    with pytest.raises(WorkflowError):
        service.native_menu(PLAYER, 900)
    with pytest.raises(WorkflowError):
        service.invite(
            OTHER, str(uuid4()), 900, current_ref(before, 2), before.revision, "Not two native AMs"
        )

    def interaction(viewer):
        value = current(viewer.user_id, int(uuid4().int % 1000000000))
        value.channel_id = 900
        return value

    async def submit(viewer, form, **values):
        form.values.update(values)
        response = interaction(viewer)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        return response

    async def invite():
        opened = interaction(OTHER)
        await opened.response.defer(ephemeral=True)
        await open_am_sex(opened, service)
        response = await submit(
            OTHER, opened.edit_original_response.call_args.kwargs["view"], source=("native_am",)
        )
        response = await submit(
            OTHER, response.edit_original_response.call_args.kwargs["view"], source=("invite",)
        )
        form = response.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(interaction(ADMIN))
        await submit(
            OTHER, form, target=(target.token,), account="PRIVATE native voluntary proposal"
        )
        return rules.sources(state(game))[-1]

    async def operation(viewer, source, operation, **values):
        opened = interaction(viewer)
        await opened.response.defer(ephemeral=True)
        await open_am_sex(opened, service, identity=source.id)
        selected = await submit(
            viewer, opened.edit_original_response.call_args.kwargs["view"], operation=(operation,)
        )
        await submit(viewer, selected.edit_original_response.call_args.kwargs["view"], **values)

    declined = asyncio.run(invite())
    asyncio.run(operation(FOUR, declined, "confirm", accept=("no",), account="My own refusal"))
    assert rules.source(state(game), declined.id).phase == "declined"
    source = asyncio.run(invite())
    assert source.lesson is None and source.action is None and source.mode == "both_am"
    with pytest.raises(WorkflowError):
        service.view_learned(ADMIN, source.id)
    asyncio.run(operation(FOUR, source, "confirm", accept=("yes",), account="My own consent"))
    with pytest.raises(WorkflowError):
        service.perform(
            OTHER,
            str(uuid4()),
            source.id,
            state(game).revision,
            "Circuit route is separate",
            circuits_touched=True,
        )
    asyncio.run(
        operation(OTHER, source, "perform", circuits=("no",), account="PRIVATE first performance")
    )
    first = rules.source(state(game), source.id)
    assert first.used_event and first.phase == "active" and first.effect_event is None
    asyncio.run(
        operation(FOUR, source, "perform", circuits=("no",), account="PRIVATE second performance")
    )
    final = state(game)
    complete = rules.source(final, source.id)
    assert complete.phase == "complete" and complete.completed_event
    assert (
        complete.lesson is None and complete.counterpart_action is None and complete.action is None
    )
    assert len([x for x in rules.performances(final) if x.source == source.id]) == 2
    assert game.dice.calls == 0
    for owner in ("3", "4"):
        assert final.sheets[owner].heat == before.sheets[owner].heat
        assert final.sheets[owner].identities == before.sheets[owner].identities
        assert final.sheets[owner].girl_runtime == before.sheets[owner].girl_runtime
    with ledger.engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"])) == 0
        assert prove_learned(game, connection, final, source.id) == complete
        assert prove_learned(game, connection, final, declined.id).phase == "declined"
        assert (
            next(x for x in service._tasks(connection, OTHER) if x["id"] == source.id)["phase"]
            == "resolved"
        )
    assert service.view_learned(OTHER, source.id)["body"]["phase"] == "complete"
