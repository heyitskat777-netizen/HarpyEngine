"""The original Girl finds an actual NPC before or after their real Void gain."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_physical_operations import place
from test_strain_void_spread import strain_source

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_strain_effects import DependentForm
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird_sex import corruption_options
from girlframe.engine.m3_npc_interest import RULE, interests
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_npc_interest import InterestService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("timing", ("before", "after"))
def test_native_npc_interest_resolves_only_after_actual_discovery_and_corruption(ledger, timing):
    strain, game, _, period, _ = strain_source(ledger, 6, column=2)
    effects = EffectService(strain)

    def select(track, severity, face, column):
        request = next(
            x for x in state(game).strain.requests if x.track == track and x.severity == severity
        )
        strain.dice.face = face
        strain.roll(ADMIN, "die-" + request.id, request.id, 1, state(game).revision)
        strain.choose(ADMIN, "column-" + request.id, request.id, 2, state(game).revision, column)
        return request.id + ":effect"

    for track, severity, face, column, choice in (
        (
            "void",
            "high",
            5,
            1,
            Choice(
                rule_id="strain.void.high.5.1",
                account="The Handler speaks to the Cadre.",
                revelation_play="reveal_near_disaster",
                revelation_channel=900,
            ),
        ),
        (
            "rebellion",
            "low",
            1,
            2,
            Choice(rule_id="strain.rebellion.low.1.2", account="Actual original effect."),
        ),
        (
            "budget",
            "low",
            5,
            2,
            Choice(rule_id="strain.budget.low.5.2", account="Shared quarters.", rooms=((2, 3),)),
        ),
    ):
        work = select(track, severity, face, column)
        effects.apply(ADMIN, "effect-" + track, work, 1, state(game).revision, choice)

    work = select("void", "low", 5, 2)
    npc = ActorRef(kind="npc", entity="reader")
    WorldService(strain.missions).npc(
        ADMIN,
        "introduce-reader",
        state(game).revision,
        Npc(
            id=npc.entity,
            name="The Reader",
            jobs=("civilian",),
            detail="Private NPC description",
            controller=ADMIN.user_id,
            cell=(0, 0),
        ),
    )

    async def route(viewer, number, task, values=None):
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(viewer) if x.identity == work and x.task == task)
        click = current(viewer.user_id, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(click, item)
        data = click.edit_original_response.call_args.kwargs
        if values is None:
            return data
        form = data["view"]
        assert isinstance(form, NativeForm)
        if task == "m3_strain_effect":
            assert isinstance(form, DependentForm)
        form.values.update(values)
        await form.confirm.callback(current(viewer.user_id, number + 1))
        assert form.completed

    hidden = "PRIVATE_SOURCE_INTEREST"
    values = dict(
        interest_npc=(npc.entity,),
        interest_girl=("2",),
        interest_timing=(timing,),
        account=hidden,
    )
    if timing == "after":
        values["interest_manifestation"] = ("brain",)
    assert effects.get(ADMIN, work)["rule_id"] == RULE
    asyncio.run(route(ADMIN, 88100, "m3_strain_effect", values))
    prior = state(game)
    dice = prior.strain.events
    (case,) = interests(prior)
    assert bool(case.gain_event and case.tag) == (timing == "after") and not case.seen_event
    assert effects.get(ADMIN, work)["state"] == "pending"
    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="Resolve actual Strain"):
        activate(cycle, game, period)
    service = InterestService(strain)
    assert service.get(PLAYER, work)["account"] is None
    assert service.get(PLAYER, work)["seen_tag"] is None
    with pytest.raises(WorkflowError, match="original Handler and discovering Girl"):
        service.get(OTHER, work)
    assert not any(x.task == "m3_npc_interest" for x in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError, match="original Girl and NPC"):
        service.act(
            PLAYER, "absent-npc", work, prior.revision, channel=900, account="I found them."
        )
    if timing == "before":
        with pytest.raises(WorkflowError, match="after its original discovery"):
            service.act(ADMIN, "early-gain", work, prior.revision, manifestation="flesh")

    with ledger.transaction() as c:
        canon = place(state(game), PLAYER.user_id, mode="outside_frame", cell=(0, 0))
        game.event(c, PLAYER.user_id, "original-location", "synthetic.positions", canon)
    change(CastService(ActorService(strain.missions)), ADMIN, "join", npc)
    revision = state(game).revision
    appeared = "The Reader is at the far end of the corridor."
    asyncio.run(route(PLAYER, 88110, "m3_npc_interest", {"account": appeared}))
    (seen,) = interests(state(game))
    assert seen.seen_account == appeared and seen.seen_event and seen.seen_scene
    assert service.get(PLAYER, work)["seen_tag"] == (
        "Void of the brain" if timing == "after" else None
    )
    assert hidden not in str(service.get(PLAYER, work))
    replay = service.act(PLAYER, "88111", work, revision, channel=900, account=appeared)
    assert replay["state"] == ("resolved" if timing == "after" else "pending")
    if timing == "before":
        assert not seen.gain_event and effects.get(ADMIN, work)["state"] == "pending"
        asyncio.run(route(ADMIN, 88120, "m3_npc_interest", {"manifestation": ("flesh",)}))
        assert service.get(PLAYER, work)["seen_tag"] is None
    final = state(game)
    (done,) = interests(final)
    assert done.complete and done.gain_event != done.seen_event and final.strain.events == dice
    [(tag, label)] = corruption_options(final, npc)
    assert tag == "tag:" + done.tag
    assert label == ("Void of the brain" if timing == "after" else "Void of the flesh")
    assert effects.get(ADMIN, work)["state"] == "resolved"
    assert activate(cycle, game, period)["phase"] == "active"
