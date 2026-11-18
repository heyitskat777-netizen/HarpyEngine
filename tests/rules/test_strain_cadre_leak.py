"""Scoped original incident and two genuine endings of Low Rebellion 3.2."""

import asyncio

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_void_spread import strain_source
from test_world import gorgon

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_strain_effects import effect_form
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_cadre_leak import leaks
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_battle_npc import NpcDamageService
from girlframe.services.m3_cadre_leak import LeakService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

REPORT = "Footage of mistreatment circulated on public channels."
PRIVATE = "PRIVATE_ORIGINAL_INCIDENT"
APOLOGY = "I apologize for our treatment of the Cadre."


def open_source(ledger):
    strain, game, _, period, identity = strain_source(ledger, 3, "rebellion", 2, high=False)
    world = WorldService(strain.missions)
    roles = NpcRoleService(world)
    offered = roles.offer(
        ADMIN,
        "incident-director",
        state(game).revision,
        Npc(
            id="director",
            name="Director",
            jobs=("director",),
            controller=3,
            detail="Original higher-up",
            cell=(0, 0),
        ),
    )
    roles.respond(OTHER, "accept-leak-director", offered["id"], state(game).revision, "accept")
    target = ActorRef(kind="npc", entity="private-informant")
    world.npc(
        ADMIN,
        "leak-party",
        state(game).revision,
        Npc(
            id=target.entity,
            name="Original informant",
            jobs=("civilian",),
            controller=1,
            detail="The actual original party",
            cell=(0, 0),
            revealed=True,
        ),
    )
    effect = EffectService(strain)
    for track, face, column in (("void", 2, 1), ("budget", 5, 2)):
        work = next(x for x in state(game).strain.requests if x.track == track)
        high_void = track == "void" and work.severity == "high"
        if high_void:
            face = 5
        strain.dice.face = face
        strain.roll(ADMIN, "die-" + track, work.id, 1, state(game).revision)
        strain.choose(ADMIN, "column-" + track, work.id, 2, state(game).revision, column)
        effect.apply(
            ADMIN,
            "finish-" + track,
            work.id + ":effect",
            1,
            state(game).revision,
            Choice(
                rule_id=f"strain.{track}.{work.severity}.{face}.{column}",
                account="Actual source.",
                gorgon=gorgon("dormant", "neighbor", (1, 0))
                if track == "void" and not high_void
                else None,
                revelation_play="reveal_near_disaster" if high_void else None,
                revelation_channel=900 if high_void else None,
                rooms=((2, 3),) if track == "budget" else (),
            ),
        )
    _, commit, _ = effect_form(ADMIN, effect, identity)
    commit(
        ADMIN,
        "publish-incident",
        dict(
            civic_director=("director",),
            parties=(target.token,),
            account=PRIVATE,
            leak_report=REPORT,
        ),
    )
    return strain, game, period, identity, target


def native(ledger, viewer, number, task, **values):
    async def run():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(viewer) if x.task == task)
        interaction = current(viewer.user_id, number)
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(interaction, item)
        reply = interaction.edit_original_response.call_args.kwargs
        if values:
            form = reply["view"]
            assert isinstance(form, NativeForm)
            form.values.update(values)
            await form.confirm.callback(current(viewer.user_id, number + 1))
            assert form.completed
        return reply["content"]

    return asyncio.run(run())


@pytest.mark.parametrize("elimination", (False, True), ids=("public-apology", "proved-death"))
def test_leak_preserves_private_parties_and_requires_a_real_end(ledger, elimination):
    strain, game, period, identity, target = open_source(ledger)
    service = LeakService(strain)
    cycle = CycleService(strain.periods)
    assert native(ledger, PLAYER, 49000, "m3_cadre_report") == REPORT
    assert PRIVATE not in str(InboxService(ledger).items(PLAYER))
    assert target.entity not in str(service.get(OTHER, identity))
    with pytest.raises(WorkflowError, match="original Handler and Director"):
        service.get(PLAYER, identity)
    with pytest.raises(WorkflowError, match="Resolve actual Strain"):
        activate(cycle, game, period)
    with pytest.raises(WorkflowError, match="actual status"):
        service.act(
            ADMIN,
            "invented-claim",
            identity,
            state(game).revision,
            "verify_elimination",
            "An unbacked claim about the fate of the original informant.",
        )
    if elimination:
        handler = HandlerPlayService(ledger)
        grant = handler.start(ADMIN, "start-real-mess", state(game).revision, (target,))["id"]
        handler.submit(
            ADMIN,
            "make-mess",
            grant,
            state(game).revision,
            "mess",
            Effect(kind="damage", target=target, account="The informant takes a real hit."),
        )
        work = t.m3["m3_required_work"]
        with ledger.engine.connect() as c:
            row = (
                c.execute(
                    sa.select(work).where(
                        work.c.campaign_id == ledger.campaign_id,
                        work.c.kind == "npc_damage",
                    )
                )
                .mappings()
                .one()
            )
        NpcDamageService(ledger).respond(
            ADMIN,
            "actual-death",
            row["id"],
            row["revision"],
            "kill",
            "The original informant dies from the adjudicated hit.",
        )
        native(
            ledger,
            ADMIN,
            49010,
            "m3_cadre_leak",
            action=("verify_elimination",),
            account="The original target's actual death is verified.",
        )
        assert leaks(state(game))[0].death_events
        assert not any(x.task == "m3_cadre_apology" for x in InboxService(ledger).items(PLAYER))
    else:
        revision = state(game).revision
        native(
            ledger,
            OTHER,
            49020,
            "m3_cadre_leak",
            action=("demand",),
            account="The higher-ups require a public apology.",
        )
        assert EffectService(strain).get(ADMIN, identity)["state"] == "pending"
        with pytest.raises(WorkflowError, match="STALE_STATE"):
            service.act(ADMIN, "stale-apology", identity, revision, "apologize", APOLOGY)
        revision = state(game).revision
        native(ledger, ADMIN, 49030, "m3_cadre_leak", action=("apologize",), account=APOLOGY)
        assert (
            LeakService(strain).act(
                ADMIN,
                "49031",
                identity,
                revision,
                "apologize",
                APOLOGY,
            )["state"]
            == "resolved"
        )
        assert native(ledger, PLAYER, 49040, "m3_cadre_apology") == APOLOGY
    assert EffectService(strain).get(ADMIN, identity)["state"] == "resolved"
    assert activate(cycle, game, period)["phase"] == "active"
