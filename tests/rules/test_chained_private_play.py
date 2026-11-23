"""The private encounter lifts only the Chained Darling's source-scoped restriction."""

import asyncio

from test_ancillary_creation import enable, scenario
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state

from girlframe.discord_adapter.m3_ancillary_intimacy import open_ancillary_intimacy_choice
from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_chained_darling import RULE
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_intimacy import CHAINED, AncillaryIntimacyService, records
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_physical import PhysicalService


def test_chained_private_play_effect_ends_on_the_actual_scene_close(ledger, tmp_path, monkeypatch):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE, CHAINED))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    offered = creation.invite(
        ADMIN,
        "private-chained-invite",
        state(game).revision,
        PLAYER.user_id,
        "city0",
        "group",
    )

    def gear(name):
        return ancillary.NamedAsset(name=name, description="Actual original gear.")

    draft = ancillary.Draft(
        name="Original Chained Darling",
        book="CHAINED DARLING",
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS["CHAINED DARLING"].assets[:2]),
        frame_assets=tuple(gear(x) for x in ancillary.frame_assets("CHAINED DARLING", "JANUS")[:2]),
    )
    result = creation.respond(
        PLAYER,
        "private-original-chained",
        offered["id"],
        state(game).revision,
        draft,
    )
    actor = ActorRef.model_validate(result["actor"])
    partner = current_ref(state(game), OTHER.user_id)
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", actor)
    placement = ChainedPlacementService(game)
    physical = placement.propose(
        PLAYER,
        "initial-outside",
        900,
        actor,
        state(game).revision,
        "outside_frame",
        "I am outside my own Frame.",
    )
    placement.decide(ADMIN, "verified-outside", physical["id"], state(game).revision, True)
    assert is_helpless(state(game), actor)
    MovementService(game).move(
        OTHER,
        "private-counterpart-arrives",
        state(game).revision,
        900,
        partner,
        (0, 4),
        frame=True,
        account="I arrive in the same area.",
    )
    physical_service = PhysicalService(ledger)
    position = physical_service.preview(OTHER)["position_sha256"]
    physical_service.operate(
        OTHER,
        "present-physical-counterpart",
        state(game).revision,
        CockpitAction(
            actor=partner,
            operation="exit",
            expected_position=position,
            account="I step outside beside her.",
            confirmed=True,
        ),
        channel=900,
    )
    service = AncillaryIntimacyService(game)
    trial = service.offer(
        PLAYER, "abandoned-invitation", 900, actor, state(game).revision, partner.token
    )
    inbox = InboxService(ledger)
    assert not any(x.identity == trial["id"] for x in inbox.items(ADMIN))
    asyncio.run(
        submit_form(
            OTHER,
            lambda click: open_ancillary_intimacy_choice(click, service, trial["id"], "withdraw"),
            dict(choice=("withdraw",)),
            94200,
        )
    )
    assert records(state(game))[0].disposition == "withdrawn"

    async def cast_menu(click):
        await open_cast(click, cast)
        picker = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        await picker.open_item(click, "ancillary-private-play:" + actor.token)

    asyncio.run(
        submit_form(
            PLAYER,
            cast_menu,
            dict(person=(partner.token,)),
            94204,
        )
    )
    original = next(x for x in records(state(game)) if x.step == "consent")
    game.dice = Dice((4, 5))
    for offset, viewer, step, decision in (
        (94208, OTHER, "consent", dict(choice=("yes",))),
        (94212, ADMIN, "verify", dict(choice=("yes",))),
        (94216, PLAYER, "roll", dict(choice=("roll",), heat="0")),
        (94220, PLAYER, "middle", dict(choice=("apply",))),
    ):
        asyncio.run(
            submit_form(
                viewer,
                lambda click, step=step: open_ancillary_intimacy_choice(
                    click, service, original.id, step
                ),
                decision,
                offset,
            )
        )
    resolved = next(x for x in records(state(game)) if x.id == original.id)
    assert resolved.roll.faces == (4, 5)
    assert resolved.disposition == "applied" and resolved.step == "closed"
    assert is_helpless(state(game), partner, actor) and not is_helpless(state(game), actor)
    game.close_scene(ADMIN, "close-actual-private-scene", 900)
    assert is_helpless(state(game), actor)
