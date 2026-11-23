"""High Void 4.2 owns the demand, response and required collective effects."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_void_spread import strain_source

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_strain_effects import effect_form
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_pilot_fears import FearsService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def source(ledger):
    strain, game, _, period, identity = strain_source(ledger, 4, column=2)
    roles = NpcRoleService(WorldService(strain.missions))
    proposed = roles.offer(
        ADMIN,
        "director",
        state(game).revision,
        Npc(
            id="director",
            name="Director",
            jobs=("director",),
            controller=OTHER.user_id,
            detail="Human controlled fictional Director",
            cell=(0, 0),
        ),
    )
    roles.respond(OTHER, "take-role", proposed["id"], state(game).revision, "accept")
    effects = EffectService(strain)
    for track, face in (("rebellion", 1), ("budget", 5)):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, "roll-" + track, request.id, 1, state(game).revision)
        strain.choose(ADMIN, "column-" + track, request.id, 2, state(game).revision, 2)
        effects.apply(
            ADMIN,
            "other-" + track,
            request.id + ":effect",
            1,
            state(game).revision,
            Choice(
                rule_id=f"strain.{track}.low.{face}.2",
                account="Actual fixture effect.",
                rooms=((2, 3),) if track == "budget" else (),
            ),
        )
    build, commit, _ = effect_form(ADMIN, effects, identity)
    assert ("director", "Director") in next(
        x for x in build({}) if x.key == "civic_director"
    ).options
    commit(ADMIN, "stage", dict(civic_director=("director",), account="The fear surges."))
    return strain, game, period, identity, effects


def native(ledger, viewer, number, **values):
    async def run():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(viewer) if x.task == "m3_pilot_fears")
        click = current(viewer.user_id, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        confirmation = current(viewer.user_id, number + 1)
        confirmation.channel_id = 900
        await form.confirm.callback(confirmation)
        assert form.completed

    asyncio.run(run())


@pytest.mark.parametrize("addressed", (True, False), ids=("answered", "collective-severe"))
def test_directors_demand_resolves_through_actual_contribution_or_actual_punishments(
    ledger,
    addressed,
):
    strain, game, period, identity, effects = source(ledger)
    cycle = CycleService(strain.periods)
    service = FearsService(strain)
    assert not any(x.task == "m3_pilot_fears" for x in InboxService(ledger).items(PLAYER))
    with pytest.raises(WorkflowError, match="Resolve actual Strain"):
        activate(cycle, game, period)
    revision = state(game).revision
    native(ledger, OTHER, 45100, action=("demand",), account="The Directors' actual demand.")
    assert (
        FearsService(strain).act(
            OTHER,
            "45101",
            identity,
            revision,
            "demand",
            "The Directors' actual demand.",
        )["state"]
        == "pending"
    )
    assert effects.get(ADMIN, identity)["state"] == "pending"
    with pytest.raises(WorkflowError, match="original fictional Director"):
        service.act(PLAYER, "wrong-owner", identity, state(game).revision, "discipline", "No")
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.act(OTHER, "old-form", identity, revision, "discipline", "Old form")
    ledger.safety(PLAYER, "pause", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.act(OTHER, "paused", identity, state(game).revision, "discipline", "Paused")
    ledger.safety(PLAYER, "resume", ledger.status(PLAYER)["revision"], pause=False)

    if addressed:
        with pytest.raises(WorkflowError, match="actual performed action"):
            service.act(
                OTHER,
                "no-evidence",
                identity,
                state(game).revision,
                "addressed",
                "Unbacked",
                evidence="missing",
            )
        native(
            ledger,
            PLAYER,
            45200,
            action=("respond",),
            account="PRIVATE_ACTUAL_GIRL_RESPONSE",
        )
        assert not FearsService(strain).get(ADMIN, identity)["responses"]
        ((result, _),) = service.get(OTHER, identity)["responses"]
        native(
            ledger,
            OTHER,
            45300,
            action=("addressed",),
            response=(result,),
            account="I witnessed the Cadre restore public confidence.",
        )
    else:
        native(
            ledger,
            OTHER,
            45300,
            action=("discipline",),
            account="No action relieved the fears.",
        )
        punishment = PunishmentService(ledger)
        with pytest.raises(WorkflowError, match="Resolve actual Strain"):
            activate(cycle, game, period)
        for viewer in (PLAYER, OTHER):
            work = f"{identity}:severe:{viewer.user_id}"
            info = punishment.get(ADMIN, work)
            assert info["required_severity"] == "severe"
            with pytest.raises(WorkflowError, match="actual severity"):
                punishment.apply(
                    ADMIN,
                    f"minor-{viewer.user_id}",
                    work,
                    1,
                    state(game).revision,
                    Details(kind="stimulant_injection"),
                )
            response = punishment.propose_scene(
                ADMIN,
                f"scene-{viewer.user_id}",
                work,
                1,
                state(game).revision,
                "Actual on-screen discipline for this original Girl.",
            )
            for witness in (ADMIN, viewer):
                response = punishment.attest_scene(
                    witness,
                    f"attest-{work}-{witness.user_id}",
                    work,
                    response["revision"],
                    state(game).revision,
                )
            punishment.apply(
                ADMIN,
                f"apply-{viewer.user_id}",
                work,
                response["revision"],
                state(game).revision,
                Details(kind="link_surgery_reversal"),
            )
        assert {x.actor.entity for x in state(game).unlinked_careers} == {"2", "3"}
    assert effects.get(ADMIN, identity)["state"] == "resolved"
    assert activate(cycle, game, period)["phase"] == "active"
