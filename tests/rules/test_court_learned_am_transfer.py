"""A genuinely learned AM performance pair is an original Court transfer source."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
import test_vatgrown_plays as fixture
from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_red_queen import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_red_queen import open_red_queen
from girlframe.engine import m3_am_sex as am_sex
from girlframe.engine import m3_red_queen as court_rules
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_am_sex import SexService, prove_learned
from girlframe.services.m3_red_queen import RedQueenService, transfer_options
from girlframe.services.onboarding import WorkflowError


def test_actual_learned_am_pair_performances_enable_native_court_transfer(
    ledger, tmp_path, monkeypatch
):
    original_service = fixture.service
    monkeypatch.setattr(
        fixture,
        "service",
        lambda store, **kwargs: original_service(store, **(kwargs | {"frame": court_rules.FRAME})),
    )
    game, worker, gateway, controls = fixture.ready(ledger, tmp_path, monkeypatch, teacher="AM")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            vat.EXPERIMENT,
            vat.INVESTMENT,
            vat.SEX,
            vat.BRUTALIZE,
            am_sex.RULE,
            court_rules.COURT,
            court_rules.TRANSFER,
        ),
    )
    lesson = fixture._learn_daily_source(game, worker, gateway, controls, am_sex.RULE)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    assert state(game).sheets["2"].girl == "VATGROWN"
    court = RedQueenService(game)
    court.initialize(PLAYER, str(uuid4()), state(game).revision)
    selected_am = next(
        x for x in court_rules.records(state(game), court_rules.CourtAM) if x.bearer == actor
    )
    with ledger.engine.connect() as c:
        action_count = c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"]))
    calls = game.dice.calls
    sex = SexService(game)
    source = sex.invite(
        PLAYER,
        str(uuid4()),
        900,
        target,
        state(game).revision,
        "Actual learned AM source after original lesson",
        learned_source=lesson.id,
    )["id"]
    sex.confirm(OTHER, str(uuid4()), source, state(game).revision, True, "My actual consent")
    sex.perform(
        PLAYER,
        str(uuid4()),
        source,
        state(game).revision,
        "My actual learned-source performance",
        circuits_touched=False,
    )
    partial = state(game)
    with pytest.raises(WorkflowError):
        court.transfer(
            PLAYER, str(uuid4()), partial.revision, selected_am.id, target, source, "sex"
        )
    assert state(game) == partial
    sex.perform(
        OTHER,
        str(uuid4()),
        source,
        state(game).revision,
        "My independently performed original scene",
        circuits_touched=False,
    )
    before = state(game)
    complete = am_sex.source(before, source)
    assert complete.phase == "complete" and complete.lesson == lesson.id
    assert (
        complete.mode == "both_am"
        and complete.action is None
        and complete.counterpart_action is None
    )
    assert len([x for x in am_sex.performances(before) if x.source == source]) == 2
    with ledger.engine.connect() as c:
        assert prove_learned(game, c, before, source) == complete
        assert any(
            x["id"] == source for x in transfer_options(game, c, before, actor, target, "sex")
        )

    async def native():
        opened = current(2, int(uuid4().int % 1000000000))
        await opened.response.defer(ephemeral=True)
        await open_red_queen(opened, court)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["operation"] = ("transfer",)
        request = current(2, int(uuid4().int % 1000000000))
        await menu.confirm.callback(request)
        form = request.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            am=(selected_am.id,),
            target=(target.token,),
            kind=("sex",),
            account="Actual completed native pair",
        )
        selection = current(2, int(uuid4().int % 1000000000))
        await form.confirm.callback(selection)
        sources = selection.edit_original_response.call_args.kwargs["view"]
        assert not await sources.interaction_check(current(3))
        sources.values["source"] = (source,)
        submitted = current(2, int(uuid4().int % 1000000000))
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
        court.transfer(PLAYER, str(uuid4()), after.revision, another.id, target, source, "sex")
    assert state(game) == after and game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"])) == action_count
