"""An ordinary owned pin response remains usable with a real NPC observer."""

from uuid import uuid4

from test_enforcer_requisitions import approved
from test_ledger import ADMIN
from test_ledger import ledger as ledger
from test_m2_game import state
from test_world import initial

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService


def test_native_mixed_beneath_pin_without_feedback_keeps_owned_response(
    ledger, tmp_path, monkeypatch
):
    import test_beneath_service as fixture
    from test_beneath_ui import (
        test_native_high_uses_one_base_and_one_extra_and_holds_lock_through_real_response_play,
    )

    original = fixture.ready

    def ready_with_observer(store, faces=(4, 5)):
        game, worker, gateway = original(store, faces)
        approved(
            store,
            game,
            tmp_path,
            monkeypatch,
            extra=(
                "core.core.npcs",
                "core.core.npc-assets",
                "core.core.npc-tags",
            ),
        )
        approval = store.policy.m3_approval
        store.policy = store.policy.model_copy(
            update={
                "m3_approval": approval.model_copy(
                    update={"subsystems": approval.subsystems | {"world"}}
                )
            }
        )
        missions = MissionService(store)
        world = WorldService(missions)
        setup = initial()
        world.initialize(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            setup.board,
            setup.locations,
            setup.gorgons[0],
        )
        target = ActorRef(kind="npc", entity="ordinary-pin-observer")
        world.npc(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            Npc(
                id=target.entity,
                name="Ordinary witness",
                jobs=("doctor",),
                cell=(0, 0),
                detail="Already separately controlled observer",
                controller=1,
                revealed=True,
                employment="foundation",
            ),
        )
        cast = CastService(ActorService(missions))
        view = cast.view(ADMIN, 900)
        cast.change(
            ADMIN, str(uuid4()), 900, view["game_revision"], view["cast_revision"], "join", target
        )
        return game, worker, gateway

    monkeypatch.setattr(fixture, "ready", ready_with_observer)
    test_native_high_uses_one_base_and_one_extra_and_holds_lock_through_real_response_play(ledger)
