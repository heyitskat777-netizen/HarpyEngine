"""Restartable surgery keeps Punishment pending until actual human-owned work finishes."""

import asyncio
from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_punishment_service import ended, submit

from girlframe.discord_adapter.m3_lobotomy import open_lobotomy, open_plan
from girlframe.engine.m3_lobotomy_state import Plan
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_lobotomy import LobotomyService
from girlframe.services.onboarding import WorkflowError


def begun(store):
    punishment, missions, game, mission, work = ended(store)
    surgery = submit(punishment, ADMIN, work, Details(kind="lobotomization"))["surgery"]
    return LobotomyService(store), punishment, missions, game, mission, work, surgery


def selection():
    return Plan(
        options=("memories", "play", "memory"),
        room="SOURCE_ROOM_CANARY",
        restraints="Actual restraints",
        tools="Actual tools",
        erase_slots=(0, 2),
        forbidden_play="defeat",
        memory="Actual implanted memory",
        identity="Source Identity",
    )


def test_surgery_is_owned_resumable_and_does_not_forge_original_patient_or_resolve_early(ledger):
    service, discipline, missions, game, mission, work, identity = begun(ledger)
    original = state(game).sheets["3"].model_dump_json()
    assert discipline.get(ADMIN, work)["state"] == "pending"
    assert state(game).sheets["3"].model_dump_json() == original
    data = service.get(ADMIN, identity)
    service.prepare(ADMIN, str(uuid4()), identity, data["game_revision"], selection())
    assert state(game).sheets["3"].model_dump_json() == original
    assert service.tasks(OTHER)[0]["phase"] == "responses"
    with pytest.raises(WorkflowError, match="actual owner"):
        service.respond(
            ADMIN,
            str(uuid4()),
            identity,
            state(game).revision,
            {x: "The Handler cannot supply this" for x in selection().options},
        )
    with pytest.raises(WorkflowError):
        service.get(PLAYER, identity)
    restarted = LobotomyService(ledger)
    restarted.respond(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        {x: "The original patient's actual narrative" for x in selection().options},
    )
    assert state(game).sheets["3"].model_dump_json() == original
    result = restarted.finish(ADMIN, str(uuid4()), identity)
    assert result["cause_count"] == 2
    actual = state(game)
    assert actual.lobotomies[-1].phase == "applied"
    assert actual.sheets["3"].blocked_plays[0].play == "defeat"
    assert len(actual.sheets["3"].identities) == 3
    assert discipline.get(ADMIN, work)["state"] == "resolved"
    assert not restarted.tasks(ADMIN) and not restarted.tasks(OTHER)
    with pytest.raises(WorkflowError):
        restarted.finish(ADMIN, str(uuid4()), identity)


def test_native_surgery_dropdown_plan_and_actual_patient_form_have_source_ownership(ledger):
    service, _, _, game, _, _, identity = begun(ledger)

    async def run():
        handler = current(1, 73101)
        await handler.response.defer(ephemeral=True)
        await open_lobotomy(handler, service, identity)
        selector = handler.edit_original_response.call_args.kwargs["view"].children[0]
        assert selector.min_values == 1 and selector.max_values == 3
        await open_plan(handler, service, identity, ("memories", "play"))
        form = handler.edit_original_response.call_args.kwargs["view"]
        fields = {x.key: x for x in form.fields}
        assert fields["erase"].maximum == fields["erase"].minimum == 2
        assert "defeat" in dict(fields["play"].options)
        service.prepare(ADMIN, str(uuid4()), identity, state(game).revision, selection())
        patient = current(3, 73102)
        await patient.response.defer(ephemeral=True)
        await open_lobotomy(patient, service, identity)
        response = patient.edit_original_response.call_args.kwargs["view"]
        assert {x.key for x in response.fields} == set(selection().options)
        assert not await response.interaction_check(handler)

    asyncio.run(run())


def test_actual_name_removal_updates_profile_and_clears_discord_nickname_from_source(ledger):
    import json

    import sqlalchemy as sa
    from test_character_tags import Guild

    from girlframe.database import tables as t
    from girlframe.discord_adapter.character_tags import DiscordCharacterTagGateway
    from girlframe.engine.m3_lobotomy import name_removal_source
    from girlframe.services.character_tags import CharacterTagSynchronizer

    service, discipline, _, game, _, work, identity = begun(ledger)
    selected = Plan(
        options=("name",),
        room="Actual room",
        restraints="Actual restraints",
        tools="Actual tools",
        new_name="",
    )
    service.prepare(ADMIN, str(uuid4()), identity, state(game).revision, selected)
    service.respond(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        {"name": "The original patient describes her skull's sound"},
    )
    service.finish(ADMIN, str(uuid4()), identity)
    assert name_removal_source(state(game), 3).id == identity
    assert discipline.get(ADMIN, work)["state"] == "resolved"
    with ledger.engine.connect() as c:
        public = c.scalar(
            sa.select(t.characters.c.public_json).where(
                t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "3"
            )
        )
    assert json.loads(public)["callsign"] == ""
    guild = Guild()
    guild.member.id = 3
    guild.member.nick = "OLD_NICKNAME"
    message = asyncio.run(
        CharacterTagSynchronizer(ledger).sync(OTHER, DiscordCharacterTagGateway(guild))
    )
    assert "nickname cleared" in message and guild.member.nick is None
    assert ledger.sync_job(OTHER)["state"] == "complete"
