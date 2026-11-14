"""Actual Frame-resident copy coexists with Handler during native owned pin response."""

from uuid import uuid4

from test_cast_service import change
from test_clone_am import cast_copy, prepared
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_physical import PhysicalService


def test_native_beneath_actual_clone_and_handler_observers_keep_owned_pin(
    ledger, tmp_path, monkeypatch
):
    import test_beneath_service as fixture
    from test_beneath_ui import (
        test_native_high_uses_one_base_and_one_extra_and_holds_lock_through_real_response_play,
    )

    def ready_with_observers(store, faces=(4, 5)):
        game, _, copy, worker, gateway = prepared(store, tmp_path, monkeypatch)
        approval = store.policy.m3_approval
        store.policy = store.policy.model_copy(
            update={
                "m3_approval": approval.model_copy(
                    update={"subsystems": approval.subsystems | {"plays"}}
                ),
                "owner_m3_rulings": store.policy.owner_m3_rulings.model_copy(
                    update={"beneath_private_choices": "affected_owner"}
                ),
            }
        )
        physical = PhysicalService(store)
        for viewer in (PLAYER, OTHER):
            view = physical.preview(viewer)
            actor = ActorRef.model_validate(view["actor"])
            with store.engine.connect() as c:
                actual = resolve(state(game), actor, profiles(c, store.campaign_id))
            physical.operate(
                viewer,
                str(uuid4()),
                view["game_revision"],
                CockpitAction(
                    actor=actor,
                    operation="exit",
                    expected_position=actual.position_sha256,
                    account="Original Girl leaves actual cockpit before social confrontation",
                    confirmed=True,
                ),
                channel=900,
            )
        cast = cast_copy(game, copy)
        handler = active_handler(state(game))
        assert handler is not None
        change(cast, ADMIN, "join", handler)
        assert {"clone_am", "handler"} <= {x.actor.kind for x in state(game).scene_casts[0].roles}
        game.dice.faces = faces
        return game, worker, gateway

    monkeypatch.setattr(fixture, "ready", ready_with_observers)
    test_native_high_uses_one_base_and_one_extra_and_holds_lock_through_real_response_play(ledger)
