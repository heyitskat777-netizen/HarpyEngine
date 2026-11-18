"""Only the Harpy's native finished Assault releases the actual raid work."""

import asyncio

import pytest
from test_harpy_assault import rolled
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_service import D6, prepared

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_strain_effects import effect_form
from girlframe.engine.m3_harpy_raid import raids
from girlframe.engine.m3_strain_effects import Choice
from girlframe.services.inbox import InboxService
from girlframe.services.m3_harpy_raid import RaidService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError


def test_harpy_raid_consumes_real_attack_and_records_original_obsession(ledger, monkeypatch):
    approval = {}

    def stage(game, actor):
        policy = ledger.policy.m3_approval
        ledger.policy = ledger.policy.model_copy(
            update={
                "m3_approval": policy.model_copy(
                    update={
                        "subsystems": policy.subsystems | {"strain", "playbooks"},
                    }
                ),
            }
        )
        strain = StrainService(OffDutyService(MissionService(ledger)), dice=D6(1))
        period = prepared(strain, game, high=frozenset({"void"}))
        effect = EffectService(strain)
        work = ""
        for track, face, col in (("void", 1, 1), ("rebellion", 1, 2), ("budget", 5, 2)):
            request = next(x for x in state(game).strain.requests if x.track == track)
            strain.dice.face = face
            strain.roll(ADMIN, f"die-{track}", request.id, 1, state(game).revision)
            strain.choose(ADMIN, f"column-{track}", request.id, 2, state(game).revision, col)
            identity = request.id + ":effect"
            if track == "void":
                work = identity
                assert effect.get(ADMIN, work)["rule_id"] == "strain.void.high.1.1"
            else:
                effect.apply(
                    ADMIN,
                    f"finish-{track}",
                    identity,
                    1,
                    state(game).revision,
                    Choice(
                        rule_id=f"strain.{track}.low.{face}.2",
                        account="Actual other event.",
                        rooms=((2, 3),) if track == "budget" else (),
                    ),
                )
        _, apply, _ = effect_form(ADMIN, effect, work)
        values = dict(
            harpy=(actor.entity,), obsession=("3",), account="The occupied base is attacked."
        )
        with pytest.raises(WorkflowError, match="actual free Harpy and original Cadre"):
            apply(ADMIN, "wrong-occupied-base", values | {"raid_base": ("base1",)})
        apply(ADMIN, "stage-raid", values | {"raid_base": ("base0",)})
        assert effect.get(ADMIN, work)["awaiting_harpy_raid"]
        assert RaidService(strain).get(PLAYER, work)["attacks"] == ()
        with pytest.raises(WorkflowError, match="Resolve actual Strain"):
            activate(CycleService(strain.periods), game, period)
        approval.update(strain=strain, work=work, period=period)

    _, game, worker, gateway, actor, action, declaration = rolled(
        ledger,
        monkeypatch,
        before_attack=stage,
    )
    strain, work, period = (approval[x] for x in ("strain", "work", "period"))
    service = RaidService(strain)
    assert service.get(PLAYER, work)["attacks"] == ()
    assert not any(x.task == "m3_harpy_raid" for x in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError, match="original Harpy's controller"):
        service.finish(ADMIN, "wrong-controller", work, state(game).revision, action)
    answer(game, PLAYER, "engage_assault_extra")
    for viewer in (ADMIN, PLAYER, OTHER):
        answer(game, viewer, "battle_assault_table", flag=False, text="Actual table judgment")
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert next(
        x for x in state(game).sheets["3"].assets if x.id == declaration.target_asset
    ).damaged
    revision = state(game).revision
    events = state(game).strain.events
    assert service.get(PLAYER, work)["attacks"][0][0] == action
    ledger.safety(OTHER, "raid-pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.finish(PLAYER, "paused-raid", work, revision, action)
    ledger.safety(OTHER, "raid-resume", ledger.status(OTHER)["revision"], pause=False)

    async def finish_from_inbox():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(PLAYER) if x.task == "m3_harpy_raid")
        click = current(PLAYER.user_id, 48600)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, PLAYER.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values["action"] = (action,)
        await form.confirm.callback(current(PLAYER.user_id, 48601))
        assert form.completed

    asyncio.run(finish_from_inbox())
    assert (
        RaidService(strain).finish(PLAYER, "48601", work, revision, action)["state"] == "resolved"
    )
    (recorded,) = raids(state(game))
    assert recorded.obsession == declaration.target and recorded.harpy == actor
    assert recorded.action == action and state(game).strain.events == events
    assert game.dice.calls == 1
    assert activate(CycleService(strain.periods), game, period)["phase"] == "active"
