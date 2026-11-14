"""Real authored NPC contact and exact Relay self-Asset cost, without a roll."""

from uuid import uuid4

import pytest
from test_ankou import native, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_world_service import transfer_npc

from girlframe.engine import m3_ankou as rules
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ankou import prove_encounter, prove_touch
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_relay_npc_touch_spends_original_asset_and_preserves_current_contact(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    world = WorldService(MissionService(ledger))
    target = ActorRef(kind="npc", entity="actual-relay-contact")
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=target.entity,
            name="Actual Relay contact",
            jobs=("guard",),
            controller=1,
            detail="Original independently controlled person",
            cell=(0, 0),
            revealed=True,
        ),
    )
    transfer_npc(world, ADMIN, OTHER, target.entity)
    actor = current_ref(state(game), 2)
    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        ("speech", "touch"),
        "Activate the actual Emotional Relay",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "Choose the actual nomination consequence",
    )
    native(
        controls,
        "encounter",
        person=(target.token,),
        kind=("touch",),
        private=("no",),
        account="I actually touch the original NPC here",
    )
    contact = rules.records(state(game), rules.Encounter)[-1]
    with ledger.engine.connect() as c:
        physical = resolve(state(game), target, profiles(c, ledger.campaign_id))
        assert physical.position_sha256 is None
        assert contact.target_position == physical.source_sha256
        assert prove_encounter(game, c, state(game), contact.id) == contact
    # A real accepted controller transfer changes the canonical NPC source.
    # The old contact cannot spend an Asset or affect its new owner's character.
    transfer_npc(world, OTHER, ADMIN, target.entity)
    asset = next(
        x.id for x in state(game).sheets["2"].assets if x.family == "frame" and not x.damaged
    )
    before = state(game)
    with pytest.raises(WorkflowError, match="changed actual bodies/contact"):
        controls.touch(
            PLAYER,
            str(uuid4()),
            before.revision,
            relay,
            contact.id,
            asset,
            "This original contact is now stale",
        )
    assert state(game) == before
    native(
        controls,
        "encounter",
        person=(target.token,),
        kind=("touch",),
        private=("no",),
        account="I establish new actual contact with the original NPC",
    )
    contact = rules.records(state(game), rules.Encounter)[-1]
    before = state(game)
    with pytest.raises(WorkflowError, match="actual active Relay"):
        controls.touch(
            OTHER, str(uuid4()), before.revision, relay, contact.id, asset, "Not the Relay owner"
        )
    assert state(game) == before
    result = controls.touch(
        PLAYER,
        str(uuid4()),
        before.revision,
        relay,
        contact.id,
        asset,
        "Damage this exact Asset to make this touched person Helpless",
    )
    after = state(game)
    assert next(x for x in after.sheets["2"].assets if x.id == asset).damaged
    assert is_helpless(after, target, actor)
    assert not is_helpless(after, current_ref(after, 3), actor)
    assert after.sheets["2"].heat == before.sheets["2"].heat
    assert after.sheets["2"].permissions == before.sheets["2"].permissions
    with ledger.engine.connect() as c:
        effect = prove_touch(game, c, after, result["id"])
    assert effect.actor == actor and effect.target == target and effect.asset == asset
    assert effect.completed_event == effect.event and game.dice.calls == 0
