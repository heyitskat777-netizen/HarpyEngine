"""Actual authored Strain effects preserve their original native dice and work."""

import asyncio

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_service import D6, prepared, ready
from test_world import initial

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_off_duty import open_period
from girlframe.discord_adapter.m3_strain import open_work
from girlframe.engine.m3_custom_strain import RULE, Design, occurrences, replacements
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_custom_strain import CustomStrainService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_all_three_custom_event_paths_record_real_owned_effects(ledger, tmp_path, monkeypatch):
    original, game = ready(ledger)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": policy.model_copy(update={"subsystems": policy.subsystems | {"world"}})
        }
    )
    board = initial()
    world = WorldService(original.missions)
    world.initialize(
        ADMIN, "custom-world", state(game).revision, board.board, board.locations, board.gorgons[0]
    )
    target = Npc(
        id="base-mechanic",
        name="Actual mechanic",
        jobs=("mechanic",),
        controller=1,
        detail="Original independent mechanic in the story",
        cell=(0, 0),
    )
    world.npc(ADMIN, "custom-target", state(game).revision, target)
    period = prepared(original, game, frozenset({"void"}))
    with pytest.raises(WorkflowError, match="implementation and review"):
        CustomStrainService(original).view(ADMIN, period)
    approved(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    strain = StrainService(OffDutyService(MissionService(ledger)), dice=D6(6))
    custom = CustomStrainService(strain)
    with pytest.raises(WorkflowError):
        custom.view(OTHER, period)
    before = state(game)
    requests = {x.track: x for x in before.strain.requests}
    original_roll = strain.roll(ADMIN, "original-six", requests["void"].id, 1, before.revision)
    assert original_roll["face"] == 6 and strain.dice.calls == 1

    async def author(mode, number, design, **args):
        entry = current(ADMIN.user_id, number)
        await entry.response.defer(ephemeral=True)
        await open_period(entry, strain.periods)
        off_duty = entry.edit_original_response.call_args.kwargs["view"]
        click = current(ADMIN.user_id, number + 1)
        await click.response.defer(ephemeral=True)
        await off_duty.open_item(click, "action:custom_strain")
        menu = click.edit_original_response.call_args.kwargs["view"]
        choose = current(ADMIN.user_id, number + 2)
        await choose.response.defer(ephemeral=True)
        await menu.open_item(choose, mode)
        form = choose.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(
            title=design.title, npc=(design.npc,), tag=design.tag, account=design.account, **args
        )
        submit = current(ADMIN.user_id, number + 3)
        await form.confirm.callback(submit)
        assert form.completed, submit.edit_original_response.call_args

    def design(title, tag):
        return Design(
            title=title, account="A real event witnessed at the base.", npc=target.id, tag=tag
        )

    revision = state(game).revision
    extra = design("An extra safety inspection", "Prepared")
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        custom.author(ADMIN, "stale-custom", period, revision - 1, "additional", extra)
    ledger.safety(OTHER, "pause-custom", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        custom.author(ADMIN, "paused-custom", period, revision, "additional", extra)
    ledger.safety(OTHER, "resume-custom", ledger.status(OTHER)["revision"], pause=False)
    asyncio.run(author("additional", 39600, extra))
    assert (
        custom.author(ADMIN, "39603", period, revision, "additional", extra)["state"] == "resolved"
    )
    assert state(game).strain.requests == tuple(
        x for x in before.strain.requests if x.track != "void"
    )
    replaced = design("No time for a cascade", "On alert")
    asyncio.run(author("replace_slot", 39610, replaced, work=(requests["void"].id,), column=("2",)))
    assert (saved_slot := replacements(state(game))[0]).roll == requests["void"].id
    assert tuple(x.label for x in state(game).world.npcs[-1].tags) == ("Prepared",)
    assert strain.work(ADMIN, requests["void"].id)["custom_columns"] == {"2": replaced.title}
    selection_rev = state(game).revision

    async def render_column():
        click = current(ADMIN.user_id, 39640)
        await click.response.defer(ephemeral=True)
        await open_work(click, strain, requests["void"].id)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert ("2", replaced.title) in form.fields[0].options
        form.values["option"] = ("2",)
        await form.confirm.callback(current(ADMIN.user_id, 39641))
        assert form.completed

    asyncio.run(render_column())
    result = strain.choose(ADMIN, "39641", requests["void"].id, 2, selection_rev, 2)
    assert result["rule_id"] == RULE and not result["effects_pending"]
    canon = state(game)
    (original_event,) = canon.strain.events
    assert (original_event.face, original_event.column, original_event.rule_id) == (
        6,
        2,
        "strain.void.high.6.2",
    )
    assert not any(x.parent == original_event.id for x in canon.strain.requests)
    assert occurrences(canon)[-1].replaces == saved_slot.id
    instead = design("Supply workers strike", "Overworked")
    chosen = requests["rebellion"].id
    with pytest.raises(WorkflowError):
        custom.author(
            ADMIN,
            "replace-saved-die",
            period,
            canon.revision,
            "instead_of_roll",
            instead,
            work=original_event.id,
        )
    asyncio.run(author("instead_of_roll", 39620, instead, work=(chosen,)))
    assert strain.dice.calls == 1
    assert not any(x.id == chosen for x in state(game).strain.events + state(game).strain.requests)
    assert strain.work(ADMIN, chosen)["state"] == "resolved"
    assert occurrences(state(game))[-1].source_work == chosen
    assert tuple(x.label for x in state(game).world.npcs[-1].tags) == (
        "Prepared",
        "On alert",
        "Overworked",
    )
    ledger.engine.dispose()
    assert strain.work(ADMIN, original_event.id)["body"]["face"] == 6
    assert len(occurrences(state(game))) == 3
    budget = requests["budget"].id
    strain.dice.face = 5
    strain.roll(ADMIN, "remaining-die", budget, 1, state(game).revision)
    strain.choose(ADMIN, "remaining-column", budget, 2, state(game).revision, 2)
    EffectService(strain).apply(
        ADMIN,
        "remaining-effect",
        budget + ":effect",
        1,
        state(game).revision,
        Choice(
            rule_id="strain.budget.low.5.2", account="The pilots share a room.", rooms=((2, 3),)
        ),
    )
    assert activate(CycleService(strain.periods), game, period)["phase"] == "active"
