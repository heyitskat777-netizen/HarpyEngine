"""The same owned NPC becomes an actual active Pilot in the original starting Frame."""

import asyncio

import pytest
from test_ancillary_creation import enable, scenario
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.discord_adapter.m3_ancillary import open_offer
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_leviathan_arrival import external_pose
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_candidate_promotion import KIND, RULE
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_candidate_original_owner_activates_real_pilot_with_actual_frame_and_bond(
    ledger,
    tmp_path,
    monkeypatch,
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    missions = MissionService(ledger)
    npc = Npc(
        id="pilot-candidate",
        name="Original Candidate",
        jobs=("pilot_candidate", "base_personnel"),
        detail="Actual original recruit.",
        cell=(0, 0),
        controller=PLAYER.user_id,
        revealed=True,
    )
    roles = NpcRoleService(WorldService(missions))
    offered_npc = roles.offer(ADMIN, "candidate-introduction", state(game).revision, npc)
    roles.respond(PLAYER, "original-npc", offered_npc["id"], state(game).revision, "accept")
    original = ActorRef(kind="npc", entity=npc.id)
    other = current_ref(state(game), OTHER.user_id)
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", original)
    with ledger.transaction() as c:
        canon = set_depth(state(game), original, other, 2, "existing-original-bond")
        game.event(c, ADMIN.user_id, "original-relationship", "synthetic.existing_bond", canon)
    service = AncillaryService(missions)

    async def invite(click):
        await open_offer(click, service, service.invite_options(ADMIN))

    asyncio.run(
        submit_form(
            ADMIN,
            invite,
            dict(controller=(str(PLAYER.user_id),), site=("0",), candidate=(original.token,)),
            94600,
        )
    )
    (offer,) = ancillary.offers(state(game))
    assert offer.candidate == original and not ancillary.records(state(game))

    def gear(label):
        return ancillary.NamedAsset(name=label, description="Actual born equipment.")

    draft = ancillary.Draft(
        name=npc.name,
        book="SOLDIER",
        bond=other,
        frame_catalogue="SOLDIER_3",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS["SOLDIER"].assets[:2]),
        frame_assets=tuple(gear(x) for x in ancillary.frame_assets("SOLDIER", "SOLDIER_3")[:2]),
    )
    with pytest.raises(WorkflowError, match="original invited"):
        service.respond(OTHER, "take-other-npc", offer.id, state(game).revision, draft)
    ledger.engine.dispose()
    outcome = service.respond(PLAYER, "become-pilot", offer.id, state(game).revision, draft)
    new = ActorRef.model_validate(outcome["actor"])
    final = state(game)
    assert not any(x.id == npc.id for x in final.world.npcs)
    assert any(
        x.id == new.entity and x.name == npc.name and x.controller == PLAYER.user_id
        for x in final.world.pilots
    )
    assert depth(final, new, other) == 2
    actual = external_pose(final, new)
    assert (
        actual.mode == "piloting" and actual.frame_cell == (0, 0) and actual.owner == PLAYER.user_id
    )
    assert any(
        role.actor == new and role.controller == PLAYER.user_id
        for current in final.scene_casts
        for role in current.roles
    )
    assert any(x.get("kind") == KIND and x.get("npc") == npc.id for x in final.facts)
