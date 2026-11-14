"""Native AM pair performances are a real Court transfer source without invented dice."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
import test_bonded_am as creation_fixture
from m3_policy_scenario import configure_m3_fixture
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_physical_operations import place
from test_red_queen import current
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_red_queen import open_red_queen
from girlframe.engine import m3_am_sex as am_sex
from girlframe.engine import m3_red_queen as court_rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.shared_setup import CourtChoice
from girlframe.services.m3_am_sex import SexService
from girlframe.services.m3_red_queen import RedQueenService, transfer_options
from girlframe.services.onboarding import WorkflowError
from girlframe.services.shared_setup import SharedSetupService


def test_native_am_pair_complete_performances_enable_native_court_transfer_without_action(
    ledger, tmp_path, monkeypatch
):
    # Choose the actual Frame during real original creation, never replace a saved sheet.
    original_draft, original_selected = creation_fixture.DraftInput, creation_fixture.selected

    def draft(**values):
        if values.get("girl_playbook") == "AM":
            values["frame_playbook"] = court_rules.FRAME
        return original_draft(**values)

    monkeypatch.setattr(creation_fixture, "DraftInput", draft)
    monkeypatch.setattr(
        creation_fixture,
        "selected",
        lambda girl, frame: original_selected(girl, court_rules.FRAME if girl == "AM" else frame),
    )
    original_creation = creation_fixture.CreationService

    def creation_with_accepted_courts(store):
        # Complete both printed external Court choices before creation is reviewed.
        shared = SharedSetupService(store)
        for owner in (OTHER, FOUR):
            offered = shared.propose(
                owner,
                str(uuid4()),
                PLAYER.user_id,
                "court",
                shared.prepare(owner, PLAYER.user_id, "court"),
                CourtChoice(role="The Knight"),
            )
            shared.decide(PLAYER, str(uuid4()), offered["id"], 1, "accept")
        return original_creation(store)

    monkeypatch.setattr(creation_fixture, "CreationService", creation_with_accepted_courts)
    game = creation_fixture.actual_three(ledger)
    configure_m3_fixture(ledger)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(am_sex.RULE, court_rules.COURT, court_rules.TRANSFER),
    )
    game.join_scene(OTHER, str(uuid4()), 900)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial()
        for owner in (2, 3, 4):
            canon = place(canon, owner, mode="outside_frame")
        game.event(c, 1, str(uuid4()), "synthetic.original_am_court_positions", canon)
    actor, target = current_ref(state(game), 3), current_ref(state(game), 4)
    court = RedQueenService(game)
    court.initialize(OTHER, str(uuid4()), state(game).revision)
    selected_am = next(
        x for x in court_rules.records(state(game), court_rules.CourtAM) if x.bearer == actor
    )
    sex = SexService(game)
    source = sex.invite(
        OTHER,
        str(uuid4()),
        900,
        target,
        state(game).revision,
        "PRIVATE actual native AM pair proposal",
    )["id"]
    sex.confirm(FOUR, str(uuid4()), source, state(game).revision, True, "My actual consent")
    sex.perform(
        OTHER,
        str(uuid4()),
        source,
        state(game).revision,
        "My actual first performance",
        circuits_touched=False,
    )
    partial = state(game)
    assert am_sex.source(partial, source).phase == "active"
    with pytest.raises(WorkflowError, match="completed native AM"):
        court.transfer(OTHER, str(uuid4()), partial.revision, selected_am.id, target, source, "sex")
    assert state(game) == partial
    sex.perform(
        FOUR,
        str(uuid4()),
        source,
        state(game).revision,
        "My actual second performance",
        circuits_touched=False,
    )
    before = state(game)
    complete = am_sex.source(before, source)
    assert complete.phase == "complete" and complete.lesson is None
    assert complete.action is None and complete.counterpart_action is None
    assert len([x for x in am_sex.performances(before) if x.source == source]) == 2
    with ledger.engine.connect() as c:
        assert any(
            x["id"] == source for x in transfer_options(game, c, before, actor, target, "sex")
        )
    with pytest.raises(WorkflowError):
        court.transfer(PLAYER, str(uuid4()), before.revision, selected_am.id, target, source, "sex")
    assert state(game) == before

    async def native():
        opened = current(3, int(uuid4().int % 1000000000))
        await opened.response.defer(ephemeral=True)
        await open_red_queen(opened, court)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["operation"] = ("transfer",)
        request = current(3, int(uuid4().int % 1000000000))
        await menu.confirm.callback(request)
        form = request.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            am=(selected_am.id,),
            target=(target.token,),
            kind=("sex",),
            account="Actual completed native pair",
        )
        selection = current(3, int(uuid4().int % 1000000000))
        await form.confirm.callback(selection)
        sources = selection.edit_original_response.call_args.kwargs["view"]
        assert not await sources.interaction_check(current(2))
        sources.values["source"] = (source,)
        submitted = current(3, int(uuid4().int % 1000000000))
        await sources.confirm.callback(submitted)
        assert sources.completed, submitted.edit_original_response.call_args_list

    asyncio.run(native())
    after = state(game)
    assert (
        next(
            x for x in court_rules.records(after, court_rules.CourtAM) if x.id == selected_am.id
        ).bearer
        == target
    )
    assert after.sheets == before.sheets and am_sex.source(after, source) == complete
    another = next(x for x in court_rules.records(after, court_rules.CourtAM) if x.bearer == actor)
    with pytest.raises(WorkflowError, match="already transferred"):
        court.transfer(OTHER, str(uuid4()), after.revision, another.id, target, source, "sex")
    assert state(game) == after and game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"])) == 0
