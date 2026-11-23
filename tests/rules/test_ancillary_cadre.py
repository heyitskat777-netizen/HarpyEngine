"""An explicitly formed Ancillary Cadre keeps its own actors and genuine Dog Status."""

import asyncio

import pytest
from test_ancillary_creation import REBEL, enable, scenario
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.discord_adapter.m3_ancillary_cadre import open_cadre_invitation
from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine import m3_ancillary_cadre as cadre
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_cadre import AncillaryCadreService
from girlframe.services.m3_ancillary_traits import BOY
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def test_actual_cadre_keeps_original_owners_and_changes_warboy_dog_pronouns(
    ledger,
    tmp_path,
    monkeypatch,
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(BOY,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    actors = ActorService(missions)
    cast = CastService(actors)
    old = state(game).order

    def create(viewer, book, name):
        invite = creation.invite(
            ADMIN,
            "create-" + name,
            state(game).revision,
            viewer.user_id,
            "city0",
            "group",
        )["id"]

        def gear(label):
            return ancillary.NamedAsset(name=label, description="Original known equipment.")

        draft = ancillary.Draft(
            name=name,
            book=book,
            frame_catalogue="JANUS",
            girl_assets=tuple(gear(x) for x in ancillary.STARTERS[book].assets[:2]),
            frame_assets=tuple(gear(x) for x in ancillary.frame_assets(book, "JANUS")[:2]),
        )
        result = creation.respond(viewer, "accept-" + name, invite, state(game).revision, draft)
        actor = ActorRef.model_validate(result["actor"])
        change(cast, viewer, "join", actor)
        return actor

    first = create(PLAYER, "CHAINED DARLING", "Original Chained Girl")
    second = create(OTHER, "WARBOY", "Original Warboy")
    assert actors.inspect(OTHER, second)["pronouns"] == "he/him"

    async def formation(click):
        await open_cast(click, cast)
        picker = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        await picker.open_item(click, "form-ancillary-cadre")

    asyncio.run(
        submit_form(
            ADMIN,
            formation,
            dict(handler=(REBEL.token,), rank1=(first.token,), rank2=(second.token,)),
            94400,
        )
    )
    (proposed,) = cadre.records(state(game))
    assert proposed.state == "pending"
    service = AncillaryCadreService(game)
    original = service.get(PLAYER, proposed.id)
    assert original["order"] == ("Original Chained Girl", "Original proposed member")
    with pytest.raises(WorkflowError, match="only your role"):
        service.approve(
            PLAYER, "not-my-role", proposed.id, original["revision"], second.token, True
        )

    for offset, viewer, role in (
        (94404, ADMIN, "handler"),
        (94408, PLAYER, first.token),
        (94412, OTHER, second.token),
    ):
        asyncio.run(
            submit_form(
                viewer,
                lambda click: open_cadre_invitation(click, service, proposed.id),
                dict(role=(role,), choice=("yes",)),
                offset,
            )
        )
    canon = state(game)
    assert cadre.actual_members(canon, cadre.current(canon, second)) == (first, second)
    assert state(game).order == old
    assert actors.inspect(OTHER, second)["ancillary_status"] == 2
    assert actors.inspect(OTHER, second)["pronouns"] == "she/her"
