"""A real meeting turns only the original verified prior facts into scoped Tags."""

import asyncio

import pytest
from test_ancillary_creation import REBEL, enable, scenario
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.discord_adapter.m3_chronically_online import open_recollection_inbox
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chronically_online import RULE, ChronicallyOnlineService, records
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.onboarding import WorkflowError


def test_chronically_online_turns_verified_prior_knowledge_into_actual_private_tags(
    ledger, tmp_path, monkeypatch
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    missions = MissionService(ledger)
    service = ChronicallyOnlineService(game)
    ancillary_service = AncillaryService(missions)
    invited = ancillary_service.invite(
        ADMIN,
        "recall-original-invite",
        state(game).revision,
        PLAYER.user_id,
        "city0",
        "group",
        contacts=(REBEL,),
    )

    def gear(name):
        return ancillary.NamedAsset(name=name, description="Original gear.")

    draft = ancillary.Draft(
        name="Revolutionary with a good memory",
        book="REVOLUTIONARY IDEALIST",
        bond=REBEL,
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS["REVOLUTIONARY IDEALIST"].assets[:2]),
        frame_assets=tuple(
            gear(x) for x in ancillary.frame_assets("REVOLUTIONARY IDEALIST", "JANUS")[:2]
        ),
    )
    result = ancillary_service.respond(
        PLAYER,
        "revolutionary",
        invited["id"],
        state(game).revision,
        draft,
    )
    revolutionary = ActorRef.model_validate(result["actor"])
    pilot = current_ref(state(game), OTHER.user_id)
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", revolutionary)

    async def cast_menu(click):
        await open_cast(click, cast)
        picker = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        await picker.open_item(click, "recollection:" + revolutionary.token)

    asyncio.run(
        submit_form(
            PLAYER,
            cast_menu,
            dict(
                pilot=(pilot.token,),
                first=("combat",),
                first_text="Relies on sensor fusion",
                second=("internet",),
                second_text="Used to review lost radio broadcasts",
                source="I read the original Pilot's plain-text public post before today.",
            ),
            93900,
        )
    )
    (recall,) = records(state(game))
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(ADMIN, recall.id)
    asyncio.run(
        submit_form(
            OTHER,
            lambda click: open_recollection_inbox(click, service, recall.id),
            dict(choice=("yes",)),
            93904,
        )
    )
    assert records(state(game))[0].verified
    assert not state(game).sheets[pilot.entity].tags
    inbox = InboxService(ledger)
    assert not any(x.identity == recall.id for x in inbox.items(PLAYER))

    MovementService(game).move(
        OTHER,
        "pilot-arrives-at-the-actual-square",
        state(game).revision,
        900,
        pilot,
        (0, 4),
        frame=True,
        account="I arrive within local radio range to greet the Revolutionary.",
    )
    assert any(
        x.identity == recall.id and x.task == "m3_chronically_online" for x in inbox.items(PLAYER)
    )
    asyncio.run(
        submit_form(
            PLAYER,
            lambda click: open_recollection_inbox(click, service, recall.id),
            dict(choice=("met",)),
            93908,
        )
    )
    assert not state(game).sheets[pilot.entity].tags
    asyncio.run(
        submit_form(
            OTHER,
            lambda click: open_recollection_inbox(click, service, recall.id),
            dict(choice=("apply",)),
            93912,
        )
    )
    final = state(game)
    assert records(final)[0].stage == "used"
    tags = final.sheets[pilot.entity].tags
    assert [x.label for x in tags] == [
        "Relies on sensor fusion",
        "Used to review lost radio broadcasts",
    ]
    assert all(x.giver_actor == revolutionary and set(x.observers) == {2, 3} for x in tags)
