"""One actual paid Pulse moves an unchanged Tag to its genuine Engage opponent."""

import asyncio
from uuid import uuid4

import pytest
from test_ankou import buy, current, ready
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.discord_adapter.m3_ankou_controls import pulse_fields, selected_pulse
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ankou import apply_pulse
from girlframe.services.m3_ankou_support import move_tag
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def test_native_engage_pulse_preserves_tag_on_actual_handler_and_one_roll(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
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
    target = active_handler(state(game))
    assert target is not None
    cast = CastService(ActorService(MissionService(ledger)))
    change(cast, ADMIN, "join", target)
    fields = asyncio.run(pulse_fields(current(), game))
    assert fields and original.id in str(fields)
    selected = selected_pulse({"ankou_pulse": (original.id,)})
    assert selected == original.id
    before = state(game)
    own = current_ref(before, PLAYER.user_id)
    # Rejected recipients must not consume the original Tag or alter saved state.
    for invalid in (
        ActorRef(kind="handler", entity=target.entity, incarnation="not-this-body"),
        ActorRef(kind="npc", entity="not-a-lossless-recipient"),
    ):
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
            context="I engage the actual opposing Handler on this battlefield",
            ankou_pulse=selected,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["receipt"] is None:
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    after_move = state(game)
    assert original not in after_move.sheets["2"].tags
    assert next(x for x in after_move.handler_tags if x.id == original.id) == original
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
    assert next(x for x in state(game).handler_tags if x.id == original.id) == original
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_PREVIOUS_TAG" not in str(gateway.messages)
