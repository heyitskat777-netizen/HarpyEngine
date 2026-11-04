from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_service import service
from test_world import initial

from girlframe.database import tables as t
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store):
    missions, game = service(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "strain", "playbooks"}}
            )
        }
    )
    svc = WorldService(missions)
    world = initial()
    svc.initialize(
        ADMIN,
        "world-initialize",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    return svc, game


def test_world_initialize_once_and_hidden_gorgon_never_leaks_to_player_or_event_metadata(ledger):
    svc, game = ready(ledger)
    private = svc.get(ADMIN, private=True)
    assert private["world"]["gorgons"][0]["id"] == "secret"
    public = svc.get(PLAYER)
    assert public["world"]["gorgons"] == [] and "secret" not in str(public)
    with pytest.raises(WorkflowError):
        svc.get(PLAYER, private=True)
    world = initial()
    with pytest.raises(WorkflowError, match="already exists"):
        svc.initialize(
            ADMIN, "reset", state(game).revision, world.board, world.locations, world.gorgons[0]
        )
    with ledger.engine.connect() as c:
        assert "benevolent" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert "secret" not in str(list(c.scalars(sa.select(t.commands.c.outcome_json))))
    assert InboxService(ledger).page(PLAYER).total >= 0


def test_npc_control_is_claimed_by_actual_member_and_keeps_private_records_private(ledger):
    svc, game = ready(ledger)
    npc = Npc(
        id="npc",
        name="PRIVATE_NPC_NAME",
        jobs=("intelligence_agent",),
        detail="PRIVATE_DETAIL",
        controller=1,
        cell=(0, 0),
    )
    svc.npc(ADMIN, "introduce", state(game).revision, npc)
    assert "PRIVATE_NPC" not in str(svc.get(PLAYER))
    with pytest.raises(WorkflowError, match="living introduced"):
        svc.claim_npc(PLAYER, "cannot-claim-hidden", state(game).revision, npc.id)
    with pytest.raises(WorkflowError, match="under your control"):
        svc.npc(
            ADMIN,
            "assign-other",
            state(game).revision,
            npc.model_copy(update={"id": "another", "controller": 2}),
        )
    visible = npc.model_copy(
        update={"id": "visible", "name": "Introduced person", "revealed": True}
    )
    svc.npc(ADMIN, "introduce-visible", state(game).revision, visible)
    revision = state(game).revision
    claimed = svc.claim_npc(PLAYER, "claim", revision, "visible")
    assert svc.claim_npc(PLAYER, "claim", revision, "visible") == claimed
    assert state(game).world.npcs[-1].controller == 2


def test_handler_cannot_introduce_a_self_controlled_director(ledger):
    svc, game = ready(ledger)
    before = state(game)
    with pytest.raises(WorkflowError, match="different human"):
        svc.npc(
            ADMIN,
            "director-needs-separate-player",
            before.revision,
            Npc(
                id="director",
                name="Director",
                jobs=("director",),
                detail="Authority",
                controller=1,
                cell=(0, 0),
            ),
        )
    assert state(game) == before


def test_concurrent_npc_claims_use_expected_state_and_do_not_both_succeed(ledger):
    svc, game = ready(ledger)
    svc.npc(
        ADMIN,
        "npc",
        state(game).revision,
        Npc(
            id="npc",
            name="Shared NPC",
            jobs=("civilian",),
            detail="An identifying quirk",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    revision = state(game).revision

    def claim(viewer):
        try:
            return svc.claim_npc(viewer, "claim-" + str(viewer.user_id), revision, "npc")
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, (PLAYER, OTHER)))
    assert sum(x is not None for x in results) == 1


def test_pause_and_stale_world_forms_cannot_mutate_but_saved_views_stay_available(ledger):
    svc, game = ready(ledger)
    before = state(game)
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        svc.reveal(ADMIN, "stale", before.revision - 1, "secret", "Encounter")
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.reveal(ADMIN, "paused", before.revision, "secret", "Encounter")
    assert svc.get(ADMIN, private=True)["world"] and state(game) == before


def test_world_reveal_is_explicit_and_rollback_after_event_restores_visibility(ledger, monkeypatch):
    svc, game = ready(ledger)
    original = svc.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic after-event failure")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError):
        svc.reveal(ADMIN, "reveal", state(game).revision, "secret", "The Cadre encounters it")
    assert svc.get(PLAYER)["world"]["gorgons"] == []
    monkeypatch.setattr(svc.game, "event", original)
    svc.reveal(ADMIN, "reveal", state(game).revision, "secret", "The Cadre encounters it")
    assert svc.get(PLAYER)["world"]["gorgons"][0]["name"] == "secret"


def test_world_survives_real_backup_and_canonical_state_rebuild(ledger, tmp_path):
    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.onboarding import OnboardingStore

    svc, game = ready(ledger)
    before = svc.get(ADMIN, private=True)
    game.rebuild()
    assert svc.get(ADMIN, private=True) == before
    destination = tmp_path / "world-backup.db"
    copy_database(Path(ledger.engine.url.database), destination)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(destination)))
    try:
        restored = WorldService(
            MissionService(OnboardingStore(engine, ledger.policy), svc.missions.access.registry)
        )
        assert restored.get(ADMIN, private=True) == before
    finally:
        engine.dispose()


def test_starting_npc_link_is_confirmed_by_its_owner_once_without_copying_private_feelings(ledger):
    svc, game = ready(ledger)
    bond = state(game).sheets["2"].review.creation.npc_bonds[0]
    npc = Npc(
        id="starting",
        name=bond.name or "Introduced contact",
        jobs=("civilian",),
        detail="A known person",
        controller=1,
        cell=(0, 0),
        revealed=True,
    )
    svc.npc(ADMIN, "introduce-starting", state(game).revision, npc)
    options = svc.bond_options(PLAYER)
    assert any(x[0] == str(bond.slot) + ":starting" for x in options["options"])
    with pytest.raises(WorkflowError, match="own saved"):
        svc.import_starting_npc(ADMIN, "not-owner", state(game).revision, bond.slot, npc.id)
    revision = state(game).revision
    result = svc.import_starting_npc(PLAYER, "link", revision, bond.slot, npc.id)
    assert svc.import_starting_npc(PLAYER, "link", revision, bond.slot, npc.id) == result
    world = state(game).world
    assert world.npcs[0].bonds == {"pilot:2": 1}
    assert world.starting_npc_links[0].character_id
    with pytest.raises(WorkflowError, match="already linked"):
        svc.import_starting_npc(PLAYER, "link-again", state(game).revision, bond.slot, npc.id)
    assert not svc.bond_options(PLAYER)["options"]
    assert "feelings" not in svc.get(ADMIN, private=True)["world"]["npcs"][0]
