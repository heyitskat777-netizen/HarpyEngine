"""The original Abyssal Acolyte's real equipment and consent-scoped Void contact."""

import asyncio

import pytest
from test_ancillary_creation import HARPY, enable, scenario
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_physical_operations import bindings

from girlframe.discord_adapter.m3_abysstech import open_abysstech_contact
from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine import m3_physical as physical
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world import update
from girlframe.services.inbox import InboxService
from girlframe.services.m3_abysstech import RULE, AbysstechService, records
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def test_native_abysstech_contact_is_private_and_applies_actual_owned_effect(
    ledger, tmp_path, monkeypatch
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    missions = MissionService(ledger)
    create = AncillaryService(missions)
    offer = create.invite(
        ADMIN,
        "invite-abyssal",
        state(game).revision,
        PLAYER.user_id,
        "city0",
        "group",
        (HARPY,),
    )["id"]

    def asset(name):
        return ancillary.NamedAsset(name=name, description="Owned synthetic abysstech gear")

    draft = ancillary.Draft(
        name="Original local Acolyte",
        book="ABYSSAL ACOLYTE",
        frame_catalogue="JANUS",
        bond=HARPY,
        girl_assets=(asset("Ripped-Out Link"), asset("Devotee Lenses")),
        frame_assets=tuple(
            asset(x) for x in ancillary.frame_assets("ABYSSAL ACOLYTE", "JANUS")[:2]
        ),
    )
    source = create.respond(PLAYER, "create-abyssal", offer, state(game).revision, draft)
    actor = ActorRef.model_validate(source["actor"])
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", actor)
    with ledger.transaction() as c:
        canon = state(game)
        girl = current_ref(canon, OTHER.user_id)
        canon = physical.cockpit_exit(
            canon, bindings(canon), girl, "actual-abyssal-exit", "I exit the original cockpit."
        )
        existing = next(x for x in canon.placements if x.actor == girl)
        canon.world = update(
            canon.world,
            pilots=tuple(
                x.model_copy(update=dict(cell=existing.girl_cell)) if x.id == actor.entity else x
                for x in canon.world.pilots
            ),
        )
        contacted = next(x for x in canon.sheets["3"].assets if x.family == "girl")
        contacted.void = True
        contacted.concealed = True
        contacted.name = "Original concealed synthetic Void gear"
        game.event(c, OTHER.user_id, "place-actual", "synthetic.placement", canon)
    service = AbysstechService(game)
    menu = service.menu(PLAYER, 900, actor)
    assert contacted.name not in str(menu)
    tool = next(x for x, value in menu["tools"].items() if value == "Ripped-Out Link")
    girl = current_ref(state(game), OTHER.user_id)

    async def start(click):
        await open_cast(click, cast)
        picker = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        await picker.open_item(click, "abysstech:" + actor.token)

    def initial(sequence):
        asyncio.run(
            submit_form(
                PLAYER,
                start,
                dict(person=(girl.token,), tool=(tool,), account="I reach with my actual tool."),
                sequence,
            )
        )
        return records(state(game))[-1].id

    def choose(viewer, identity, option, sequence):
        asyncio.run(
            submit_form(
                viewer,
                lambda click: open_abysstech_contact(click, service, identity),
                dict(choice=(option,)),
                sequence,
            )
        )

    first = initial(93500)
    inbox = InboxService(ledger)
    assert any(x.identity == first and x.task == "m3_abysstech" for x in inbox.items(OTHER))
    assert not any(x.identity == first for x in inbox.items(ADMIN))
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(PLAYER, first)
    choose(OTHER, first, contacted.id, 93504)
    ledger.engine.dispose()
    assert service.get(PLAYER, first)["asset"] == contacted.name
    choose(PLAYER, first, "heat", 93508)
    assert ancillary.find(state(game), actor).heat == 2

    second = initial(93512)
    choose(OTHER, second, contacted.id, 93516)
    choose(PLAYER, second, "pressure", 93520)
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(PLAYER, second)
    choose(OTHER, second, "helpless", 93524)
    settled = state(game)
    assert records(settled)[-1].outcome == "helpless"
    assert is_helpless(settled, girl, actor)
    assert not next(x for x in settled.sheets["3"].assets if x.id == contacted.id).damaged
