"""Both Low Void contacts are actual role-owned and scene-bound Plays."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_strain_effects import DependentForm
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_benevolent_contact import RULE, contacts
from girlframe.engine.m3_strain_effects import Choice
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_benevolent_contact import ContactService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("play", ("offer_information", "take_interest"))
def test_benevolent_contact_gives_the_original_gorgon_its_performed_private_play(ledger, play):
    strain, game = ready(ledger, face=4)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    map_state = initial()
    WorldService(strain.missions).initialize(
        ADMIN,
        "map",
        state(game).revision,
        map_state.board,
        map_state.locations,
        map_state.gorgons[0],
    )
    with ledger.transaction() as c:
        baseline = state(game)
        for sheet in baseline.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, ADMIN.user_id, "non-void-start", "synthetic.nonvoid", baseline)
    prepared(strain, game)
    request = next(x for x in state(game).strain.requests if x.track == "void")
    strain.roll(ADMIN, "contact-die", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "contact-column", request.id, 2, state(game).revision, 2)
    work = request.id + ":effect"
    effects = EffectService(strain)
    before = state(game)
    account = "PRIVATE_FAVOUR_OFFER" if play == "offer_information" else "PRIVATE_INTEREST"
    choice = Choice(
        rule_id=RULE,
        account=account,
        target="secret",
        victim="2",
        contact_play=play,
        contact_channel=900,
    )
    assert effects.get(ADMIN, work)["rule_id"] == RULE
    with pytest.raises(WorkflowError, match="actual living Benevolent Gorgon"):
        effects.apply(ADMIN, "before-joining", work, 1, before.revision, choice)
    assert state(game) == before

    gorgon = ActorRef(kind="gorgon", entity="secret")
    change(CastService(ActorService(strain.missions)), ADMIN, "join", gorgon)
    revision = state(game).revision
    inbox = InboxService(ledger)

    async def route(viewer, number, task):
        item = next(x for x in inbox.items(viewer) if x.task == task and x.identity == work)
        click = current(viewer.user_id, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(click, item)
        return click.edit_original_response.call_args.kwargs

    async def perform():
        screen = await route(ADMIN, 85800, "m3_strain_effect")
        form = screen["view"]
        assert isinstance(form, DependentForm)
        form.values.update(
            contact_gorgon=("secret",),
            contact_girl=("2",),
            contact_channel=("900",),
            contact_play=(play,),
            account=account,
        )
        click = current(ADMIN.user_id, 85801)
        click.channel_id = 900
        await form.confirm.callback(click)
        assert form.completed

    asyncio.run(perform())
    assert EffectService(strain).apply(ADMIN, "85801", work, 1, revision, choice)["state"] == (
        "resolved"
    )
    (first,) = contacts(state(game))
    assert first.grant == work and first.speaker.actor == gorgon and first.recipient.controller == 2
    assert first.play == play and first.scene == state(game).scene_casts[0].id
    assert state(game).sheets == before.sheets and state(game).world == before.world
    assert state(game).strain.events == before.strain.events
    assert account in asyncio.run(route(PLAYER, 85810, "m3_benevolent_contact"))["content"]
    assert not any(x.task == "m3_benevolent_contact" for x in inbox.items(OTHER))
    service = ContactService(strain)
    with pytest.raises(WorkflowError, match="original speaker and addressee"):
        service.get(OTHER, work, 900)
    with pytest.raises(WorkflowError, match="original Gorgon controller"):
        service.repeat(PLAYER, "wrong-controller", work, state(game).revision, "3", 900, "Fake")

    async def reuse():
        form = (await route(ADMIN, 85820, "m3_benevolent_contact"))["view"]
        assert isinstance(form, NativeForm) and not isinstance(form, DependentForm)
        form.values.update(girl=("3",), account="PRIVATE_LATER_CONTACT")
        click = current(ADMIN.user_id, 85821)
        click.channel_id = 900
        await form.confirm.callback(click)
        assert form.completed

    asyncio.run(reuse())
    original, later = contacts(state(game))
    assert original == first and later.grant == first.grant and later.play == first.play
    assert later.recipient.controller == 3 and later.speaker == first.speaker
    assert service.get(OTHER, later.id, 900)["account"] == "PRIVATE_LATER_CONTACT"
    with pytest.raises(WorkflowError, match="original speaker and addressee"):
        service.get(PLAYER, later.id, 900)
