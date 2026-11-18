"""The original NPC's stable identity and Bond survive the two printed forms."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_void_spread import strain_source

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_strain_effects import effect_form
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_doppelganger_reveal import reveals
from girlframe.engine.m3_gorgon_catalog import ASSETS
from girlframe.engine.m3_world import CLASS_ASSETS
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("kind", ("benevolent", "erratic"))
def test_native_disguise_reveal_preserves_original_body_bonds_and_audience(ledger, kind):
    strain, game, _, _, identity = strain_source(ledger, 1, column=2)
    world = WorldService(strain.missions)
    original_bond = state(game).sheets["2"].review.creation.npc_bonds[0]
    mask = Npc(
        id="original-mask",
        name=original_bond.name or "Bonded person",
        jobs=("civilian",),
        detail="OTHER_PRIVATE_MASK_DETAILS",
        controller=OTHER.user_id,
        cell=(1, 1),
        revealed=True,
    )
    roles = NpcRoleService(world)
    offered = roles.offer(ADMIN, "offer-mask", state(game).revision, mask)
    roles.respond(OTHER, "accept-mask", offered["id"], state(game).revision, "accept")
    world.import_starting_npc(
        PLAYER, "link-mask", state(game).revision, original_bond.slot, mask.id
    )
    effects = EffectService(strain)
    build, commit, _ = effect_form(ADMIN, effects, identity)
    assert (mask.id, mask.name) not in next(x for x in build({}) if x.key == "mask").options
    names = ASSETS["doppleganger"][: CLASS_ASSETS[kind]]
    source = dict(
        mask=(mask.id,),
        assets=names,
        core=names[:1],
        weakness="Its original cover is exposed.",
        account="PRIVATE_REVEAL_TO_ORIGINAL_BOND",
        revealed=("no",),
        **{"class": (kind,)},
    )
    with pytest.raises(WorkflowError, match="actual control"):
        commit(ADMIN, "unaccepted-control", source)
    offered = roles.offer_transfer(
        OTHER, "transfer-mask", state(game).revision, mask.id, ADMIN.user_id
    )
    roles.respond(ADMIN, "accept-transfer", offered["id"], state(game).revision, "accept")

    build, commit, _ = effect_form(ADMIN, effects, identity)
    assert (mask.id, mask.name) in next(x for x in build({}) if x.key == "mask").options
    before = state(game)
    with pytest.raises(WorkflowError):
        commit(PLAYER, "wrong-owner", source)
    ledger.safety(PLAYER, "pause", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        commit(ADMIN, "paused", source)
    ledger.safety(PLAYER, "resume", ledger.status(PLAYER)["revision"], pause=False)
    assert "committed" in commit(ADMIN, "reveal", source)
    assert "committed" in commit(ADMIN, "reveal", source)
    after = state(game)
    assert before.strain.events == after.strain.events
    original = ActorRef(kind="npc", entity=mask.id)
    living = ActorRef(kind="gorgon", entity=mask.id)
    pilot = current_ref(after, PLAYER.user_id)
    assert depth(before, original, pilot) == depth(after, living, pilot) == 1
    assert after.world.starting_npc_links == before.world.starting_npc_links
    assert not any(x.id == mask.id for x in after.world.npcs)
    actual = next(x for x in after.world.gorgons if x.id == mask.id)
    assert actual.alive and actual.cell == mask.cell and actual.name == mask.name
    assert actual.types == ("doppleganger",) and actual.gorgon_class == kind
    (saved,) = reveals(after)
    assert saved.mask.id == mask.id and actual.mask_source == saved.source
    assert effects.get(ADMIN, identity)["state"] == "resolved"

    known = ActorService(strain.missions)
    assert any(
        x["ref"] == living.model_dump(mode="json") for x in known.known(PLAYER, pilot)["actors"]
    )
    assert not any(
        x["ref"] == living.model_dump(mode="json")
        for x in known.known(OTHER, current_ref(after, OTHER.user_id))["actors"]
    )
    assert not any(x["id"] == mask.id for x in world.get(OTHER)["world"]["gorgons"])
    with pytest.raises(WorkflowError, match="original audience"):
        EffectService(strain).disguise_revelation(OTHER, identity)

    async def read_original_notice():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(PLAYER) if x.task == "m3_strain_disguise_revelation")
        click = current(PLAYER.user_id, 46700)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, PLAYER.user_id).route(click, item)
        contents = click.edit_original_response.call_args.kwargs["content"]
        assert source["account"] in contents and mask.name in contents
        assert mask.detail not in contents

    asyncio.run(read_original_notice())
