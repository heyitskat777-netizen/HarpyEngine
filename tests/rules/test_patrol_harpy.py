"""Actual low-Void source, new World Harpy, reviewed body and private once-only sighting."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_physical_operations import place
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_patrol_harpy import open_patrol_harpy
from girlframe.engine import m3_patrol_harpy as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
from girlframe.engine.m3_void_state import HarpyIdentity
from girlframe.services.m3_access import load_registry
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_patrol_harpy import (
    PatrolHarpyService,
    knows,
    prove_encounter,
    prove_sighting,
)
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


class ActualD6:
    def __init__(self, face):
        self.face, self.calls = face, 0

    def roll_d6(self):
        self.calls += 1
        return self.face


def test_actual_low_void_patrol_new_harpy_body_review_native_die_and_private_sighting(
    ledger, tmp_path, monkeypatch
):
    """Deferred: source-only observation creates no fabricated combat, healing or replies."""
    strain, game = ready(ledger, face=3)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    strain.missions.access.registry = load_registry()
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        for sheet in actual.sheets.values():
            for component in sheet.assets:
                component.void = False
        game.event(c, 1, str(uuid4()), "synthetic.actual_patrol_baseline", actual)
    prepared(strain, game)
    request = next(x for x in state(game).strain.requests if x.track == "void")
    strain.roll(ADMIN, "actual-patrol-source-die", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "actual-patrol-source-column", request.id, 2, state(game).revision, 1)
    work = request.id + ":effect"
    assert next(x for x in state(game).strain.events if x.id == request.id).rule_id == rules.RULE
    service = PatrolHarpyService(strain)
    observer = current_ref(state(game), 2)
    with pytest.raises(WorkflowError):
        service.get(PLAYER, work)

    async def form(operation, number):
        opened = current(1, number)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_patrol_harpy(opened, service, work)
        chooser = opened.edit_original_response.call_args.kwargs["view"]
        chooser.values.update(operation=(operation,))
        selected = current(1, number + 1)
        selected.channel_id = 900
        await chooser.confirm.callback(selected)
        assert chooser.completed, selected.edit_original_response.call_args_list
        return selected.edit_original_response.call_args.kwargs["view"]

    async def introduce():
        introduction = await form("introduce", 993000)
        introduction.values.update(
            name="Actual quiet patrol Harpy",
            frame="Actual Gorgon shell",
            cell=("[0, 0]",),
            girl_asset="Actual retained hands",
            girl_detail="Actual original biological hands",
            girl_void=("no",),
            frame_asset="Actual Void shell",
            frame_detail="Actual Void-corrupted physical shell",
            frame_void=("yes",),
            account="PRIVATE_PATROL_SOURCE The actual Harpy is present here",
        )
        submitted = current(1, 993002)
        submitted.channel_id = 900
        await introduction.confirm.callback(submitted)
        assert introduction.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await introduction.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(introduce())
    source = next(
        x
        for x in state(game).facts
        if x.get("kind") == "patrol_harpy_introduction" and x["work"] == work
    )
    harpy = ActorRef.model_validate_json(source["actor"])
    target = next(x for x in state(game).world.pilots if x.id == harpy.entity)
    assert target.kind == "harpy" and target.controller == 1 and not target.revealed
    assert set(state(game).sheets) == {"2", "3"}
    # Review the actual controller-owned body through the existing source, not an invented Pilot.
    bodies = HarpyDefeatService(ledger, game=game)
    proposed = bodies.propose_runtime(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        NativeHarpyFacts(
            actor=harpy,
            linked=True,
            girl_cell=(0, 0),
            frame_cell=(0, 0),
            heat=0,
            frame_shutdown=False,
            body_incapacitated=False,
            custody="free",
            identities=(HarpyIdentity(id=str(uuid4()), name="Free"),),
            tags=(),
            account="Actual original Harpy body and known zero Heat/Identities",
            facts_confirmed=True,
        ),
    )
    bodies.review_setup(
        ADMIN,
        str(uuid4()),
        proposed["id"],
        state(game).revision,
        True,
        "I factually review this real original body, not a substitute account",
    )
    with ledger.engine.connect() as c:
        assert bodies._runtime(c, state(game), harpy).controller == 1
    before = state(game)
    with pytest.raises(WorkflowError):
        service.stage(
            OTHER,
            str(uuid4()),
            work,
            service.get(ADMIN, work)["revision"],
            before.revision,
            observer,
            harpy,
            900,
            "Not the original Handler",
        )
    with pytest.raises(WorkflowError):
        service.stage(
            ADMIN,
            str(uuid4()),
            work,
            service.get(ADMIN, work)["revision"],
            before.revision - 1,
            observer,
            harpy,
            900,
            "Stale patrol facts",
        )
    assert state(game) == before

    async def stage():
        actual = await form("stage", 993010)
        actual.values.update(
            observer=(observer.token,),
            harpy=(harpy.token,),
            channel=("900",),
            account="PRIVATE_PATROL I actually spot this Harpy while on patrol",
        )
        submitted = current(1, 993012)
        submitted.channel_id = 900
        await actual.confirm.callback(submitted)
        assert actual.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await actual.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(stage())
    encounter = rules.records(state(game), rules.Encounter)[-1]
    actual_d6 = ActualD6(4)
    strain.dice = actual_d6
    before = state(game)

    async def observe():
        opened = current(1, 993020)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_patrol_harpy(opened, service, work)
        actual = opened.edit_original_response.call_args.kwargs["view"]
        actual.values.update(operation=("roll",))
        submitted = current(1, 993021)
        submitted.channel_id = 900
        await actual.confirm.callback(submitted)
        assert actual.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await actual.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(observe())
    final = state(game)
    sighting = rules.records(final, rules.Sighting)[0]
    assert sighting.face == 4 and sighting.mood == "ready to flee" and actual_d6.calls == 1
    assert final.world == before.world and final.native_harpies == before.native_harpies
    assert final.sheets == before.sheets and final.placements == before.placements
    assert not next(x for x in final.world.pilots if x.id == harpy.entity).revealed
    assert service.get(ADMIN, work)["state"] == "resolved"
    assert service.get(PLAYER, work)["sighting"]["mood"] == sighting.mood
    assert service.get(PLAYER, work)["encounter"]["harpy_body"] == {"name": target.name}
    with pytest.raises(WorkflowError):
        service.get(OTHER, work)
    actors = ActorService(strain.missions)
    with ledger.engine.connect() as c:
        assert prove_encounter(game, c, final, encounter.id) == encounter
        assert prove_sighting(game, c, final, sighting.id) == sighting
        assert knows(game, c, final, observer, harpy)
        assert not knows(game, c, final, current_ref(final, 3), harpy)
        from girlframe.engine.m3_actors import resolve

        target_view = resolve(final, harpy, profiles(c, ledger.campaign_id))
        assert any(
            x["ref"] == harpy.model_dump(mode="json")
            for x in actors.known(PLAYER, observer)["actors"]
        )
        assert not any(
            x["ref"] == harpy.model_dump(mode="json")
            for x in actors.known(OTHER, current_ref(final, 3))["actors"]
        )
        assert target_view.vessel_id == encounter.harpy_vessel and target_view.cell == (0, 0)
        public = str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert "PRIVATE_PATROL" not in public
        row = (
            c.execute(
                sa.select(t.m3["m3_required_work"])
                .where(t.m3["m3_required_work"].c.id == work)
                .order_by(t.m3["m3_required_work"].c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert row["state"] == "resolved" and row["event_id"] == sighting.event

    async def reopen():
        opened = current(2, 993030)
        opened.channel_id = 999
        await opened.response.defer(ephemeral=True)
        await open_patrol_harpy(opened, service, work)
        shown = opened.edit_original_response.call_args.kwargs["view"]
        assert sighting.mood in "".join(x.body for x in shown.pages)
        assert encounter.account in "".join(x.body for x in shown.pages)

    asyncio.run(reopen())
