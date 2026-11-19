"""Void concealment is a one-use audience effect with ordinary medical consequences."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both, roll_for
from test_physical_operations import place
from test_strain import facts
from test_strain_void_spread import strain_source
from test_void_lab_portal import prepare_endgame
from test_world import gorgon

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_off_duty import open_period
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_handler_void import require
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_void_privacy import Witness, grants, notices
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_handler_void import HandlerVoidService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_void_privacy import ConcealmentService
from girlframe.services.m3_void_spread import SpreadService
from girlframe.services.onboarding import WorkflowError


def arm_and_save_next_scope(ledger):
    strain, game, _, period, work = prepare_endgame(ledger, slot=5)
    concealment = ConcealmentService(ledger)
    expected = state(game).revision
    with pytest.raises(WorkflowError, match="original Endgame Handler"):
        concealment.arm(OTHER, "wrong-owner", work, 1, expected)
    with pytest.raises(WorkflowError, match="STALE_CONCEALMENT"):
        concealment.arm(ADMIN, "stale", work, 1, expected - 1)
    ledger.safety(OTHER, "privacy-pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        concealment.arm(ADMIN, "paused", work, 1, expected)
    ledger.safety(OTHER, "privacy-resume", ledger.status(OTHER)["revision"], pause=False)

    async def native():
        inbox = InboxService(ledger)
        assert not any(x.identity == work for x in inbox.items(OTHER))
        period_view = current(ADMIN.user_id, 39398)
        await period_view.response.defer(ephemeral=True)
        await open_period(period_view, strain.periods)
        picker = period_view.edit_original_response.call_args.kwargs["view"]
        period_pick = current(ADMIN.user_id, 39399)
        await period_pick.response.defer(ephemeral=True)
        await picker.open_item(period_pick, work)
        assert isinstance(period_pick.edit_original_response.call_args.kwargs["view"], NativeForm)
        card = next(x for x in inbox.items(ADMIN) if x.identity == work)
        click = current(ADMIN.user_id, 39400)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, ADMIN.user_id).route(click, card)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values["confirm"] = ("confirm",)
        await form.confirm.callback(current(ADMIN.user_id, 39401))
        assert form.completed

    asyncio.run(native())
    assert concealment.arm(ADMIN, "39401", work, 1, expected)["state"] == "resolved"
    assert concealment.view(ADMIN, work)["grant"].used_event is None
    cycle = CycleService(strain.periods)
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"

    def prepare_next(key):
        following = strain.periods.begin(ADMIN, key + "-begin")["id"]
        canon = state(game)
        affected = sum(any(a.void for a in sheet.assets) for sheet in canon.sheets.values())
        strain.prepare(
            ADMIN,
            key + "-prep",
            following,
            1,
            canon.revision,
            facts(
                at_least_half_have_void=2 * affected >= len(canon.order), no_girl_void=not affected
            ),
        )
        return following

    # The repeated high cascades lower Void for one intervening period.
    intermediate = prepare_next("intermediate-privacy")
    effects = EffectService(strain)
    for track, die, column, choice in (
        (
            "void",
            1,
            1,
            Choice(
                rule_id="strain.void.low.1.1",
                account="Another edge arrival.",
                gorgon=gorgon("directed", "intermediate-edge", (-3, 0)),
            ),
        ),
        ("rebellion", 1, 2, Choice(rule_id="strain.rebellion.low.1.2", account="Control slips.")),
        (
            "budget",
            5,
            2,
            Choice(rule_id="strain.budget.low.5.2", account="New rooms.", rooms=((2, 3),)),
        ),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = die
        strain.roll(ADMIN, "intermediate-die-" + track, request.id, 1, state(game).revision)
        strain.choose(
            ADMIN, "intermediate-column-" + track, request.id, 2, state(game).revision, column
        )
        effects.apply(
            ADMIN,
            "intermediate-effect-" + track,
            request.id + ":effect",
            1,
            state(game).revision,
            choice,
        )
    activate(cycle, game, intermediate)
    for viewer, faces in ((OTHER, (2, 2)), (PLAYER, (4, 4))):
        roll_for(cycle, game, intermediate, viewer, faces)
        call(cycle, game, viewer, intermediate, "scene", None, (), "")
        call(cycle, game, viewer, intermediate, "recover", RecoveryChoice())
    finish_routine(cycle, game, intermediate)
    call(cycle, game, ADMIN, intermediate, "finish", movement(game))
    prepare_next("next-privacy")
    request = next(x for x in state(game).strain.requests if x.track == "void")
    assert request.severity == "high"
    strain.dice.face = 2
    strain.roll(ADMIN, "next-privacy-die", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "next-privacy-column", request.id, 2, state(game).revision, 1)
    return strain, game, request.id + ":effect"


@pytest.mark.parametrize("protected", (False, True))
def test_original_area_gain_has_only_actual_witnesses_unless_concealed(ledger, protected):
    if protected:
        strain, game, effect = arm_and_save_next_scope(ledger)
    else:
        strain, game, _, _, effect = strain_source(ledger, 2)
    original_handler = active_handler(state(game))
    assert original_handler is not None
    with ledger.transaction() as c:
        positioned = place(place(state(game), 2, cell=(0, 0)), 3, cell=(0, 0))
        positioned.facts.append(
            dict(
                kind="ordinary_handler_movement",
                actor=original_handler.model_dump_json(),
                cell="[0,0]",
                event="fixture-physical-placement",
            )
        )
        game.event(c, 1, "privacy-original-poses", "synthetic.positions", positioned)
    cast = CastService(ActorService(strain.missions))
    change(cast, ADMIN, "join", original_handler)
    effects = EffectService(strain)
    strain.dice.face = 1
    effects.prepare_spread(ADMIN, "privacy-area-dice", effect, 1, state(game).revision)
    effects.prepare_spread(
        ADMIN, "privacy-area-map", effect, 2, state(game).revision, cells=((0, 0), (0, 1))
    )
    change(cast, OTHER, "withdraw", current_ref(state(game), 3))
    apply = SpreadService(strain)
    before = state(game).revision
    selected = (current_ref(state(game), 2).token,)
    with pytest.raises(WorkflowError, match="actual current witnesses"):
        apply.start(
            ADMIN,
            "withdrawn-witness",
            effect,
            before,
            3,
            (),
            "",
            witnesses=(current_ref(state(game), 3).token,),
        )

    async def native_spread():
        click = current(ADMIN.user_id, 39404)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_effect(click, effects, effect)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        options = next(x.options for x in form.fields if x.key == "witnesses")
        assert tuple(x for x, _ in options) == selected
        form.values.update(apply=("yes",), witnesses=selected)
        await form.confirm.callback(current(ADMIN.user_id, 39405))
        assert form.completed

    asyncio.run(native_spread())
    assert (
        apply.start(ADMIN, "39405", effect, before, 3, (), "", witnesses=selected)["required"] == 3
    )
    body = next(x for x in state(game).handler_void if x.body == original_handler)
    ledger.engine.dispose()
    service = ConcealmentService(ledger)
    if protected:
        (grant,) = grants(state(game))
        assert grant.used_work == body.work and grant.used_event == body.source_event
        assert not notices(state(game))
        with pytest.raises(WorkflowError, match="original witnesses"):
            service.observed(PLAYER, body.work)
        # A later original gain, unlike a retry, can be witnessed again.
        following, _ = require(
            state(game),
            original_handler,
            work="following-gain",
            source_event="following-source",
            appointment=body.appointment,
            witnesses=(Witness(actor=current_ref(state(game), 2), controller=2),),
        )
        assert notices(following)[0].id == "following-gain" and grants(following) == (grant,)
    else:
        visible = service.observed(PLAYER, body.work)
        assert visible.witnesses == (Witness(actor=current_ref(state(game), 2), controller=2),)

        async def read_observation():
            inbox = InboxService(ledger)
            entry = next(x for x in inbox.items(PLAYER) if x.task == "m3_void_privacy_notice")
            click = current(PLAYER.user_id, 39402)
            await click.response.defer(ephemeral=True)
            await InboxView(inbox, PLAYER.user_id).route(click, entry)
            assert "saw the Handler gain Void" in str(click.edit_original_response.call_args)

        asyncio.run(read_observation())
    assert not any(x.task == "m3_void_privacy_notice" for x in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError, match="original witnesses"):
        service.observed(OTHER, body.work)
    medicine = HandlerVoidService(ledger)
    with pytest.raises(WorkflowError, match="owns the medical choice"):
        medicine.get(PLAYER, body.work)
    result = medicine.choose(
        ADMIN,
        "concealed-treatment",
        body.work,
        state(game).revision,
        "knife",
        "The Handler removes the corruption",
        site="Hand",
    )
    assert result["phase"] == "removed"
