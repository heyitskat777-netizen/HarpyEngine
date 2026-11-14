"""Original owned Pulse into an actual NPC, with exact lossless receipt provenance."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou import buy, current, ready
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_ankou_controls import pulse_fields, selected_pulse
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_ankou_pulse import npc_move, world_tag
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ankou import apply_pulse, prove_tag
from girlframe.services.m3_ankou_support import move_tag
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_malleable import stage_birth
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_native_engage_pulse_preserves_original_tag_on_npc_and_one_receipt(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.RELAY, *rules.REQUISITIONS, "core.core.npcs", "core.core.npc-tags"),
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    before_purchase = state(game)
    buy(controls, rules.PULSE)
    assert state(game).sheets["2"].permissions < before_purchase.sheets["2"].permissions
    with ledger.transaction() as c:
        canon = state(game)
        original = TagState(
            id="original-owned-tag",
            label="PRIVATE_PREVIOUS_TAG",
            giver=OTHER.user_id,
            giver_actor=current_ref(canon, OTHER.user_id),
            giver_character=canon.sheets["3"].character_id,
            observers=(2, 3),
            marked=True,
            scene_used="prior-scene",
        )
        canon.sheets["2"].tags.append(original)
        game.event(c, 1, str(uuid4()), "synthetic.prior_owned_tag", canon)
    target = ActorRef(kind="npc", entity="actual-pulse-opponent")
    missions = MissionService(ledger)
    world = WorldService(missions)
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=target.entity,
            name="Actual Pulse Opponent",
            jobs=("guard",),
            cell=(0, 0),
            controller=ADMIN.user_id,
            revealed=True,
            detail="The original opposing NPC present for this real Engage",
        ),
    )
    cast = CastService(ActorService(missions))
    change(cast, ADMIN, "join", target)
    fields = asyncio.run(pulse_fields(current(), game))
    assert fields and original.id in str(fields)
    selected = selected_pulse({"ankou_pulse": (original.id,)})
    assert selected == original.id
    before = state(game)
    own = current_ref(before, PLAYER.user_id)
    # Rejected recipients must not consume the original Tag or alter saved state.
    for invalid in (ActorRef(kind="npc", entity="not-a-lossless-recipient"),):
        snapshot = before.model_copy(deep=True)
        with pytest.raises(WorkflowError):
            move_tag(snapshot, own, invalid, original.id)
        assert snapshot == before
    game.dice.faces = (4, 4)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="engage",
            target_actor=target,
            trigger_confirmed=True,
            heat=0,
            piloting=True,
            context="I engage the actual opposing NPC on this battlefield",
            ankou_pulse=selected,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["receipt"] is None:
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    after_move = state(game)
    assert original not in after_move.sheets["2"].tags
    npc = next(x for x in after_move.world.npcs if x.id == target.entity)
    assert next(x for x in npc.tags if x.id == original.id) == world_tag(original)
    assert after_move.sheets["3"] == before.sheets["3"]
    assert after_move.sheets["2"].permissions == before.sheets["2"].permissions
    assert after_move.sheets["2"].heat == before.sheets["2"].heat
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        for recipient in (own, target):
            snapshot = after_move.model_copy(deep=True)
            with pytest.raises(WorkflowError):
                apply_pulse(game, c, snapshot, saved, original.id, recipient, "forged-replay")
            assert snapshot == after_move
    uses = [x for x in rules.records(after_move, rules.TagUse) if x.kind == "pulse"]
    assert len(uses) == 1 and uses[0].source == action
    assert uses[0].original_tag == original
    assert uses[0].original_tag.observers == original.observers
    with ledger.engine.connect() as c:
        before_roll, after_roll = snapshots(game, c, uses[0].event)
        assert npc_move(before_roll, after_roll, target, original.id, uses[0].event)
        assert prove_tag(game, c, after_move, target, original.id) == uses[0]
        assert not stage_birth(
            game,
            c,
            before_roll,
            after_roll,
            original.giver_actor,
            target,
            original.id,
            uses[0].event,
        )
        audit = c.execute(
            sa.select(t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.campaign_id == ledger.campaign_id,
                t.events.c.id == uses[0].event,
            )
        ).one()
        raw = json.loads(audit.payload_json)
        assert audit.kind in ("m2.rolled", "m3.rolled")
        assert raw["action_id"] == action
        assert raw["receipt_id"] == game.action(c, action)["data"]["receipt"]["id"]
    assert uses[0].actor == own and uses[0].target == target and uses[0].tag == original.id
    asset = next(x for x in after_move.sheets["2"].assets if not x.damaged)
    result = answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover", "advance"),
        fields={"cover": asset.id, "advance": asset.id},
        text="I use my actual Frame to advance behind cover",
    )
    assert result["state"] == "complete" and game.dice.calls == 1
    reopened = state(game)
    assert rules.get(reopened, rules.TagUse, uses[0].id).original_tag == original
    assert next(x for x in reopened.world.npcs if x.id == target.entity).tags == npc.tags
    assert "PRIVATE_PREVIOUS_TAG" not in str(world.get(OTHER))
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_PREVIOUS_TAG" not in str(gateway.messages)
