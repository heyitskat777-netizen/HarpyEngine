"""Verified Chained Darling placement makes the actual cockpit exit impose Helplessness."""

import asyncio

import pytest
from test_ancillary_creation import enable, scenario
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.discord_adapter.m3_chained_darling import open_chained_review
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_chained_darling import RULE
from girlframe.engine.m3_leviathan_arrival import external_pose
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService, records
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


def test_chained_darling_real_cockpit_exit_keeps_frame_and_makes_her_helpless(
    ledger, tmp_path, monkeypatch
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    missions = MissionService(ledger)
    ancillary_service = AncillaryService(missions)
    invitation = ancillary_service.invite(
        ADMIN,
        "chained-invite",
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
    created = ancillary_service.respond(
        PLAYER,
        "chained-create",
        invitation["id"],
        state(game).revision,
        draft,
    )
    actor = ActorRef.model_validate(created["actor"])
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", actor)
    service = ChainedPlacementService(game)
    assert external_pose(state(game), actor) is None

    async def cast_menu(click):
        await open_cast(click, cast)
        picker = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        await picker.open_item(click, "chained-placement:" + actor.token)

    asyncio.run(
        submit_form(
            PLAYER,
            cast_menu,
            dict(
                mode=("piloting",),
                account="I am actually piloting my original Frame in this square.",
            ),
            94000,
        )
    )
    (proposal,) = records(state(game))
    inbox = InboxService(ledger)
    assert any(
        x.identity == proposal.id and x.task == "m3_chained_placement" for x in inbox.items(ADMIN)
    )
    assert not any(x.identity == proposal.id for x in inbox.items(OTHER))
    with pytest.raises(WorkflowError, match="unavailable"):
        service.review(OTHER, proposal.id)
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_chained_review(click, service, proposal.id),
            dict(choice=("yes",)),
            94004,
        )
    )
    before = state(game)
    body = external_pose(before, actor)
    assert body.mode == "piloting" and not is_helpless(before, actor)

    asyncio.run(
        submit_form(
            PLAYER,
            cast_menu,
            dict(
                mode=("outside_frame",), account="I step out even though the drugs will take hold."
            ),
            94008,
        )
    )
    pending = next(x for x in records(state(game)) if x.decision is None)
    assert external_pose(state(game), actor) == body
    ledger.engine.dispose()
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_chained_review(click, service, pending.id),
            dict(choice=("yes",)),
            94012,
        )
    )
    final = state(game)
    after = external_pose(final, actor)
    assert after.mode == "outside_frame"
    assert after.frame == body.frame and after.frame_cell == body.frame_cell == (0, 4)
    assert is_helpless(final, actor, current_ref(final, OTHER.user_id))
    with pytest.raises(WorkflowError, match="Helplessness"):
        MovementService(game).move(
            PLAYER,
            "helpless-cannot-self-move",
            final.revision,
            900,
            actor,
            (0, 3),
            account="Try moving away unsupported.",
        )

    helper = current_ref(final, OTHER.user_id)
    MovementService(game).move(
        OTHER,
        "helper-approaches",
        final.revision,
        900,
        helper,
        after.frame_cell,
        frame=True,
        account="I bring my Frame next to hers.",
    )
    physical = PhysicalService(ledger)
    view = physical.preview(OTHER)
    physical.operate(
        OTHER,
        "helper-exits",
        state(game).revision,
        CockpitAction(
            actor=helper,
            operation="exit",
            expected_position=view["position_sha256"],
            account="I step out of my own Frame beside her.",
            confirmed=True,
        ),
        channel=900,
    )
    asyncio.run(
        submit_form(
            PLAYER,
            cast_menu,
            dict(
                mode=("inside_frame",),
                helper=(helper.token,),
                account="I ask for help getting back into my own Frame.",
            ),
            94016,
        )
    )
    entry = next(x for x in records(state(game)) if x.decision is None)
    assert any(x.identity == entry.id for x in inbox.items(OTHER))
    assert not any(x.identity == entry.id for x in inbox.items(ADMIN))
    asyncio.run(
        submit_form(
            OTHER,
            lambda click: open_chained_review(click, service, entry.id),
            dict(choice=("yes",)),
            94020,
        )
    )
    assert is_helpless(state(game), actor)
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_chained_review(click, service, entry.id),
            dict(choice=("yes",)),
            94024,
        )
    )
    returned = state(game)
    returned_body = external_pose(returned, actor)
    assert returned_body.mode == "inside_frame" and returned_body.frame == body.frame
    assert returned_body.frame_cell == body.frame_cell
    assert not is_helpless(returned, actor)
