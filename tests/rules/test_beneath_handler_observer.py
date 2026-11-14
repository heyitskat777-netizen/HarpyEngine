"""Native Girls retain their owned pin response beside a real Handler observer."""

from test_cast_service import change
from test_ledger import ADMIN
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService


def test_native_beneath_handler_observer_keeps_owned_pin_response(ledger, monkeypatch):
    import test_beneath_service as fixture
    from test_beneath_ui import (
        test_native_high_uses_one_base_and_one_extra_and_holds_lock_through_real_response_play,
    )

    original = fixture.ready

    def ready_with_handler(store, faces=(4, 5)):
        game, worker, gateway = original(store, faces)
        approval = store.policy.m3_approval
        store.policy = store.policy.model_copy(
            update={
                "m3_approval": approval.model_copy(
                    update={"subsystems": approval.subsystems | {"world"}}
                )
            }
        )
        actor = active_handler(state(game))
        assert actor is not None
        cast = CastService(ActorService(MissionService(store)))
        change(cast, ADMIN, "join", actor)
        assert any(x.actor == actor for x in state(game).scene_casts[0].roles)
        return game, worker, gateway

    monkeypatch.setattr(fixture, "ready", ready_with_handler)
    test_native_high_uses_one_base_and_one_extra_and_holds_lock_through_real_response_play(ledger)
